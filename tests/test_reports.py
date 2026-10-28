from datetime import date

import pytest

from core.reports import PRESETS, preset_range

TODAY = date(2026, 10, 21)  # a Wednesday


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("last_week", (date(2026, 10, 12), date(2026, 10, 18))),
        ("this_month", (date(2026, 10, 1), TODAY)),
        ("last_30_days", (date(2026, 9, 22), TODAY)),
        ("this_year", (date(2026, 1, 1), TODAY)),
        ("all_time", (date(2026, 9, 14), TODAY)),
    ],
)
def test_preset_ranges(preset, expected) -> None:
    assert preset_range(preset, TODAY, date(2026, 9, 14)) == expected


def test_last_week_on_a_monday_and_across_new_year() -> None:
    assert preset_range("last_week", date(2026, 10, 19), None) == (date(2026, 10, 12), date(2026, 10, 18))
    assert preset_range("last_week", date(2027, 1, 2), None) == (date(2026, 12, 21), date(2026, 12, 27))


def test_all_time_without_transactions_is_today() -> None:
    assert preset_range("all_time", TODAY, None) == (TODAY, TODAY)


def test_every_preset_is_valid() -> None:
    for preset in PRESETS:
        start, end = preset_range(preset, TODAY, date(2026, 9, 14))
        assert start <= end
