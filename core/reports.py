"""Report queries. Categories of kind 'transfer' never count as income or expense."""

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy import Connection, text

from core.classify_service import NEEDS_REVIEW

_BASE = (
    "FROM transactions t "
    "LEFT JOIN categories c ON c.id = t.category_id "
    "WHERE (c.kind IS NULL OR c.kind <> 'transfer') "
    "AND t.txn_date::date BETWEEN :start AND :end "
)


PRESETS = ("last_week", "this_month", "last_30_days", "this_year", "all_time")


def preset_range(preset: str, today: date, first_date: date | None) -> tuple[date, date]:
    """Date range for a quick filter. last_week is the previous Monday-Sunday."""
    if preset == "last_week":
        this_monday = today - timedelta(days=today.weekday())
        return this_monday - timedelta(days=7), this_monday - timedelta(days=1)
    if preset == "this_month":
        return today.replace(day=1), today
    if preset == "last_30_days":
        return today - timedelta(days=29), today
    if preset == "this_year":
        return date(today.year, 1, 1), today
    if preset == "all_time":
        return min(first_date or today, today), today
    raise ValueError(f"Unknown preset: {preset}")


def previous_period(start: date, end: date) -> tuple[date, date]:
    """The equally long period right before start..end (for change-vs-previous deltas)."""
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def period_totals(conn: Connection, start: date, end: date) -> tuple[Decimal, Decimal, int]:
    """(income, expense, transaction count) for a period, transfers excluded."""
    row = conn.execute(
        text(
            "SELECT COALESCE(SUM(t.amount) FILTER (WHERE t.amount > 0), 0) AS income, "
            "COALESCE(-SUM(t.amount) FILTER (WHERE t.amount < 0), 0) AS expense, "
            "COUNT(*) AS n " + _BASE
        ),
        {"start": start, "end": end},
    ).one()
    return Decimal(row.income), Decimal(row.expense), int(row.n)


def first_transaction_date(conn: Connection) -> date | None:
    return conn.execute(text("SELECT MIN(txn_date)::date FROM transactions")).scalar()


def import_history(conn: Connection) -> pd.DataFrame:
    return pd.read_sql(
        text(
            "SELECT i.file_name AS file, b.code AS bank, a.account_number AS account, "
            "i.period_start, i.period_end, i.rows_read, i.rows_inserted, i.imported_at "
            "FROM imports i JOIN accounts a ON a.id = i.account_id "
            "JOIN banks b ON b.id = a.bank_id "
            "ORDER BY i.imported_at DESC"
        ),
        conn,
    )


def monthly_summary(conn: Connection, start: date, end: date) -> pd.DataFrame:
    """month, income, expense, net (money as Decimal)."""
    df = pd.read_sql(
        text(
            "SELECT date_trunc('month', t.txn_date)::date AS month, "
            "COALESCE(SUM(t.amount) FILTER (WHERE t.amount > 0), 0) AS income, "
            "COALESCE(-SUM(t.amount) FILTER (WHERE t.amount < 0), 0) AS expense "
            + _BASE
            + "GROUP BY 1 ORDER BY 1"
        ),
        conn,
        params={"start": start, "end": end},
    )
    df["net"] = df["income"] - df["expense"]
    return df


def by_category(
    conn: Connection, start: date, end: date, kind: str, level: str = "main"
) -> pd.DataFrame:
    """category, total, pct, count for 'income' (amount > 0) or 'expense' (amount < 0).

    level='main' rolls subcategories up into their main category; level='sub' adds a
    'main' column and keeps each subcategory separate (for drill-down tables).
    """
    sign = ">" if kind == "income" else "<"
    main = "COALESCE(p.name, c.name, 'Unclassified')"
    columns = f"{main} AS category" if level == "main" else (
        f"{main} AS main, CASE WHEN p.id IS NULL THEN '—' ELSE c.name END AS category"
    )
    groups = "1" if level == "main" else "1, 2"
    df = pd.read_sql(
        text(
            f"SELECT {columns}, SUM(ABS(t.amount)) AS total, COUNT(*) AS count "
            + _BASE.replace(
                "LEFT JOIN categories c ON c.id = t.category_id ",
                "LEFT JOIN categories c ON c.id = t.category_id "
                "LEFT JOIN categories p ON p.id = c.parent_id ",
            )
            + f"AND t.amount {sign} 0 "
            f"GROUP BY {groups} ORDER BY total DESC"
        ),
        conn,
        params={"start": start, "end": end},
    )
    grand_total = df["total"].sum()
    df["pct"] = [
        round(float(total / grand_total) * 100, 1) if grand_total else 0.0
        for total in df["total"]
    ]
    return df


def top_merchants(
    conn: Connection,
    start: date,
    end: date,
    n: int = 15,
    txn_type: str | None = None,
) -> pd.DataFrame:
    """Return merchant spending for POS and QPay, optionally filtered by type."""
    txn_type_filter = "AND t.txn_type = :txn_type " if txn_type else ""
    params: dict[str, date | int | str] = {"start": start, "end": end, "n": n}
    if txn_type:
        params["txn_type"] = txn_type

    return pd.read_sql(
        text(
            "SELECT m.name AS merchant, t.txn_type, COUNT(*) AS count, "
            "SUM(-t.amount) AS total "
            "FROM transactions t "
            "JOIN merchants m ON m.id = t.merchant_id "
            "LEFT JOIN categories c ON c.id = t.category_id "
            "WHERE (c.kind IS NULL OR c.kind <> 'transfer') "
            "AND t.txn_date::date BETWEEN :start AND :end "
            "AND t.amount < 0 AND t.txn_type IN ('pos', 'qpay') "
            + txn_type_filter
            + "GROUP BY m.name, t.txn_type ORDER BY total DESC LIMIT :n"
        ),
        conn,
        params=params,
    )


def home_metrics(conn: Connection, month_start: date, today: date) -> dict:
    """Totals for the home page."""
    row = conn.execute(
        text(
            "SELECT "
            "(SELECT COUNT(*) FROM transactions) AS transactions, "
            f"(SELECT COUNT(*) FROM transactions t WHERE {NEEDS_REVIEW}) AS unclassified, "
            "(SELECT MAX(imported_at) FROM imports) AS last_import, "
            "(SELECT COALESCE(-SUM(t.amount), 0) " + _BASE + "AND t.amount < 0) AS month_expense"
        ),
        {"start": month_start, "end": today},
    ).one()
    return dict(row._mapping)
