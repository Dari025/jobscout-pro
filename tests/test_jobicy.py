from datetime import date, timedelta
from unittest.mock import Mock, patch

from job_scout.config import ScrapingConfig
from job_scout.models import JobType, ScrapeParams, Site
from job_scout.scrapers.jobicy import (
    _FEED_CACHE,
    JobicyScraper,
    _geo_slug,
    _location_matches,
    _matches_title,
    parse_jobicy_job,
)


def sample_job(**overrides):
    raw = {
        "id": 123,
        "url": "https://jobicy.com/jobs/123-data-analyst",
        "jobTitle": "Data Analyst",
        "companyName": "Example Ltd",
        "jobIndustry": ["Data Science & Analytics"],
        "jobType": ["Part-Time", "Internship"],
        "jobGeo": "Spain, Portugal",
        "jobLevel": "Junior",
        "jobExcerpt": "Analyse business data",
        "jobDescription": "<p>Analyse <b>business</b> data.</p><script>bad()</script>",
        "pubDate": "2026-11-03T09:00:00+00:00",
        "salaryMin": 25000,
        "salaryMax": 32000,
        "salaryCurrency": "EUR",
        "salaryPeriod": "yearly",
    }
    raw.update(overrides)
    return raw


def test_jobicy_parser_maps_original_link_salary_contract_and_description():
    job = parse_jobicy_job(sample_job())
    assert job is not None
    assert job.source is Site.JOBICY
    assert job.source_id == "123"
    assert job.url == "https://jobicy.com/jobs/123-data-analyst"
    assert job.title == "Data Analyst"
    assert job.job_type == [JobType.PART_TIME, JobType.INTERNSHIP]
    assert job.compensation is not None
    assert job.compensation.min_amount == 25000
    assert job.compensation.currency == "EUR"
    assert "Analyse business data." in job.description
    assert "bad()" not in job.description


def test_jobicy_parser_rejects_missing_identity_or_noncanonical_link():
    assert parse_jobicy_job(sample_job(url="https://example.com/job/123")) is None
    assert parse_jobicy_job(sample_job(id=None)) is None


def test_jobicy_parses_missing_date_and_salary_safely():
    job = parse_jobicy_job(sample_job(pubDate="", salaryMin=None, salaryMax=None))
    assert job is not None
    assert job.date_posted is None
    assert job.compensation is None


def test_jobicy_geography_slugs_and_eligibility():
    assert _geo_slug("Madrid, Spain") == "spain"
    assert _geo_slug("Remote, Europe") == "europe"
    assert _geo_slug("Remote, Worldwide") == "anywhere"
    assert _location_matches("Spain, Portugal", "Madrid, Spain")
    assert _location_matches("EMEA", "Remote, Spain")
    assert _location_matches("Germany", "Remote, Europe")
    assert not _location_matches("USA", "Remote, Europe")
    assert _location_matches("USA", "Remote, United States")


def test_jobicy_title_match_requires_a_complete_role_not_one_generic_word():
    assert _matches_title("Data Analyst Intern", "Data Analyst Intern")
    assert _matches_title("Business Intelligence Analyst", "Data Analyst")
    assert not _matches_title("Director of Data Strategy", "Data Analyst")
    assert not _matches_title("ICT Security Operations Specialist", "HR Specialist")
    assert not _matches_title("Senior Data Science Intern", "Data Science Intern", job_types=["Internship"], job_level="Senior")
    assert not _matches_title(
        "Business Intelligence Analyst", "Data Analyst Intern",
        job_types=["Full-Time"], job_level="Senior",
    )
    assert _matches_title(
        "Business Intelligence Analyst", "Data Analyst Intern",
        job_types=["Internship"], job_level="Junior",
    )


def test_jobicy_scraper_filters_wrong_roles_and_locations_and_honours_dates():
    _FEED_CACHE.clear()
    today = date.today()
    rows = [
        sample_job(id=1, jobTitle="Data Analyst Intern", jobGeo="Spain",
                   pubDate=today.isoformat() + "T09:00:00+00:00"),
        sample_job(id=2, jobTitle="Director of Data Strategy", jobGeo="Spain",
                   pubDate=today.isoformat() + "T09:00:00+00:00"),
        sample_job(id=3, jobTitle="Data Analyst", jobGeo="USA",
                   pubDate=today.isoformat() + "T09:00:00+00:00"),
        sample_job(id=4, jobTitle="Data Analyst", jobGeo="Spain",
                   pubDate=(today - timedelta(days=45)).isoformat() + "T09:00:00+00:00"),
    ]
    scraper = JobicyScraper(ScrapingConfig())
    params = ScrapeParams(
        search_term="Data Analyst Intern", location="Madrid, Spain",
        results_wanted=10, hours_old=720, include_unknown_dates=False,
    )
    with patch("job_scout.scrapers.jobicy._load_feed", return_value=rows):
        jobs = scraper.scrape(params)
    assert [job.source_id for job in jobs] == ["1"]
    assert "España" in jobs[0].location.city or "Spain" in jobs[0].location.city


def test_jobicy_cache_prevents_multiple_feed_requests_within_hour(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBSCOUT_CACHE_DIR", str(tmp_path))
    _FEED_CACHE.clear()
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "jobs": [sample_job()]}
    with patch("job_scout.scrapers.jobicy.httpx.get", return_value=response) as request:
        from job_scout.scrapers.jobicy import _load_feed
        assert len(_load_feed("europe", 10)) == 1
        assert len(_load_feed("europe", 10)) == 1
    request.assert_called_once()
