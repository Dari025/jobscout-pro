"""Freehire public job API adapter.

Uses Freehire's public read/search API (no key for personal, non-commercial use).
The API excludes closed postings from search and supplies the employer's ATS URL.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import httpx

from job_scout.models import (
    CompInterval,
    Compensation,
    Job,
    JobType,
    Location,
    ScrapeParams,
    Site,
)
from job_scout.scrapers import BaseScraper

log = logging.getLogger("job_scout.scrapers.freehire")
API_URL = "https://freehire.me/api/v1/agent/jobs/search"
USER_AGENT = "JobScout-Pro/1.0 (personal job search; https://github.com/Dari025/jobscout-pro)"


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).date()
        except (ValueError, OSError, OverflowError):
            return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, TypeError, OverflowError):
        try:
            return date.fromisoformat(str(value)[:10])
        except (ValueError, TypeError):
            return None


def _specific_http_url(value: object) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return ""
    path = (parsed.path or "/").rstrip("/").lower()
    if path in {"", "/", "/jobs", "/careers", "/search", "/jobs/search"}:
        return ""
    if parsed.hostname.lower() in {"google.com", "www.google.com", "bing.com", "www.bing.com"}:
        if path in {"/search", "/url", "/goto"}:
            return ""
    return raw


def _job_types(value: object) -> list[JobType]:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "full_time": JobType.FULL_TIME,
        "part_time": JobType.PART_TIME,
        "contract": JobType.CONTRACT,
        "internship": JobType.INTERNSHIP,
        "fellowship": JobType.INTERNSHIP,
        "temporary": JobType.TEMPORARY,
    }
    mapped = mapping.get(raw)
    return [mapped] if mapped else []


def parse_freehire_job(raw: dict) -> Job | None:
    """Convert one public API record to the shared Job model; never invent a posting URL."""
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()
    company = str(raw.get("company") or raw.get("company_name") or "").strip()
    slug = str(raw.get("public_slug") or raw.get("external_id") or "").strip()
    if not title or not company or not slug or raw.get("closed_at"):
        return None

    url = _specific_http_url(raw.get("url"))
    if not url:
        # Freehire's own per-posting page is a safe, concrete fallback when an
        # employer ATS URL is absent or rejected as a generic page.
        url = f"https://freehire.me/jobs/{slug}"
    enrichment = raw.get("enrichment") if isinstance(raw.get("enrichment"), dict) else {}
    remote = str(raw.get("work_mode") or "").lower() == "remote"
    location_text = str(raw.get("location") or "").strip()
    remote = remote or bool(re.search(r"\bremote\b", location_text, re.I))

    cities = raw.get("cities") if isinstance(raw.get("cities"), list) else []
    countries = raw.get("countries") if isinstance(raw.get("countries"), list) else []
    city = str(cities[0]).strip() if cities else (None if remote else location_text or None)
    country = str(countries[0]).strip() if countries else None
    location = Location(city=city, country=country, is_remote=remote)

    posted = _parse_date(raw.get("posted_at")) or _parse_date(raw.get("created_at"))
    types = _job_types(enrichment.get("employment_type"))
    comp = None
    salary_min = enrichment.get("salary_min")
    salary_max = enrichment.get("salary_max")
    if salary_min is not None or salary_max is not None:
        interval_map = {
            "year": CompInterval.YEARLY,
            "month": CompInterval.MONTHLY,
            "week": CompInterval.WEEKLY,
            "day": CompInterval.DAILY,
            "hour": CompInterval.HOURLY,
        }
        interval = interval_map.get(str(enrichment.get("salary_period") or "year").lower())
        try:
            comp = Compensation(
                min_amount=float(salary_min) if salary_min is not None else None,
                max_amount=float(salary_max) if salary_max is not None else None,
                currency=str(enrichment.get("salary_currency") or "EUR").upper(),
                interval=interval,
            )
        except (TypeError, ValueError):
            comp = None

    description = str(raw.get("description") or enrichment.get("summary") or "").strip()
    return Job(
        source=Site.FREEHIRE,
        source_id=slug,
        url=url,
        title=title,
        company=company,
        location=location,
        description=description,
        job_type=types,
        compensation=comp,
        date_posted=posted,
    )


class FreehireScraper(BaseScraper):
    """Reliable first-party ATS search across Spain and remote Europe."""

    site = Site.FREEHIRE

    def scrape(self, params: ScrapeParams) -> list[Job]:
        queries = [str(params.search_term or "").strip()]
        # If the qualifier-heavy query is sparse, retry with the core role rather
        # than returning no results solely because "intern"/"junior" is not indexed.
        relaxed = re.sub(
            r"\b(intern(ship)?|junior|entry[\s-]?level|graduate|trainee|working student)\b",
            "",
            queries[0],
            flags=re.I,
        )
        relaxed = re.sub(r"\s+", " ", relaxed).strip()
        if relaxed and relaxed.casefold() != queries[0].casefold():
            queries.append(relaxed)

        jobs: list[Job] = []
        seen: set[str] = set()
        timeout = min(max(self.config.request_timeout, 8), 15)
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            for query in queries:
                api_params = {
                    "q": query,
                    "q_fields": "title,description,company,location",
                    "description_format": "text",
                    "limit": min(max(params.results_wanted, 10), 40),
                    "order": "desc",
                }
                location_text = str(params.location or "").casefold()
                if "remote" in location_text and ("europe" in location_text or "eu" in location_text):
                    api_params["regions"] = "eu"
                    api_params["work_mode"] = "remote"
                elif any(token in location_text for token in ("spain", "españa", "madrid")):
                    api_params["countries"] = "ES"

                # Preserve junior opportunities with no inferred seniority. A strict
                # internship-only filter would drop postings whose level is unstated.
                api_params["seniority"] = "intern,junior"
                api_params["seniority_include_unspecified"] = "true"
                response = client.get(API_URL, params=api_params)
                if response.status_code == 429:
                    raise RuntimeError("Freehire API limit reached (HTTP 429); try again later.")
                response.raise_for_status()
                payload = response.json()
                rows = payload.get("data", []) if isinstance(payload, dict) else []
                if not isinstance(rows, list):
                    raise RuntimeError("Freehire returned an unexpected JSON response.")
                for raw in rows:
                    job = parse_freehire_job(raw)
                    if not job or job.source_id in seen:
                        continue
                    seen.add(job.source_id)
                    jobs.append(job)
                    if len(jobs) >= params.results_wanted:
                        break
                if len(jobs) >= params.results_wanted:
                    break
                # A relaxed second query is only useful if the first query was sparse.
                if query == queries[0] and len(jobs) >= max(5, params.results_wanted // 2):
                    break

        log.info(
            "Freehire returned %s matching postings for %r in %s",
            len(jobs), params.search_term, params.location,
        )
        return jobs[: params.results_wanted]
