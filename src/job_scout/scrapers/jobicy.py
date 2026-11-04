"""Jobicy public API adapter.

The public feed contains remote roles from the last seven days. Responses are
cached per geographic filter for one hour, respecting Jobicy's polling guidance.
Every displayed URL remains the canonical Jobicy listing URL and cards must
credit the source.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from job_scout.config import ScrapingConfig
from job_scout.models import (
    Compensation,
    CompInterval,
    Job,
    JobType,
    Location,
    ScrapeParams,
    Site,
)
from job_scout.role_terms import role_search_variants

log = logging.getLogger("job_scout.scrapers.jobicy")
API_URL = "https://jobicy.com/api/v2/remote-jobs"
CACHE_TTL_SECONDS = 3600
MAX_PAGE_SIZE = 100
_CACHE_LOCK = threading.Lock()
_FEED_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}

_COUNTRY_SLUGS = {
    "spain": "spain", "españa": "spain", "madrid": "spain",
    "barcelona": "spain", "valencia": "spain", "bilbao": "spain",
    "united states": "usa", "usa": "usa", "u.s.a.": "usa",
    "united kingdom": "uk", "uk": "uk", "britain": "uk",
    "portugal": "portugal", "germany": "germany", "france": "france",
    "italy": "italy", "netherlands": "netherlands", "ireland": "ireland",
    "switzerland": "switzerland", "canada": "canada", "australia": "australia",
    "poland": "poland", "sweden": "sweden", "denmark": "denmark",
    "finland": "finland", "norway": "norway", "belgium": "belgium",
    "austria": "austria",
}

_QUALIFIERS = {
    "intern", "internship", "junior", "jr", "entry", "level",
    "graduate", "trainee", "working", "student", "senior", "sr",
    "lead", "principal", "staff", "the", "and", "or", "of",
}


def _normalise(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9+#]+", " ", str(value or "").casefold()).split())


def _geo_slug(location: str) -> str:
    value = _normalise(location)
    if "europe" in value or value in {"eu", "remote eu"}:
        return "europe"
    if any(word in value for word in ("world", "worldwide", "global", "anywhere")):
        return "anywhere"
    # A city-qualified Spain search should use the country-level eligibility filter.
    for key, slug in _COUNTRY_SLUGS.items():
        if _normalise(key) in value:
            return slug
    # Custom unknown locations use the broad feed, then receive a strict
    # client-side eligibility check where the location is unambiguous.
    return "anywhere"


def _location_matches(job_geo: str, location: str) -> bool:
    requested = _normalise(location)
    eligible = _normalise(job_geo)
    if not eligible:
        return False
    if "remote" in requested and any(x in requested for x in ("europe", "eu")):
        return any(x in eligible for x in (
            "europe", "emea", "anywhere", "austria", "belgium", "bulgaria",
            "croatia", "cyprus", "czechia", "denmark", "estonia", "finland",
            "france", "germany", "greece", "hungary", "iceland", "ireland",
            "italy", "latvia", "liechtenstein", "lithuania", "luxembourg",
            "malta", "netherlands", "norway", "poland", "portugal",
            "romania", "slovakia", "slovenia", "spain", "sweden",
            "switzerland", "united kingdom", "uk",
        ))
    if "spain" in requested or "españa" in requested:
        return any(x in eligible for x in ("spain", "emea", "europe", "anywhere"))
    for country, slug in _COUNTRY_SLUGS.items():
        if _normalise(country) in requested:
            return slug in eligible or "anywhere" in eligible or "emea" in eligible
    # "Anywhere" is a valid global-remote eligibility, but an unknown named
    # city should not be treated as if that employer accepted applicants there.
    if any(x in requested for x in ("world", "worldwide", "global", "anywhere")):
        return True
    city = requested.removeprefix("remote ").strip()
    return city in eligible or "anywhere" in eligible


def _matches_title(
    title: str,
    query: str,
    *,
    job_types: Any = None,
    job_level: Any = None,
) -> bool:
    title_n = _normalise(title)
    if not title_n:
        return False
    query_n = _normalise(query)
    type_n = _normalise(job_types)
    level_n = _normalise(job_level)

    wants_intern = bool(re.search(r"\b(intern|internship|trainee|working student|fellowship)\b", query_n))
    if wants_intern and any(level in level_n for level in ("senior", "lead", "principal", "staff", "director", "head")):
        return False
    if wants_intern and not (
        re.search(r"\b(intern|internship|trainee|working student|fellowship)\b", title_n)
        or re.search(r"\b(intern|internship|trainee|working student|fellowship)\b", type_n)
    ):
        return False

    wants_junior = bool(re.search(r"\b(junior|graduate|entry level|new grad)\b", query_n))
    wants_senior = bool(re.search(r"\b(senior|lead|principal|staff|director|head)\b", query_n))
    if wants_junior and any(level in level_n for level in ("senior", "lead", "principal", "director", "head")):
        return False
    if wants_senior and any(level in level_n for level in ("junior", "intern", "entry")):
        return False

    for variant in role_search_variants(query):
        candidate = _normalise(variant)
        if candidate and re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", title_n):
            return True
    tokens = [token for token in query_n.split() if token not in _QUALIFIERS]
    if not tokens:
        return True
    # Avoid matching on only "data", "analyst", "engineer", etc. Every
    # meaningful term in the role must appear in the actual title.
    return all(re.search(rf"(?<!\w){re.escape(token)}(?!\w)", title_n) for token in tokens)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.date()
    except (ValueError, TypeError, OverflowError):
        return None


def _html_to_text(value: Any) -> str:
    source = html.unescape(str(value or ""))
    source = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", source)
    source = re.sub(r"(?s)<[^>]+>", " ", source)
    return " ".join(source.split())


def _job_types(values: Any) -> list[JobType]:
    if not isinstance(values, list):
        values = [values] if values else []
    output: list[JobType] = []
    for value in values:
        text = _normalise(value)
        if any(word in text for word in ("intern", "internship", "working student", "fellowship")):
            mapped = JobType.INTERNSHIP
        elif any(word in text for word in ("part time", "parttime")):
            mapped = JobType.PART_TIME
        elif any(word in text for word in ("contract", "freelance", "contractor")):
            mapped = JobType.CONTRACT
        elif any(word in text for word in ("temporary", "temp")):
            mapped = JobType.TEMPORARY
        elif "full time" in text or text in {"fulltime", "full"}:
            mapped = JobType.FULL_TIME
        else:
            continue
        if mapped not in output:
            output.append(mapped)
    return output


def _compensation(raw: dict[str, Any]) -> Compensation | None:
    low = raw.get("salaryMin", raw.get("annualSalaryMin"))
    high = raw.get("salaryMax", raw.get("annualSalaryMax"))
    if low in (None, "") and high in (None, ""):
        return None
    periods = {
        "yearly": CompInterval.YEARLY, "year": CompInterval.YEARLY,
        "annual": CompInterval.YEARLY, "annually": CompInterval.YEARLY,
        "monthly": CompInterval.MONTHLY, "month": CompInterval.MONTHLY,
        "weekly": CompInterval.WEEKLY, "week": CompInterval.WEEKLY,
        "daily": CompInterval.DAILY, "day": CompInterval.DAILY,
        "hourly": CompInterval.HOURLY, "hour": CompInterval.HOURLY,
    }
    try:
        return Compensation(
            min_amount=float(low) if low not in (None, "") else None,
            max_amount=float(high) if high not in (None, "") else None,
            currency=str(raw.get("salaryCurrency") or "EUR").upper(),
            interval=periods.get(str(raw.get("salaryPeriod") or "yearly").casefold()),
        )
    except (TypeError, ValueError):
        return None


def parse_jobicy_job(raw: dict[str, Any]) -> Job | None:
    if not isinstance(raw, dict):
        return None
    job_id = str(raw.get("id") or "").strip()
    title = str(raw.get("jobTitle") or "").strip()
    company = str(raw.get("companyName") or "").strip()
    url = str(raw.get("url") or "").strip()
    if not (job_id and title and company):
        return None
    if not url.startswith("https://jobicy.com/jobs/"):
        return None
    geo = str(raw.get("jobGeo") or "Anywhere").strip()
    geo_parts = [part.strip() for part in geo.split(",") if part.strip()]
    city = geo_parts[0] if len(geo_parts) == 1 and _normalise(geo_parts[0]) != "anywhere" else (
        "Varios destinos: " + ", ".join(geo_parts[:4]) if len(geo_parts) > 1 else None
    )
    location = Location(city=city, country=None, is_remote=True)
    return Job(
        source=Site.JOBICY,
        source_id=job_id,
        url=url,
        title=title,
        company=company,
        location=location,
        description=_html_to_text(raw.get("jobDescription") or raw.get("jobExcerpt")),
        job_type=_job_types(raw.get("jobType")),
        compensation=_compensation(raw),
        date_posted=_parse_date(raw.get("pubDate")),
    )


def _load_feed(geo: str, timeout: float) -> list[dict[str, Any]]:
    now = time.monotonic()
    wall_now = time.time()
    with _CACHE_LOCK:
        cached = _FEED_CACHE.get(geo)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return list(cached[1])

        # Persist only public Jobicy listings (never CVs or profile data) so
        # repeated dashboard runs do not poll the provider more than hourly.
        cache_root = Path(
            os.environ.get("JOBSCOUT_CACHE_DIR")
            or (Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache")) / "JobScout" / "cache")
        )
        cache_path = cache_root / f"jobicy_{geo}.json"
        try:
            if cache_path.is_file() and wall_now - cache_path.stat().st_mtime < CACHE_TTL_SECONDS:
                cached_payload = json.loads(cache_path.read_text(encoding="utf-8"))
                cached_rows = cached_payload.get("jobs") if isinstance(cached_payload, dict) else None
                if isinstance(cached_rows, list):
                    clean_cached = [row for row in cached_rows if isinstance(row, dict)]
                    _FEED_CACHE[geo] = (now, clean_cached)
                    return list(clean_cached)
        except (OSError, ValueError, TypeError):
            log.warning("Could not read Jobicy cache for %s; refreshing feed.", geo)
        try:
            response = httpx.get(
                API_URL,
                params={"count": MAX_PAGE_SIZE, "geo": geo},
                headers={"Accept": "application/json", "User-Agent": "JobScoutPro/1.0"},
                timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
                follow_redirects=True,
            )
            if response.status_code == 429:
                raise RuntimeError("Jobicy API limit reached (HTTP 429). Try again later.")
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Jobicy tardó demasiado en responder.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"No se pudo consultar Jobicy: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("success") is False:
            message = payload.get("error", "respuesta inesperada") if isinstance(payload, dict) else "respuesta inesperada"
            raise RuntimeError(f"Jobicy devolvió un error: {message}")
        rows = payload.get("jobs", [])
        if not isinstance(rows, list):
            raise TypeError("Jobicy devolvió una lista de ofertas con formato inesperado.")
        clean_rows = [row for row in rows if isinstance(row, dict)]
        _FEED_CACHE[geo] = (now, clean_rows)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = cache_path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps({"cached_at": wall_now, "jobs": clean_rows}, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary_path.replace(cache_path)
        except (OSError, TypeError, ValueError):
            log.warning("Could not persist Jobicy cache for %s.", geo)
        return list(clean_rows)


class JobicyScraper:
    """Search the public remote-only Jobicy feed and filter it locally."""

    site = Site.JOBICY

    def __init__(self, config: ScrapingConfig):
        self.config = config

    def scrape(self, params: ScrapeParams) -> list[Job]:
        geo = _geo_slug(params.location)
        rows = _load_feed(geo, timeout=min(max(self.config.request_timeout, 8), 20))
        output: list[Job] = []
        seen: set[str] = set()
        for raw in rows:
            if not _location_matches(str(raw.get("jobGeo") or ""), params.location):
                continue
            if not _matches_title(
                str(raw.get("jobTitle") or ""),
                params.search_term,
                job_types=raw.get("jobType"),
                job_level=raw.get("jobLevel"),
            ):
                continue
            job = parse_jobicy_job(raw)
            if not job or job.source_id in seen:
                continue
            job.location = Location(city=f"Remoto desde {params.location}", country=None, is_remote=True)
            if params.hours_old > 0:
                if job.date_posted is None and not params.include_unknown_dates:
                    continue
                if job.date_posted is not None:
                    age_days = (date.today() - job.date_posted).days
                    if age_days > (params.hours_old + 23) // 24:
                        continue
            seen.add(job.source_id)
            output.append(job)
            if len(output) >= params.results_wanted:
                break
        log.info(
            "Jobicy returned %s matching remote listings for %r in %s",
            len(output), params.search_term, params.location,
        )
        return output
