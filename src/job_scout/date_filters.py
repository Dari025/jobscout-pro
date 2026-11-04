"""Publication-date filters shared by all job sources."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from math import ceil
from typing import TypeVar

T = TypeVar("T")


def filter_jobs_by_age(
    jobs: Iterable[T],
    *,
    hours_old: int,
    include_unknown_dates: bool = True,
    today: date | None = None,
) -> list[T]:
    """Apply one consistent publication window to any scraper's Job objects.

    Scrapers use date-only source fields, so the cutoff is rounded up to whole
    days. A non-positive window means no age restriction.
    """
    items = list(jobs)
    if hours_old <= 0:
        return items
    cutoff_days = max(1, ceil(int(hours_old) / 24))
    cutoff = (today or date.today()) - timedelta(days=cutoff_days)
    return [
        item for item in items
        if (
            item.date_posted is not None and item.date_posted >= cutoff
        ) or (
            item.date_posted is None and include_unknown_dates
        )
    ]
