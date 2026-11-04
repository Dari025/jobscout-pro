from job_scout.scrapers.freehire import _row_location_matches, _within_age_limit


def test_freehire_geography_filter_rejects_other_continents_for_spain_and_europe():
    north_america_remote = {
        "countries": ["US"], "regions": ["north_america"],
        "work_mode": "remote", "location": "Remote",
    }
    european_remote = {
        "countries": ["DE"], "regions": ["eu"],
        "work_mode": "remote", "location": "Remote",
    }
    spain_onsite = {
        "countries": ["ES"], "regions": ["eu"],
        "work_mode": "onsite", "location": "Madrid, Spain",
    }
    assert not _row_location_matches(north_america_remote, "Spain")
    assert not _row_location_matches(north_america_remote, "Remote, Europe")
    assert _row_location_matches(european_remote, "Remote, Europe")
    assert _row_location_matches(spain_onsite, "Madrid, Spain")


def test_freehire_remote_spain_requires_explicit_spanish_eligibility():
    assert _row_location_matches({
        "countries": ["ES"], "regions": ["eu"],
        "work_mode": "remote", "location": "Remote",
    }, "Remote, Spain")
    assert not _row_location_matches({
        "countries": ["US"], "regions": ["north_america"],
        "work_mode": "remote", "location": "Remote",
    }, "Remote, Spain")


def test_freehire_age_filter_does_not_accept_old_known_dates():
    from datetime import date, timedelta

    today = date.today()
    assert _within_age_limit(today - timedelta(days=30), 720)
    assert not _within_age_limit(today - timedelta(days=31), 720)
    assert _within_age_limit(None, 720)
