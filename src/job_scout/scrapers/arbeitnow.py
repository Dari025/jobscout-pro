"""Arbeitnow public European job-board API adapter."""
from __future__ import annotations

import html
import logging
import re
import threading
import time
from datetime import date, datetime, timezone

import httpx

from job_scout.models import Job, JobType, Location, ScrapeParams, Site
from job_scout.scrapers import BaseScraper
from job_scout.role_terms import role_matches_text
from job_scout.util import html_to_text

log = logging.getLogger("job_scout.scrapers.arbeitnow")
API_URL = "https://www.arbeitnow.com/api/job-board-api"
USER_AGENT = "JobScout-Pro/1.0 (personal job search; https://github.com/Dari025/jobscout-pro)"
_CACHE_TTL_SECONDS = 900
_CACHE_LOCK = threading.Lock()
_CACHE_TIME = 0.0
_CACHE_JOBS: list[dict] = []


def _load_feed(timeout: float = 12.0) -> list[dict]:
    """Load a few newest feed pages once per process, shared by parallel search tasks."""
    global _CACHE_TIME, _CACHE_JOBS
    with _CACHE_LOCK:
        if _CACHE_JOBS and time.monotonic() - _CACHE_TIME < _CACHE_TTL_SECONDS:
            return list(_CACHE_JOBS)

        jobs: list[dict] = []
        seen: set[str] = set()
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            for page in range(1, 4):
                response = client.get(API_URL, params={"page": page})
                if response.status_code == 429:
                    if not jobs:
                        raise RuntimeError("Arbeitnow API limit reached (HTTP 429); try again later.")
                    log.warning("Arbeitnow rate limited after %s page(s); using partial feed", page - 1)
                    break
                response.raise_for_status()
                payload = response.json()
                rows = payload.get("data", []) if isinstance(payload, dict) else []
                if not isinstance(rows, list):
                    raise RuntimeError("Arbeitnow returned an unexpected JSON response.")
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    slug = str(row.get("slug") or row.get("url") or "").strip()
                    if slug and slug not in seen:
                        seen.add(slug)
                        jobs.append(row)
                links = payload.get("links", {}) if isinstance(payload, dict) else {}
                if not links.get("next") or not rows:
                    break

        if jobs:
            _CACHE_JOBS = jobs
            _CACHE_TIME = time.monotonic()
        return list(jobs)


def _normalise(value: object) -> str:
    value = html.unescape(str(value or "")).casefold()
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).date()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def _matches_term(row: dict, search_term: str) -> bool:
    title = _normalise(row.get("title"))
    tags = row.get("tags") if isinstance(row.get("tags"), list) else []
    tag_text = _normalise(" ".join(str(item) for item in tags))
    # Do not require seniority words to appear literally in the title. They
    # are often encoded in job_types or omitted from the listing altogether.
    ignored = {
        "intern", "internship", "junior", "entry", "level", "graduate",
        "trainee", "working", "student", "the", "and", "or",
    }
    tokens = [token for token in re.findall(r"[a-z0-9]+", _normalise(search_term)) if token not in ignored]
    if not tokens:
        return True
    joined = f"{title} {tag_text}"
    # Recognise common geology/hydrogeology aliases and compound titles.
    if role_matches_text(search_term, joined):
        return True
    return any(re.search(r"(?<!\\w)" + re.escape(token) + r"(?!\\w)", joined) for token in tokens)


def _job_types(values: object) -> list[JobType]:
    if not isinstance(values, list):
        return []
    text = " ".join(str(value).casefold().replace("-", "_").replace(" ", "_") for value in values)
    output: list[JobType] = []
    if any(value in text for value in ("intern", "working_student", "student")):
        output.append(JobType.INTERNSHIP)
    if any(value in text for value in ("part_time", "parttime", "teilzeit")):
        output.append(JobType.PART_TIME)
    if any(value in text for value in ("full_time", "fulltime", "vollzeit")):
        output.append(JobType.FULL_TIME)
    if "contract" in text or "freelance" in text:
        output.append(JobType.CONTRACT)
    return output


def parse_arbeitnow_job(raw: dict) -> Job | None:
    if not isinstance(raw, dict):
        return None
    slug = str(raw.get("slug") or "").strip()
    title = str(raw.get("title") or "").strip()
    company = str(raw.get("company_name") or "").strip()
    url = str(raw.get("url") or "").strip()
    if not slug or not title or not company or not url:
        return None
    if not url.startswith(("https://www.arbeitnow.com/jobs/", "https://arbeitnow.com/jobs/",
                           "https://www.arbeitnow.co.uk/jobs/", "https://arbeitnow.co.uk/jobs/")):
        return None

    remote = bool(raw.get("remote"))
    location_text = str(raw.get("location") or "").strip()
    location = Location(
        city=None if remote and location_text.lower() == "remote" else location_text or None,
        country=None,
        is_remote=remote,
    )
    description = html_to_text(str(raw.get("description") or ""))
    posted = _parse_date(raw.get("created_at"))
    return Job(
        source=Site.ARBEITNOW,
        source_id=slug,
        url=url,
        title=title,
        company=company,
        location=location,
        description=description,
        job_type=_job_types(raw.get("job_types")),
        date_posted=posted,
    )


class ArbeitnowScraper(BaseScraper):
    """Query the cached latest European listings and keep role/location matches."""

    site = Site.ARBEITNOW

    def scrape(self, params: ScrapeParams) -> list[Job]:
        rows = _load_feed(timeout=min(max(self.config.request_timeout, 8), 15))
        location_query = _normalise(params.location)
        remote_requested = "remote" in location_query
        spain_requested = any(token in location_query for token in ("spain", "españa", "madrid"))

        jobs: list[Job] = []
        for row in rows:
            if not _matches_term(row, params.search_term):
                continue
            candidate = parse_arbeitnow_job(row)
            if not candidate:
                continue
            loc = _normalise(row.get("location"))
            if spain_requested and not (
                candidate.location.is_remote or "spain" in loc or "españa" in loc or "madrid" in loc
            ):
                continue
            if remote_requested and not candidate.location.is_remote:
                continue
            jobs.append(candidate)
            if len(jobs) >= params.results_wanted:
                break

        log.info(
            "Arbeitnow returned %s matching postings for %r in %s",
            len(jobs), params.search_term, params.location,
        )
        return jobs
