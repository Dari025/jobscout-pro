"""Live source audit: public job listings, parser links and first ranked results.

Uses small personal-search requests only. It does not save postings to the user's
existing database or print full CV text.
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from jobscout_links import score_job, professional_domain_mismatch, is_specific_job_url
from job_scout.config import ScrapingConfig
from job_scout.models import ScrapeParams
from job_scout.scrapers.freehire import FreehireScraper
from job_scout.scrapers.arbeitnow import ArbeitnowScraper

SCENARIOS = [
    ("Decision Science & Data Analytics Intern",
     "Economics graduate and master's student in Decision Systems Engineering. Training in statistics, econometrics, decision analysis, operations research and quantitative modelling. Basic R, beginner Python, learning SQL. Interested in data analytics, business analytics, product analytics, risk, operations research and decision science internships or part-time junior roles.",
     ["Decision Science Intern", "Data Analyst Intern", "Business Analyst Intern", "Risk Analyst Intern"]),
    ("Hydrogeologist",
     "Hydrogeologist and geologist with groundwater, aquifer modelling, hydrogeology, geological mapping, GIS, environmental assessment and field studies.",
     ["Hydrogeologist", "Groundwater Specialist"]),
    ("Financial Analyst",
     "Financial analyst with financial modelling, Excel, budgeting, forecasting, valuation, accounting and investment analysis.",
     ["Financial Analyst", "Investment Analyst"]),
    ("Software Engineer",
     "Software engineer experienced in backend engineering, Python, Java, APIs, databases, cloud and testing.",
     ["Software Engineer", "Backend Engineer"]),
    ("Environmental Scientist",
     "Environmental scientist experienced in ecology, biodiversity, environmental impact assessment, GIS, conservation and water quality.",
     ["Environmental Scientist", "Environmental Consultant"]),
    ("HR Specialist",
     "Human resources specialist with recruitment, talent acquisition, onboarding, payroll, HRIS and employee relations.",
     ["HR Specialist", "Talent Acquisition Specialist"]),
    ("Customer Support",
     "Customer support specialist with CRM, Zendesk, ticket handling, customer care, troubleshooting and English and Spanish.",
     ["Customer Support Specialist", "Customer Success Specialist"]),
]


def config(target, cv):
    return {
        "profile": {
            "target_title": target,
            "resume_text": cv,
            "keywords": {"critical": [], "strong": [], "moderate": [], "weak": []},
            "title_signals": [],
        },
        "search": {"terms": [target]},
    }


def main():
    scraping = ScrapingConfig(
        delay_min_seconds=0, delay_max_seconds=0,
        request_timeout=12, max_retries=0, max_pages=1,
        fetch_descriptions=False, max_workers=2,
    )
    sources = {
        "Freehire": FreehireScraper(scraping),
        "Arbeitnow": ArbeitnowScraper(scraping),
    }
    locations = ["Spain", "Remote, Europe"]
    all_rows = []
    for profile_name, cv, titles in SCENARIOS:
        for target in titles:
            cfg = config(target, cv)
            for location in locations:
                for source_name, scraper in sources.items():
                    try:
                        params = ScrapeParams(
                            search_term=target, location=location,
                            results_wanted=8, hours_old=720,
                        )
                        jobs = scraper.scrape(params)
                        ranked = []
                        for j in jobs:
                            row = {
                                "title": j.title, "company": j.company,
                                "description": j.description or "",
                                "location": j.location.display,
                                "job_url": j.url, "source": source_name,
                                "date_posted": str(j.date_posted or ""),
                                "job_type": " ".join(str(x.value if hasattr(x, "value") else x) for x in j.job_type),
                            }
                            row["score"] = score_job(row, cfg, cv)
                            row["mismatch"] = professional_domain_mismatch(row, cfg, cv)
                            row["valid_url"] = is_specific_job_url(j.url)
                            ranked.append(row)
                        ranked.sort(key=lambda r: (-r["score"], r["title"].casefold()))
                        print(f"\nPROFILE={profile_name} | TARGET={target} | LOCATION={location} | SOURCE={source_name} | RAW={len(jobs)}")
                        if not ranked:
                            print("  NO RESULTS")
                        for rank, row in enumerate(ranked[:5], 1):
                            print(
                                f"  {rank}. {row['score']:3}/100 | {row['title']} — {row['company']} "
                                f"| {row['location']} | date={row['date_posted']} "
                                f"| url={'OK' if row['valid_url'] else 'BAD'} "
                                f"| mismatch={'YES' if row['mismatch'] else 'no'} | {row['job_url']}"
                            )
                            all_rows.append((profile_name, target, location, source_name, rank, row))
                    except Exception as exc:
                        print(f"\nPROFILE={profile_name} | TARGET={target} | LOCATION={location} | SOURCE={source_name} | ERROR={type(exc).__name__}: {exc}")
    print("\nSUMMARY")
    print("rows in top 5:", len(all_rows))
    print("invalid specific URLs in top 5:", sum(not row["valid_url"] for *_, row in all_rows))
    print("mismatches still in top 5:", sum(row["mismatch"] is not None for *_, row in all_rows))
    print("sources:", dict(Counter(x[3] for x in all_rows)))


if __name__ == "__main__":
    main()
