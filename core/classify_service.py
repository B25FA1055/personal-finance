"""SQL for the Classify page: merchant groups to review and manual assignment."""

import pandas as pd
from sqlalchemy import Connection, text

from core.classifier import OTHER

_DIRECTION = "CASE WHEN t.amount > 0 THEN 'in' ELSE 'out' END"

# "Needs review": no category, or put in Бусад only because no rule matched.
NEEDS_REVIEW = (
    "(t.category_id IS NULL OR (t.classified_by = 'merchant' AND t.category_id IN "
    f"(SELECT id FROM categories WHERE name = '{OTHER}')))"
)


def unclassified_counts(conn: Connection) -> tuple[int, int]:
    """Return (transactions needing review, distinct merchant groups)."""
    row = conn.execute(
        text(
            "SELECT COALESCE(SUM(n), 0) AS n, COUNT(*) AS g FROM ("
            f"SELECT COUNT(*) AS n FROM transactions t WHERE {NEEDS_REVIEW} "
            f"GROUP BY t.merchant_id, {_DIRECTION}) groups"
        )
    ).one()
    return row.n, row.g


def unclassified_groups(conn: Connection) -> pd.DataFrame:
    """Transactions needing review, grouped by merchant and direction, biggest first."""
    return pd.read_sql(
        text(
            "SELECT t.merchant_id, "
            "COALESCE(m.name, '(no merchant)') AS merchant, "
            "MIN(t.txn_type) AS txn_type, "
            f"{_DIRECTION} AS direction, "
            "COUNT(*) AS count, "
            "SUM(ABS(t.amount)) AS total, "
            "MIN(t.txn_date)::date AS first_date, "
            "MAX(t.txn_date)::date AS last_date, "
            "MIN(t.description) AS example "
            "FROM transactions t LEFT JOIN merchants m ON m.id = t.merchant_id "
            f"WHERE {NEEDS_REVIEW} "
            "GROUP BY t.merchant_id, m.name, 4 "
            "ORDER BY total DESC"
        ),
        conn,
    )


def classification_transactions(
    conn: Connection, search: str = "", limit: int = 500
) -> pd.DataFrame:
    """Return recent transactions with category labels for the classification editor."""
    return pd.read_sql(
        text(
            "SELECT t.id, t.txn_date::date AS date, t.description, "
            "COALESCE(m.name, t.counterparty, '') AS merchant, "
            "t.txn_type, t.amount, t.category_id, "
            "CASE WHEN c.id IS NULL THEN NULL "
            "ELSE INITCAP(c.kind) || ' · ' || c.name END AS category, "
            "CASE t.classified_by WHEN 'rule' THEN 'Automatic rule' "
            "WHEN 'merchant' THEN 'Automatic default' "
            "WHEN 'manual' THEN 'Manual' ELSE 'Unclassified' END AS classified_by "
            "FROM transactions t "
            "LEFT JOIN merchants m ON m.id = t.merchant_id "
            "LEFT JOIN categories c ON c.id = t.category_id "
            "WHERE :search = '' OR t.description ILIKE :pattern "
            "OR COALESCE(m.name, '') ILIKE :pattern "
            "OR COALESCE(t.counterparty, '') ILIKE :pattern "
            "ORDER BY t.txn_date DESC, t.id DESC LIMIT :limit"
        ),
        conn,
        params={"search": search, "pattern": f"%{search}%", "limit": limit},
    )


def set_transaction_categories(
    conn: Connection, category_by_transaction: dict[int, int]
) -> int:
    """Manually set categories for selected transactions."""
    if not category_by_transaction:
        return 0
    result = conn.execute(
        text(
            "UPDATE transactions SET category_id = :category_id, "
            "classified_by = 'manual' WHERE id = :transaction_id "
            "AND category_id IS DISTINCT FROM :category_id"
        ),
        [
            {"transaction_id": transaction_id, "category_id": category_id}
            for transaction_id, category_id in category_by_transaction.items()
        ],
    )
    return result.rowcount


def assign_group(
    conn: Connection,
    merchant_id: int | None,
    direction: str,
    category_id: int,
    remember: bool,
) -> tuple[int, bool]:
    """Manually classify one group; optionally save a rule. Return (rows, rule_saved)."""
    updated = conn.execute(
        text(
            "UPDATE transactions t SET category_id = :category_id, "
            "classified_by = 'manual' "
            f"WHERE {NEEDS_REVIEW} "
            "AND t.merchant_id IS NOT DISTINCT FROM CAST(:merchant_id AS BIGINT) "
            f"AND {_DIRECTION} = :direction"
        ),
        {"category_id": category_id, "merchant_id": merchant_id, "direction": direction},
    ).rowcount

    if not remember or merchant_id is None:
        return updated, False

    merchant = conn.execute(
        text("SELECT name, txn_type FROM merchants WHERE id = :id"), {"id": merchant_id}
    ).one()
    rule_direction = "any" if merchant.txn_type in ("pos", "qpay") else direction
    params = {"pattern": merchant.name, "direction": rule_direction, "category_id": category_id}

    existing = conn.execute(
        text(
            "SELECT id FROM rules WHERE field = 'merchant' AND match = 'exact' "
            "AND pattern = :pattern AND direction = :direction"
        ),
        params,
    ).scalar_one_or_none()
    if existing is None:
        conn.execute(
            text(
                "INSERT INTO rules (field, match, pattern, direction, category_id, priority) "
                "VALUES ('merchant', 'exact', :pattern, :direction, :category_id, 50)"
            ),
            params,
        )
    else:
        conn.execute(
            text("UPDATE rules SET category_id = :category_id WHERE id = :id"),
            {"category_id": category_id, "id": existing},
        )
    return updated, True
