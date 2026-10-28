from datetime import date
from decimal import Decimal

import pytest

from core.i18n import TEXTS
from core.recurring import FREQUENCIES, add_months, following_due, monthly_cost


@pytest.mark.parametrize(
    ("anchor", "months", "expected"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),  # leap year
        (date(2026, 1, 31), 2, date(2026, 3, 31)),
        (date(2026, 11, 15), 3, date(2027, 2, 15)),
        (date(2024, 2, 29), 12, date(2025, 2, 28)),
    ],
)
def test_add_months_clamps_to_month_end(anchor, months, expected) -> None:
    assert add_months(anchor, months) == expected


def test_monthly_schedule_does_not_drift_after_short_month() -> None:
    start = date(2026, 1, 31)
    due = start
    dates = []
    for _ in range(3):
        due = following_due(start, due, "monthly")
        dates.append(due)
    assert dates == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_weekly_and_yearly() -> None:
    assert following_due(date(2026, 10, 1), date(2026, 10, 8), "weekly") == date(2026, 10, 15)
    assert following_due(date(2026, 3, 10), date(2026, 3, 10), "yearly") == date(2027, 3, 10)


def test_monthly_cost() -> None:
    assert monthly_cost(Decimal("12000"), "monthly") == Decimal("12000.00")
    assert monthly_cost(Decimal("12000"), "yearly") == Decimal("1000.00")
    assert monthly_cost(Decimal("3000"), "weekly") == Decimal("13000.00")


def test_every_runtime_text_key_exists() -> None:
    keys = [f"freq_{f}" for f in FREQUENCIES]
    keys += [f"rec_status_{s}" for s in ("overdue", "due", "upcoming")]
    keys += [f"rec_action_{a}" for a in ("confirmed", "log", "skipped")]
    keys += [f"rec_done_{a}" for a in ("confirmed", "log", "skipped")]
    keys += [f"rec_hist_{s}" for s in ("matched", "confirmed", "logged", "skipped")]
    keys += [f"rec_invalid_{f}" for f in ("name", "amount", "frequency")]
    assert [k for k in keys if k not in TEXTS] == []
