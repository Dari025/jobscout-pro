"""Non-blocking live smoke test for the public job search providers.

This runs in GitHub Actions to distinguish parser/unit-test success from provider
availability. It prints counts and checks that returned records have specific URLs.
"""
from __future__ import annotations

from collections import Counter
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from jobscout_links import is_specific_job_url
from job_scout.scrapers.arbeitnow import API_URL as ARBEITNOW_URL, parse_arbeitnow_job
from job_scout.scrapers.freehire import API_URL as FREEHIRE_URL, parse_freehire_job

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "JobScout-Pro-source-smoke/1.0 (personal job search)",
}


def probe_freehire(client: httpx.Client) -> tuple[bool, str]:
    try:
        response = client.get(
            FREEHIRE_URL,
            params={
                "q": "Data Analyst",
                "q_fields": "title,description,company,location",
                "description_format": "text",
                "limit": 5,
                "order": "desc",
            },
        )
        print(f"Freehire HTTP {response.status_code}")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return False, "unexpected JSON response (expected object with data array)"
        rows = payload["data"]
        valid = []
        for row in rows:
            parsed = parse_freehire_job(row)
            if parsed and is_specific_job_url(parsed.url):
                valid.append(parsed)
        total = (payload.get("meta") or {}).get("total", "unknown")
        print(f"Freehire: API total={total}; returned={len(rows)}; valid postings with specific links={len(valid)}")
        if not valid:
            return False, "API returned no usable Data Analyst postings with a specific vacancy URL"
        return True, "ok"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def probe_arbeitnow(client: httpx.Client) -> tuple[bool, str]:
    try:
        response = client.get(ARBEITNOW_URL, params={"page": 1})
        print(f"Arbeitnow HTTP {response.status_code}")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return False, "unexpected JSON response (expected object with data array)"
        rows = payload["data"]
        valid = []
        for row in rows:
            parsed = parse_arbeitnow_job(row)
            if parsed and is_specific_job_url(parsed.url):
                valid.append(parsed)
        print(f"Arbeitnow: returned={len(rows)}; valid postings with specific links={len(valid)}")
        if not valid:
            return False, "API returned no usable postings with a specific vacancy URL"
        return True, "ok"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def probe_targeted_searches() -> None:
    """Run the actual scraper logic for the two locations the dashboard targets."""
    from job_scout.config import ScrapingConfig
    from job_scout.models import ScrapeParams
    from job_scout.scrapers.arbeitnow import ArbeitnowScraper
    from job_scout.scrapers.freehire import FreehireScraper

    cfg = ScrapingConfig(
        delay_min_seconds=0,
        delay_max_seconds=0,
        request_timeout=8,
        max_retries=0,
        max_pages=1,
        fetch_descriptions=False,
    )
    locations = ("Madrid, Spain", "Remote, Europe")
    freehire = FreehireScraper(cfg)
    arbeitnow = ArbeitnowScraper(cfg)
    for location in locations:
        params = ScrapeParams(
            search_term="Data Analyst",
            location=location,
            results_wanted=10,
            hours_old=720,
        )
        for label, scraper in (("Freehire", freehire), ("Arbeitnow", arbeitnow)):
            try:
                jobs = scraper.scrape(params)
                linked = sum(1 for job in jobs if is_specific_job_url(job.url))
                countries = Counter((job.location.country or "unknown").upper() for job in jobs)
                remote_count = sum(1 for job in jobs if job.location.is_remote)
                expected_geo = 0
                for job in jobs:
                    city = (job.location.city or "").casefold()
                    country = (job.location.country or "").upper()
                    if location == "Madrid, Spain":
                        if country == "ES" or city == "madrid" or job.location.is_remote:
                            expected_geo += 1
                    elif job.location.is_remote:
                        expected_geo += 1
                samples = [
                    f"{job.title} — {job.company} [{job.location.country or 'unknown'}; "
                    f"remote={job.location.is_remote}]"
                    for job in jobs[:2]
                ]
                print(
                    f"Targeted query {label} | Data Analyst | {location}: "
                    f"{len(jobs)} results, {linked} specific URLs, "
                    f"{remote_count} remote, countries={dict(countries)}, "
                    f"geography_matches={expected_geo}; samples={samples}"
                )
            except Exception as exc:
                print(
                    f"Targeted query WARNING {label} | Data Analyst | {location}: "
                    f"{type(exc).__name__}: {exc}"
                )


def main() -> int:
    results = {}
    with httpx.Client(
        timeout=httpx.Timeout(15.0, connect=8.0),
        follow_redirects=True,
        headers=HEADERS,
    ) as client:
        results["Freehire"] = probe_freehire(client)
        results["Arbeitnow"] = probe_arbeitnow(client)

    # Connectivity and payload checks alone are not enough: exercise the same
    # source adapters/region filters used by the deployed search button as well.
    probe_targeted_searches()

    failed = False
    for provider, (ok, detail) in results.items():
        status = "PASS" if ok else "WARNING"
        print(f"{status} {provider}: {detail}")
        if not ok:
            failed = True
    # This workflow is explicitly non-blocking, but a non-zero exit makes the
    # provider problem visible in its logs/check annotations.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
