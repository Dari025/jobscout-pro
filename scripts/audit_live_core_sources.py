"""Small live relevance audit for Freehire and Arbeitnow."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
for path in (ROOT,ROOT/"src"):
    if str(path) not in sys.path: sys.path.insert(0,str(path))

from job_scout.config import ScrapingConfig
from job_scout.models import ScrapeParams
from job_scout.scrapers.freehire import FreehireScraper
from job_scout.scrapers.arbeitnow import ArbeitnowScraper
from jobscout_links import score_job, professional_domain_mismatch

SCENARIOS=[
 ("Data Analyst Intern","Economics graduate; master student in Decision Systems Engineering; econometrics, statistics, Excel, basic R, beginner Python, learning SQL.","Madrid, Spain"),
 ("Business Analyst Intern","Economics graduate; quantitative analysis, decision science, business analytics, statistical modelling, Excel; beginner Python and SQL.","Remote, Europe"),
 ("Hydrogeologist","Hydrogeologist with aquifer assessment, groundwater modelling, GIS, field sampling and hydrogeology.","Spain"),
]

def main():
 cfg_scrape=ScrapingConfig(request_timeout=12,max_retries=0,max_pages=1,fetch_descriptions=False,delay_min_seconds=0,delay_max_seconds=0)
 sources={"Freehire":FreehireScraper(cfg_scrape),"Arbeitnow":ArbeitnowScraper(cfg_scrape)}
 for title,cv,location in SCENARIOS:
  config={"profile":{"target_title":title,"keywords":{},"title_signals":[]},"search":{"terms":[title]}}
  for name,scraper in sources.items():
   try:
    rows=scraper.scrape(ScrapeParams(search_term=title,location=location,results_wanted=8,hours_old=720,include_unknown_dates=False))
   except Exception as exc:
    print(f"\n{name} | {title} | ERROR {type(exc).__name__}: {exc}")
    continue
   ranked=[]
   for job in rows:
    row={"title":job.title,"company":job.company,"description":job.description,"location":job.location.display,"job_url":job.url,"source":name,"date_posted":str(job.date_posted or ""),"job_type":[value.value for value in job.job_type]}
    score=score_job(row,config,cv)
    mismatch=professional_domain_mismatch(row,config,cv)
    ranked.append((score,job,mismatch))
   ranked.sort(key=lambda x:(-x[0],x[1].title.casefold()))
   print(f"\n{name} | {title} | {location} | {len(ranked)} matches")
   for i,(score,job,mismatch) in enumerate(ranked[:5],1):
    print(f" {i}. {score:3}/100 | {job.title} — {job.company} | {job.location.display} | {job.date_posted} | mismatch={bool(mismatch)} | {job.url}")
if __name__=="__main__": main()
