import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from job_scout.cli import quick_search_scope


def test_quick_scope_prioritizes_relevant_sources_and_limits_query_volume():
    sites = ["linkedin", "indeed", "google", "glassdoor", "ziprecruiter"]
    terms = [f"term-{index}" for index in range(8)]
    locations = ["Madrid, Spain", "Remote, Europe", "Barcelona, Spain"]

    quick_sites, quick_terms, quick_locations = quick_search_scope(sites, terms, locations)

    assert quick_sites == ["google", "linkedin", "indeed"]
    assert quick_terms == terms[:4]
    assert quick_locations == locations[:2]
    # The caller's full-scan configuration is left untouched.
    assert len(sites) == 5
    assert len(terms) == 8
    assert len(locations) == 3


def test_quick_scope_falls_back_to_configured_sources_when_preferred_sites_missing():
    sites, terms, locations = quick_search_scope(
        ["bayt", "glassdoor", "ziprecruiter"],
        ["one", "two", "three", "four", "five"],
        ["Madrid", "Remote Europe", "Barcelona"],
    )

    assert sites == ["bayt", "glassdoor", "ziprecruiter"]
    assert terms == ["one", "two", "three", "four"]
    assert locations == ["Madrid", "Remote Europe"]


def test_quick_scope_respects_explicit_single_site():
    sites, terms, locations = quick_search_scope(
        ["indeed"], ["Data Analyst"], ["Madrid, Spain"]
    )
    assert sites == ["indeed"]
    assert terms == ["Data Analyst"]
    assert locations == ["Madrid, Spain"]
