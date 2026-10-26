import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from job_scout.scrapers.google import _resolve_job_url


def test_google_redirect_unwraps_to_the_real_posting():
    url = "https://www.google.com/url?q=https%3A%2F%2Fwww.linkedin.com%2Fjobs%2Fview%2F123456789"
    assert _resolve_job_url(url) == "https://www.linkedin.com/jobs/view/123456789"


def test_google_search_results_are_not_treated_as_a_job():
    assert _resolve_job_url("https://www.google.com/search?q=Data%20Analyst") is None


def test_google_rejects_empty_and_non_http_links():
    assert _resolve_job_url("") is None
    assert _resolve_job_url("javascript:alert(1)") is None
