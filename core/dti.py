"""Monthly debt-to-income calculations from classified statement transactions."""

from datetime import date
from decimal import Decimal
from typing import Literal, TypedDict

from sqlalchemy import Connection, Date, bindparam, text

DTI_TARGET_PERCENT = Decimal("45")
DTI_WARNING_PERCENT = Decimal("35")
CENT = Decimal("0.01")


class DTIResult(TypedDict):
    gross_income: Decimal
    monthly_debt_payments: Decimal
    ratio_percent: Decimal | None
    target_percent: Decimal
    status: Literal["safe", "moderate", "high_risk", "unavailable"]


def calculate_dti(
    gross_income: Decimal | int | str,
    monthly_debt_payments: Decimal | int | str,
) -> DTIResult:
    """Calculate DTI percentage and its standard status for non-negative amounts."""
    income = Decimal(str(gross_income))
    debt = Decimal(str(monthly_debt_payments))
    if not income.is_finite() or not debt.is_finite():
        raise ValueError("DTI amounts must be finite numbers.")
    if income < 0 or debt < 0:
        raise ValueError("DTI amounts cannot be negative.")
    income = income.quantize(CENT)
    debt = debt.quantize(CENT)

    if income == 0:
        return {
            "gross_income": income,
            "monthly_debt_payments": debt,
            "ratio_percent": None,
            "target_percent": DTI_TARGET_PERCENT,
            "status": "unavailable",
        }

    ratio = debt / income * Decimal("100")
    if ratio < DTI_WARNING_PERCENT:
        status: Literal["safe", "moderate", "high_risk", "unavailable"] = "safe"
    elif ratio <= DTI_TARGET_PERCENT:
        status = "moderate"
    else:
        status = "high_risk"

    return {
        "gross_income": income,
        "monthly_debt_payments": debt,
        "ratio_percent": ratio,
        "target_percent": DTI_TARGET_PERCENT,
        "status": status,
    }


def monthly_dti(conn: Connection, month: date) -> DTIResult:
    """Return current-month DTI; income transfers are excluded by category kind."""
    month_start = date(month.year, month.month, 1)
    next_month = (
        date(month.year + 1, 1, 1)
        if month.month == 12
        else date(month.year, month.month + 1, 1)
    )
    row = conn.execute(
        text(
            "WITH RECURSIVE debt_categories(id) AS ("
            "  SELECT id FROM categories "
            "  WHERE name = :debt_category AND kind = 'expense' "
            "    AND is_active IS TRUE AND parent_id IS NULL "
            "  UNION ALL "
            "  SELECT child.id FROM categories child "
            "  JOIN debt_categories parent ON child.parent_id = parent.id "
            "  WHERE child.kind = 'expense' AND child.is_active IS TRUE"
            ") "
            "SELECT "
            "COALESCE(SUM(CASE WHEN c.kind = 'income' AND t.amount > 0 "
            "THEN t.amount ELSE 0 END), 0) AS gross_income, "
            "COALESCE(SUM(CASE WHEN debt_categories.id IS NOT NULL AND t.amount < 0 "
            "THEN -t.amount ELSE 0 END), 0) AS debt_payments "
            "FROM transactions t "
            "JOIN categories c ON c.id = t.category_id "
            "LEFT JOIN debt_categories ON debt_categories.id = c.id "
            "WHERE t.txn_date >= :month_start AND t.txn_date < :next_month"
        ).bindparams(
            bindparam("month_start", type_=Date()),
            bindparam("next_month", type_=Date()),
        ),
        {
            "debt_category": "Зээлийн төлбөр",
            "month_start": month_start,
            "next_month": next_month,
        },
    ).one()
    return calculate_dti(
        Decimal(str(row.gross_income)),
        Decimal(str(row.debt_payments)),
    )
