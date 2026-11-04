from datetime import date, timedelta
from types import SimpleNamespace

from job_scout.date_filters import filter_jobs_by_age


def job(posted):
    return SimpleNamespace(date_posted=posted)


def test_recent_job_filter_keeps_only_jobs_in_window():
    today = date(2026, 11, 4)
    rows = [job(today), job(today - timedelta(days=30)), job(today - timedelta(days=31)), job(None)]
    kept = filter_jobs_by_age(rows, hours_old=720, today=today)
    assert kept == rows[:2] + [rows[3]]


def test_unknown_publication_dates_are_controlled_by_user_setting():
    today = date(2026, 11, 4)
    rows = [job(today), job(None)]
    assert filter_jobs_by_age(rows, hours_old=168, include_unknown_dates=False, today=today) == rows[:1]
    assert filter_jobs_by_age(rows, hours_old=168, include_unknown_dates=True, today=today) == rows


def test_any_date_setting_does_not_drop_old_or_undated_jobs():
    today = date(2026, 11, 4)
    rows = [job(today - timedelta(days=500)), job(None)]
    assert filter_jobs_by_age(rows, hours_old=0, include_unknown_dates=False, today=today) == rows
