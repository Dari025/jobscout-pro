from unittest.mock import Mock, patch

from job_scout.scrapers.jobicy import _FEED_CACHE, _load_feed


def test_jobicy_persistent_cache_survives_a_new_scraper_process(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBSCOUT_CACHE_DIR", str(tmp_path))
    _FEED_CACHE.clear()
    response = Mock(status_code=200)
    response.json.return_value = {
        "success": True,
        "jobs": [{
            "id": 123,
            "url": "https://jobicy.com/jobs/123-data-analyst",
            "jobTitle": "Data Analyst",
            "companyName": "Example Ltd",
            "jobGeo": "Spain",
        }],
    }
    with patch("job_scout.scrapers.jobicy.httpx.get", return_value=response) as request:
        assert len(_load_feed("europe", 10)) == 1
    request.assert_called_once()

    # A new process has no in-memory cache; the persisted public feed avoids
    # a second API call until the one-hour refresh window expires.
    _FEED_CACHE.clear()
    with patch("job_scout.scrapers.jobicy.httpx.get", side_effect=AssertionError("cache miss")):
        assert len(_load_feed("europe", 10)) == 1
    assert (tmp_path / "jobicy_europe.json").exists()
