"""Small live Jobicy quality audit across synthetic professional profiles."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from job_scout.config import ScrapingConfig
from job_scout.models import ScrapeParams
from job_scout.scrapers.jobicy import JobicyScraper
from jobscout_links import score_job, professional_domain_mismatch

PROFILES = [
    ("Economics graduate", "Economics graduate and master's student in Decision Systems Engineering. Econometrics, statistics, decision analysis, Excel, basic R, beginner Python, learning SQL.", "Data Analyst Intern", "Madrid, Spain"),
    ("Economics graduate remote", "Economics graduate, statistics, econometrics, forecasting, operations research, SQL basics, Python beginner.", "Business Analyst Intern", "Remote, Europe"),
    ("Software engineer", "Backend software engineer with Python, Java, PostgreSQL, Docker, AWS, APIs and testing.", "Backend Engineer", "Remote, Europe"),
    ("HR specialist", "Human resources specialist. Recruitment, talent acquisition, onboarding, HRIS, employee relations.", "HR Specialist", "Remote, Europe"),
    ("UX designer", "UX designer with Figma, user research, interaction design, prototyping, usability testing and accessibility.", "UX Designer", "Remote, Europe"),
    ("Financial analyst", "Financial analyst with financial modelling, budgeting, valuation, forecasting, Excel and accounting.", "Financial Analyst", "Remote, Europe"),
    ("Hydrogeologist", "Hydrogeologist with groundwater modelling, aquifer assessment, hydrogeology, GIS and environmental impact assessment.", "Hydrogeologist", "Spain"),
]

def main():
    scraper=JobicyScraper(ScrapingConfig(request_timeout=15))
    total=0
    failures=[]
    for label,cv,target,location in PROFILES:
        params=ScrapeParams(search_term=target,location=location,results_wanted=10,hours_old=720,include_unknown_dates=False)
        try:
            jobs=scraper.scrape(params)
        except Exception as exc:
            print(f"{label} | ERROR {type(exc).__name__}: {exc}")
            failures.append(label)
            continue
        config={"profile":{"target_title":target,"keywords":{},"title_signals":[]},"search":{"terms":[target]}}
        jobs.sort(key=lambda j: score_job({
            "title":j.title,"company":j.company,"description":j.description,
            "location":j.location.display,"job_url":j.url
        },config,cv),reverse=True)
        print(f"\n{label} | {target} | {location} | {len(jobs)} matches")
        for rank,job in enumerate(jobs[:5],1):
            row={"title":job.title,"company":job.company,"description":job.description,"location":job.location.display}
            score=score_job(row,config,cv)
            mismatch=professional_domain_mismatch(row,config,cv)
            print(f" {rank}. {score:3}/100 | {job.title} — {job.company} | {job.location.display} | {job.date_posted} | {job.job_type} | domain_mismatch={bool(mismatch)} | {job.url}")
            if "intern" in target.casefold() and any(x.value in {"full_time","contract"} for x in job.job_type) and not any(x.value=="internship" for x in job.job_type):
                failures.append(f"{label}: non-internship {job.title}")
            total+=1
    print(f"\nSUMMARY: {total} live listings inspected; issues={len(failures)}")
    for item in failures: print("ISSUE:",item)
    if failures: raise SystemExit(1)

if __name__=="__main__": main()
