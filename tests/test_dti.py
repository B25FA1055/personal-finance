from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from core.classifier import Ctx, Rule, classify
from core.dti import calculate_dti, monthly_dti
from core.seed import SEED_RULES


@pytest.mark.parametrize(
    ("payments", "income", "expected_status", "expected_ratio"),
    [
        ("3499", "10000", "safe", Decimal("34.99")),
        ("3500", "10000", "moderate", Decimal("35")),
        ("4500", "10000", "moderate", Decimal("45")),
        ("4501", "10000", "high_risk", Decimal("45.01")),
    ],
)
def test_dti_thresholds(payments, income, expected_status, expected_ratio) -> None:
    result = calculate_dti(Decimal(income), Decimal(payments))
    assert result["status"] == expected_status
    assert result["ratio_percent"] == expected_ratio


def test_dti_unavailable_without_gross_income() -> None:
    result = calculate_dti(Decimal("0"), Decimal("500"))
    assert result["status"] == "unavailable"
    assert result["ratio_percent"] is None


@pytest.mark.parametrize(
    ("description", "counterparty", "merchant"),
    [
        ("LOAN REPAYMENT", "", ""),
        ("ЛИЗИНГИЙН ТӨЛБӨР", "", ""),
        ("", "MORTGAGE REPAYMENT", ""),
        ("", "", "CREDIT CARD PAYMENT"),
    ],
)
def test_seeded_debt_rules_classify_common_obligations(
    description, counterparty, merchant
) -> None:
    debt_rules = [
        Rule(index, rule_field, match, pattern, direction, 77, priority)
        for index, (pattern, rule_field, match, direction, category, priority) in enumerate(
            SEED_RULES, start=1
        )
        if category == "Зээлийн төлбөр"
    ]
    context = Ctx(debt_rules, set(), {}, None)
    transaction = {
        "description": description,
        "counterparty": counterparty,
        "merchant": merchant,
        "amount": Decimal("-1000"),
        "txn_type": "other",
    }
    assert classify(transaction, context) == (77, "rule")


def test_monthly_dti_uses_income_and_debt_category_and_excludes_transfers() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT, kind TEXT, "
                "is_active BOOLEAN, parent_id INTEGER)"
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
                "INSERT INTO categories (id, name, kind, is_active, parent_id) VALUES "
                "(1, 'Өөрийн орлого', 'income', TRUE, NULL), "
                "(2, 'Зээлийн төлбөр', 'expense', TRUE, NULL), "
                "(3, 'Зээлийн карт', 'expense', TRUE, 2), "
                "(4, 'Дотоод шилжүүлэг', 'transfer', TRUE, NULL), "
                "(5, 'Хоол хүнс', 'expense', TRUE, NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO transactions (id, category_id, txn_date, amount) VALUES "
                "(1, 1, '2026-05-02', 10000), "
                "(2, 2, '2026-05-04', -2000), "
                "(3, 3, '2026-05-12', -1000), "
                "(4, 4, '2026-05-15', 5000), "
                "(5, 5, '2026-05-16', -3000), "
                "(6, 1, '2026-04-30', 9000), "
                "(7, 2, '2026-06-01', -4000)"
            )
        )

        result = monthly_dti(conn, date(2026, 5, 22))

    assert result["gross_income"] == Decimal("10000.00")
    assert result["monthly_debt_payments"] == Decimal("3000.00")
    assert result["ratio_percent"] == Decimal("30")
    assert result["status"] == "safe"
    engine.dispose()


def test_monthly_dti_works_without_debt_category_or_income() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT, kind TEXT, "
                "is_active BOOLEAN, parent_id INTEGER)"
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
                "INSERT INTO categories (id, name, kind, is_active, parent_id) "
                "VALUES (1, 'Хоол хүнс', 'expense', TRUE, NULL)"
            )
        )
        result = monthly_dti(conn, date(2026, 5, 1))

    assert result["status"] == "unavailable"
    assert result["gross_income"] == Decimal("0.00")
    assert result["monthly_debt_payments"] == Decimal("0.00")
    engine.dispose()
