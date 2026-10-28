from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from core.budget_service import (
    archive_savings_goal,
    budget_alerts,
    copy_previous_month_budgets,
    create_savings_goal,
    list_savings_goals,
    monthly_budget_progress,
    months_between,
    save_monthly_budgets,
    update_savings_goal,
)


@pytest.fixture
def budget_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT, "
                "kind TEXT, is_active BOOLEAN, parent_id INTEGER)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE category_budgets (id INTEGER PRIMARY KEY, "
                "category_id INTEGER, budget_month DATE, monthly_limit NUMERIC, "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                "UNIQUE(category_id, budget_month))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE transactions (id INTEGER PRIMARY KEY, category_id INTEGER, "
                "txn_date DATE, amount NUMERIC)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE savings_goals (id INTEGER PRIMARY KEY, name TEXT, "
                "target_amount NUMERIC, current_amount NUMERIC, deadline DATE, "
                "is_active BOOLEAN DEFAULT TRUE, goal_type TEXT DEFAULT 'other', "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO categories (id, name, kind, is_active) VALUES "
                "(1, 'Хоол хүнс', 'expense', TRUE), "
                "(2, 'Тээвэр', 'expense', TRUE), "
                "(3, 'Дотоод шилжүүлэг', 'transfer', TRUE)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO transactions (id, category_id, txn_date, amount) VALUES "
                "(1, 1, '2026-05-05', -800), "
                "(2, 1, '2026-05-20', -100), "
                "(3, 1, '2026-06-01', -500), "
                "(4, 2, '2026-05-20', -100), "
                "(5, 3, '2026-05-20', -900), "
                "(6, NULL, '2026-05-20', -50)"
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()


def test_monthly_budget_progress_and_alert_threshold(budget_db) -> None:
    with budget_db.begin() as conn:
        save_monthly_budgets(
            conn,
            date(2026, 5, 22),
            {1: Decimal("1000.00"), 2: Decimal("200.00")},
        )
        progress = monthly_budget_progress(conn, date(2026, 5, 1))

    by_category = {item["category"]: item for item in progress}
    food = by_category["Хоол хүнс"]
    assert food["spent"] == Decimal("900.00")
    assert food["remaining"] == Decimal("100.00")
    assert food["status"] == "approaching"

    transport = by_category["Тээвэр"]
    assert transport["spent"] == Decimal("100.00")
    assert transport["status"] == "within"

    unclassified = by_category["Ангилаагүй"]
    assert unclassified["spent"] == Decimal("50.00")
    assert unclassified["status"] == "unbudgeted"


def test_budget_upsert_and_remove(budget_db) -> None:
    with budget_db.begin() as conn:
        save_monthly_budgets(conn, date(2026, 5, 8), {1: Decimal("1000")})
        save_monthly_budgets(conn, date(2026, 5, 30), {1: Decimal("750.50")})
        progress = monthly_budget_progress(conn, date(2026, 5, 1))
        assert next(item for item in progress if item["category_id"] == 1)[
            "monthly_limit"
        ] == Decimal("750.50")

        save_monthly_budgets(conn, date(2026, 5, 1), {1: None})
        progress = monthly_budget_progress(conn, date(2026, 5, 1))
        assert next(item for item in progress if item["category_id"] == 1)[
            "monthly_limit"
        ] is None


def test_budget_reports_overspending(budget_db) -> None:
    with budget_db.begin() as conn:
        save_monthly_budgets(conn, date(2026, 5, 1), {1: Decimal("850")})
        food = next(
            item
            for item in monthly_budget_progress(conn, date(2026, 5, 1))
            if item["category_id"] == 1
        )

    assert food["status"] == "exceeded"
    assert food["remaining"] == Decimal("-50.00")


def test_budget_rejects_non_expense_category(budget_db) -> None:
    with budget_db.begin() as conn, pytest.raises(ValueError, match="expense"):
        save_monthly_budgets(conn, date(2026, 5, 1), {3: Decimal("100")})


def test_savings_goal_create_update_and_archive(budget_db) -> None:
    with budget_db.begin() as conn:
        goal_id = create_savings_goal(
            conn, "Emergency fund", Decimal("1000"), Decimal("250"), date(2027, 1, 1)
        )
        update_savings_goal(conn, goal_id, Decimal("400.25"))
        goals = list_savings_goals(conn)
        assert len(goals) == 1
        assert goals[0]["current_amount"] == Decimal("400.25")

        archive_savings_goal(conn, goal_id)
        assert list_savings_goals(conn) == []


def test_budget_alerts_list_exceeded_first_and_skip_on_track(budget_db) -> None:
    with budget_db.begin() as conn:
        # May: food 900/1000 (approaching), transport 100/50 (exceeded)
        save_monthly_budgets(conn, date(2026, 5, 1), {1: Decimal("1000"), 2: Decimal("50")})
        alerts = budget_alerts(conn, date(2026, 5, 1))
        assert [(a["category"], a["status"]) for a in alerts] == [
            ("Тээвэр", "exceeded"),
            ("Хоол хүнс", "approaching"),
        ]
        save_monthly_budgets(conn, date(2026, 5, 1), {1: Decimal("5000"), 2: Decimal("5000")})
        assert budget_alerts(conn, date(2026, 5, 1)) == []


def test_copy_previous_month_budgets_keeps_existing_limits(budget_db) -> None:
    with budget_db.begin() as conn:
        save_monthly_budgets(conn, date(2026, 5, 1), {1: Decimal("1000"), 2: Decimal("200")})
        save_monthly_budgets(conn, date(2026, 6, 1), {2: Decimal("300")})
        assert copy_previous_month_budgets(conn, date(2026, 6, 15)) == 1
        june = {i["category_id"]: i["monthly_limit"] for i in monthly_budget_progress(conn, date(2026, 6, 1))}
        assert june[1] == Decimal("1000.00")
        assert june[2] == Decimal("300.00")  # not overwritten
        assert copy_previous_month_budgets(conn, date(2026, 6, 1)) == 0  # idempotent


def test_months_between_spans_year_end() -> None:
    assert months_between(date(2026, 11, 14), date(2027, 1, 3)) == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
    ]
