from datetime import date

import pytest

from periods import PERIODS, coerce_range, custom_bounds, resolve_period

TODAY = date(2026, 8, 9)
EARLIEST = date(2026, 5, 12)


@pytest.mark.parametrize(
    "period,start,days",
    [
        ("This month", date(2026, 8, 1), 9),
        ("30 days", date(2026, 7, 11), 30),
        ("3 months", date(2026, 5, 12), 90),
        ("This year", date(2026, 1, 1), 221),
        ("All", EARLIEST, 90),
    ],
)
def test_presets(period, start, days):
    got_start, got_end = resolve_period(period, TODAY, EARLIEST)
    assert got_start == start
    assert got_end == TODAY
    assert (got_end - got_start).days + 1 == days


def test_every_preset_is_resolvable():
    for period in PERIODS:
        if period == "Custom":
            continue
        start, end = resolve_period(period, TODAY, EARLIEST)
        assert start <= end


def test_custom_floor_never_exceeds_the_default_start():
    """The regression: one recent expense pushed the floor past the default.

    Streamlit raises when date_input's value falls outside min_value, so this
    made the Custom tab crash whenever all data was newer than the 1st.
    """
    only_today = TODAY
    default_start, floor, ceiling = custom_bounds(TODAY, only_today)
    assert floor <= default_start <= ceiling


def test_custom_floor_uses_earliest_when_data_is_older():
    default_start, floor, _ = custom_bounds(TODAY, EARLIEST)
    assert floor == EARLIEST
    assert floor < default_start


def test_custom_bounds_on_an_empty_looking_first_day_of_month():
    first = date(2026, 8, 1)
    default_start, floor, ceiling = custom_bounds(first, first)
    assert floor == default_start == ceiling == first


FALLBACK = (date(2026, 8, 1), TODAY)


def test_coerce_full_range():
    assert coerce_range((date(2026, 7, 1), date(2026, 7, 9)), FALLBACK) == (
        date(2026, 7, 1),
        date(2026, 7, 9),
    )


def test_coerce_half_picked_range_becomes_one_day():
    assert coerce_range((date(2026, 7, 4),), FALLBACK) == (
        date(2026, 7, 4),
        date(2026, 7, 4),
    )


def test_coerce_bare_date():
    assert coerce_range(date(2026, 7, 4), FALLBACK) == (date(2026, 7, 4), date(2026, 7, 4))


def test_coerce_empty_falls_back():
    assert coerce_range((), FALLBACK) == FALLBACK
    assert coerce_range(None, FALLBACK) == FALLBACK


def test_coerce_reversed_range_is_ordered():
    assert coerce_range((date(2026, 7, 9), date(2026, 7, 1)), FALLBACK) == (
        date(2026, 7, 1),
        date(2026, 7, 9),
    )
