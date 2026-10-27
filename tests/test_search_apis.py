import sys
from datetime import date
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from job_scout.models import JobType, Site
from job_scout.scrapers.arbeitnow import _matches_term, parse_arbeitnow_job
from job_scout.scrapers.freehire import (
    _seniority_params,
    _validate_search_metadata,
    parse_freehire_job,
)
from job_scout.role_terms import role_matches_text, role_search_variants
from job_scout.scrapers.indeed import IndeedScraper
from job_scout.config import ScrapingConfig


def test_freehire_parser_keeps_the_original_employer_application_link():
    raw = {
        "public_slug": "junior-data-analyst-acme-123",
        "title": "Junior Data Analyst",
        "company": "Acme",
        "url": "https://boards.greenhouse.io/acme/jobs/123",
        "location": "Madrid, Spain",
        "cities": ["Madrid"],
        "countries": ["ES"],
        "regions": ["eu"],
        "work_mode": "onsite",
        "posted_at": "2026-10-20T00:00:00Z",
        "description": "Analyse product metrics and build dashboards.",
        "enrichment": {
            "employment_type": "full_time",
            "salary_min": 30000,
            "salary_max": 40000,
            "salary_currency": "EUR",
            "salary_period": "year",
        },
    }

    job = parse_freehire_job(raw)

    assert job is not None
    assert job.source is Site.FREEHIRE
    assert job.title == "Junior Data Analyst"
    assert job.company == "Acme"
    assert job.url == "https://boards.greenhouse.io/acme/jobs/123"
    assert job.location.country == "ES"
    assert job.location.city == "Madrid"
    assert job.date_posted == date(2026, 10, 20)
    assert job.compensation is not None
    assert job.compensation.min_amount == 30000
    assert job.compensation.max_amount == 40000


def test_freehire_uses_a_specific_catalogue_page_only_when_ats_url_missing():
    job = parse_freehire_job({
        "public_slug": "junior-analyst-42",
        "title": "Junior Analyst",
        "company": "Example",
        "url": "https://boards.greenhouse.io/",
        "location": "Spain",
        "description": "Analysis role",
    })

    assert job is not None
    assert job.url == "https://freehire.me/jobs/junior-analyst-42"
    assert "/jobs/junior-analyst-42" in job.url


def test_freehire_rejects_records_without_identity_fields():
    assert parse_freehire_job({"title": "Analyst", "company": "Example"}) is None
    assert parse_freehire_job({"public_slug": "x", "company": "Example"}) is None


def test_arbeitnow_parser_keeps_the_specific_listing_url_and_remote_status():
    raw = {
        "slug": "remote-data-analyst-123",
        "title": "Data Analyst",
        "company_name": "Example GmbH",
        "url": "https://www.arbeitnow.com/jobs/companies/example/remote-data-analyst-123",
        "description": "<p>Analyse customer and financial data.</p>",
        "remote": True,
        "location": "Remote",
        "tags": ["Data", "Analytics"],
        "job_types": ["Working student", "Part-time"],
        "created_at": 1780000000,
    }

    job = parse_arbeitnow_job(raw)

    assert job is not None
    assert job.source is Site.ARBEITNOW
    assert job.url == raw["url"]
    assert job.company == "Example GmbH"
    assert job.location.is_remote is True
    assert JobType.PART_TIME in job.job_type
    assert job.description
    assert job.date_posted is not None


def test_arbeitnow_rejects_generic_or_missing_posting_urls():
    raw = {
        "slug": "missing-url",
        "title": "Data Analyst",
        "company_name": "Example GmbH",
        "url": "https://www.arbeitnow.com/",
    }
    assert parse_arbeitnow_job(raw) is None


def test_indeed_parser_builds_the_correct_country_specific_job_link():
    scraper = IndeedScraper(ScrapingConfig())
    job = {
        "key": "abc123",
        "title": "Data Analyst",
        "employer": {"name": "Example"},
        "location": {"city": "Madrid", "countryCode": "ES"},
        "description": {"html": "<p>Reporting</p>"},
    }

    result = scraper._parse_job(job, set(), country_code="ES")

    assert result is not None
    assert result.url == "https://es.indeed.com/viewjob?jk=abc123"
    assert result.location.country == "ES"


def test_freehire_fails_closed_when_country_filter_is_ignored():
    payload = {
        "meta": {
            "ignored_params": [
                {"param": "countries", "value": "ES", "reason": "unknown facet"}
            ]
        }
    }

    import pytest

    with pytest.raises(RuntimeError, match="ignored required geographic filter"):
        _validate_search_metadata(payload, "Madrid, Spain")


def test_freehire_fails_closed_when_remote_region_filter_is_ignored():
    payload = {"meta": {"ignored_params": ["work_mode"]}}

    import pytest

    with pytest.raises(RuntimeError, match="work_mode"):
        _validate_search_metadata(payload, "Remote, Europe")


def test_freehire_warns_but_allows_non_geographic_ignored_params():
    payload = {"meta": {"ignored_params": ["seniority_include_unspecified"]}}
    _validate_search_metadata(payload, "Madrid, Spain")



def test_freehire_does_not_force_junior_seniority_for_general_searches():
    assert _seniority_params("Hydrogeologist") == {}
    assert _seniority_params("Geologist") == {}
    assert _seniority_params("Senior Geologist") == {}


def test_freehire_only_filters_seniority_when_the_user_requests_it():
    assert _seniority_params("Junior Geologist") == {
        "seniority": "intern,junior",
        "seniority_include_unspecified": "true",
    }
    assert _seniority_params("Data Analyst Internship")["seniority"] == "intern,junior"


def test_geoscience_search_variants_include_related_role_terms():
    hydro = {term.casefold() for term in role_search_variants("Hydrogeologist")}
    geology = {term.casefold() for term in role_search_variants("Geologist")}
    assert {"hydrogeology", "groundwater", "geologist"} <= hydro
    assert {"geology", "geoscientist", "engineering geologist", "hydrogeologist"} <= geology


def test_geologist_search_matches_compound_hydrogeologist_title():
    assert role_matches_text("geologist", "Senior Hydrogeologist")
    assert _matches_term(
        {"title": "Hydrogeologist", "tags": []},
        "geologist",
    )


def test_hydrogeologist_search_matches_groundwater_role_title():
    assert role_matches_text("hydrogeologist", "Groundwater Specialist")
    assert _matches_term(
        {"title": "Groundwater Specialist", "tags": []},
        "hydrogeologist",
    )
