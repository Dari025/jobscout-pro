"""Freehire public job API adapter.

Uses Freehire's public read/search API (no key for personal, non-commercial use).
The API excludes closed postings from search and supplies the employer's ATS URL.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime
from urllib.parse import urlparse

import httpx

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
from job_scout.scrapers import BaseScraper

log = logging.getLogger("job_scout.scrapers.freehire")
API_URL = "https://freehire.me/api/v1/agent/jobs/search"
USER_AGENT = "JobScout-Pro/1.0 (personal job search; https://github.com/Dari025/jobscout-pro)"


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=UTC).date()
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
    remote = remote or bool(re.search(r"\bremote\b", location_text, re.IGNORECASE))

    cities = raw.get("cities") if isinstance(raw.get("cities"), list) else []
    countries = raw.get("countries") if isinstance(raw.get("countries"), list) else []
    clean_cities = list(dict.fromkeys(str(value).strip() for value in cities if str(value).strip()))
    clean_countries = list(dict.fromkeys(str(value).strip() for value in countries if str(value).strip()))
    if remote and location_text.casefold() == "remote":
        city = None
    elif len(clean_cities) > 1:
        city = "Varios destinos: " + ", ".join(clean_cities[:4]) + ("…" if len(clean_cities) > 4 else "")
    elif clean_cities:
        city = clean_cities[0]
    else:
        city = location_text or None
    country = clean_countries[0] if len(clean_countries) == 1 else None
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


def _seniority_params(search_term: str) -> dict[str, str]:
    """Only constrain seniority when the user explicitly asks for junior/intern roles."""
    if re.search(
        r"\b(intern(ship)?|junior|entry[\s-]?level|graduate|trainee|working student)\b",
        str(search_term or ""),
        flags=re.IGNORECASE,
    ):
        return {
            "seniority": "intern,junior",
            "seniority_include_unspecified": "true",
        }
    return {}


def _row_location_matches(raw: dict, location: str) -> bool:
    """Fail closed when the listing's geography does not support the requested location."""
    target = " ".join(str(location or "").casefold().split())
    countries = raw.get("countries") if isinstance(raw.get("countries"), list) else []
    country_codes = {str(value).strip().casefold() for value in countries if str(value).strip()}
    cities = raw.get("cities") if isinstance(raw.get("cities"), list) else []
    city_values = {str(value).strip().casefold() for value in cities if str(value).strip()}
    location_text = str(raw.get("location") or "").casefold()
    regions = raw.get("regions") if isinstance(raw.get("regions"), list) else []
    region_codes = {str(value).strip().casefold() for value in regions if str(value).strip()}
    work_mode = str(raw.get("work_mode") or "").casefold()
    remote_flag = raw.get("remote") is True or work_mode == "remote" or "remote" in location_text

    eu_codes = {
        "at", "be", "bg", "hr", "cy", "cz", "dk", "ee", "fi", "fr",
        "de", "gr", "hu", "is", "ie", "it", "lv", "li", "lt", "lu",
        "mt", "nl", "no", "pl", "pt", "ro", "sk", "si", "es", "se",
        "ch", "gb",
    }
    if "remote" in target:
        if not remote_flag:
            return False
        if "europe" in target or re.search(r"(?<!\\w)eu(?!\\w)", target):
            return "eu" in region_codes or bool(country_codes & eu_codes)
        if any(token in target for token in ("world", "worldwide", "global")):
            return True

    country_aliases = {
        "spain": {"es", "spain", "españa"},
        "españa": {"es", "spain", "españa"},
        "united states": {"us", "usa", "united states"},
        "usa": {"us", "usa", "united states"},
        "united kingdom": {"gb", "uk", "united kingdom"},
        "uk": {"gb", "uk", "united kingdom"},
        "portugal": {"pt", "portugal"},
        "germany": {"de", "germany"},
        "france": {"fr", "france"},
        "italy": {"it", "italy"},
        "netherlands": {"nl", "netherlands"},
        "ireland": {"ie", "ireland"},
        "switzerland": {"ch", "switzerland"},
        "canada": {"ca", "canada"},
        "australia": {"au", "australia"},
        "poland": {"pl", "poland"},
        "sweden": {"se", "sweden"},
    }
    for name, aliases in country_aliases.items():
        if name in target:
            if name in {"spain", "españa"} and "remote" not in target:
                return bool(country_codes & aliases) or "spain" in location_text or "españa" in location_text
            return bool(country_codes & aliases) or any(alias in location_text for alias in aliases)

    # Plain city searches (e.g. "Bilbao") require a city or location hit.
    city_query = target
    for separator in (",", " - "):
        if separator in city_query:
            city_query = city_query.split(separator, 1)[0].strip()
    city_query = city_query.removeprefix("remote ").strip()
    if city_query and city_query not in {"spain", "europe", "worldwide", "world"}:
        return any(city_query in city for city in city_values) or city_query in location_text
    return True


def _within_age_limit(posted: date | None, hours_old: int) -> bool:
    """Keep undated jobs visible, but enforce any explicit age limit."""
    if posted is None or hours_old <= 0:
        return True
    max_days = max(1, (int(hours_old) + 23) // 24)
    return (date.today() - posted).days <= max_days


def _validate_search_metadata(payload: dict, location: str) -> None:
    """Fail closed if Freehire silently ignores a requested geography filter."""
    meta = payload.get("meta") if isinstance(payload, dict) else {}
    meta = meta if isinstance(meta, dict) else {}
    ignored = meta.get("ignored_params") or []
    if not ignored:
        return

    ignored_text = str(ignored).casefold()
    log.warning("Freehire ignored search parameter(s): %s", ignored)

    location_text = str(location or "").casefold()
    if "remote" in location_text and ("europe" in location_text or "eu" in location_text):
        required = ("regions", "work_mode")
    elif any(token in location_text for token in ("spain", "españa", "madrid")):
        required = ("countries",)
    else:
        required = ()

    ignored_required = [name for name in required if name.casefold() in ignored_text]
    if ignored_required:
        raise RuntimeError(
            "Freehire ignored required geographic filter(s) "
            f"{', '.join(ignored_required)} for location {location!r}; "
            "refusing to show potentially wrong-region postings."
        )


class FreehireScraper(BaseScraper):
    """Reliable first-party ATS search across Spain and remote Europe."""

    site = Site.FREEHIRE

    def scrape(self, params: ScrapeParams) -> list[Job]:
        original_query = str(params.search_term or "").strip()
        queries = role_search_variants(original_query)
        # If the qualifier-heavy query is sparse, retry without seniority words.
        # Role variants stay behind the exact query so we preserve user intent first.
        relaxed = re.sub(
            r"\b(intern(ship)?|junior|entry[\s-]?level|graduate|trainee|working student)\b",
            "",
            original_query,
            flags=re.IGNORECASE,
        )
        relaxed = re.sub(r"\s+", " ", relaxed).strip()
        if relaxed and relaxed.casefold() != original_query.casefold():
            for variant in role_search_variants(relaxed):
                if variant.casefold() not in {query.casefold() for query in queries}:
                    queries.append(variant)

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
                elif "remote" in location_text and any(token in location_text for token in ("world", "worldwide", "global")):
                    api_params["work_mode"] = "remote"
                elif any(token in location_text for token in ("spain", "españa", "madrid")):
                    api_params["countries"] = "ES"
                else:
                    country_codes = {
                        "united states": "US", "usa": "US", "uk": "GB",
                        "united kingdom": "GB", "portugal": "PT", "germany": "DE",
                        "france": "FR", "italy": "IT", "netherlands": "NL",
                        "ireland": "IE", "switzerland": "CH", "canada": "CA",
                        "australia": "AU", "poland": "PL", "sweden": "SE",
                    }
                    for country_name, code in country_codes.items():
                        if country_name in location_text:
                            api_params["countries"] = code
                            break

                # Do not impose an entry-level filter on a general job search.
                # Restrict seniority only when the query explicitly asks for it.
                api_params.update(_seniority_params(original_query))
                response = client.get(API_URL, params=api_params)
                if response.status_code == 429:
                    raise RuntimeError("Freehire API limit reached (HTTP 429); try again later.")
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise RuntimeError("Freehire returned an unexpected JSON object.")
                _validate_search_metadata(payload, params.location)
                rows = payload.get("data", [])
                if not isinstance(rows, list):
                    raise RuntimeError("Freehire returned an unexpected JSON response.")
                for raw in rows:
                    if not _row_location_matches(raw, params.location):
                        continue
                    job = parse_freehire_job(raw)
                    if not job or job.source_id in seen:
                        continue
                    if not _within_age_limit(job.date_posted, params.hours_old):
                        continue
                    seen.add(job.source_id)
                    jobs.append(job)
                    if len(jobs) >= params.results_wanted:
                        break
                if len(jobs) >= params.results_wanted:
                    break
                # Stop once a useful list is available, regardless of which
                # exact/expanded query supplied the matches.
                if len(jobs) >= max(5, params.results_wanted // 2):
                    break

        log.info(
            "Freehire returned %s matching postings for %r in %s",
            len(jobs), params.search_term, params.location,
        )
        return jobs[: params.results_wanted]
