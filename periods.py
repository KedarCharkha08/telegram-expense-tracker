"""Date-range logic for the dashboard filters.

Kept out of dashboard.py so it can be unit tested: importing dashboard.py
executes the whole Streamlit app, which makes its internals untestable.
"""

from __future__ import annotations

from datetime import date, timedelta

# Ordered shortest-to-longest so the control reads like a zoom level.
PERIODS = ["This month", "30 days", "3 months", "This year", "All", "Custom"]
DEFAULT_PERIOD = "This month"


def resolve_period(period: str, today: date, earliest: date) -> tuple[date, date]:
    """Turn a preset name into an inclusive [start, end] pair."""
    if period == "This month":
        return today.replace(day=1), today
    if period == "30 days":
        return today - timedelta(days=29), today
    if period == "3 months":
        return today - timedelta(days=89), today
    if period == "This year":
        return date(today.year, 1, 1), today
    return earliest, today  # "All"


def custom_bounds(today: date, earliest: date) -> tuple[date, date, date]:
    """(default_start, floor, ceiling) for the custom date picker.

    The floor must sit at or below the default start, otherwise Streamlit
    rejects its own initial value and the Custom tab raises. `earliest` alone
    is not safe: with a single recent expense it lands after the start of the
    current month.
    """
    default_start = today.replace(day=1)
    return default_start, min(earliest, default_start), today


def coerce_range(picked, fallback: tuple[date, date]) -> tuple[date, date]:
    """Normalise whatever st.date_input hands back into (start, end).

    Between the two clicks of a range selection it returns a 1-tuple; treat
    that as a single day rather than blanking the page mid-selection.
    """
    if isinstance(picked, (tuple, list)):
        if not picked:
            return fallback
        start = picked[0]
        end = picked[1] if len(picked) > 1 else picked[0]
    elif isinstance(picked, date):
        start = end = picked
    else:
        return fallback
    return (start, end) if start <= end else (end, start)
