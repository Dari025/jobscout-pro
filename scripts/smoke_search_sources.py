"""Non-blocking live smoke test for the public job search providers.

This runs in GitHub Actions to distinguish parser/unit-test success from provider
availability. It prints counts and checks that returned records have specific URLs.
"""
from __future__ import annotations

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


def main() -> int:
    results = {}
    with httpx.Client(
        timeout=httpx.Timeout(15.0, connect=8.0),
        follow_redirects=True,
        headers=HEADERS,
    ) as client:
        results["Freehire"] = probe_freehire(client)
        results["Arbeitnow"] = probe_arbeitnow(client)

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
