"""SQL for the Classify page: merchant groups to review and manual assignment."""

import pandas as pd
from sqlalchemy import Connection, text

from core import classifier
from core.classifier import OTHER

_DIRECTION = "CASE WHEN t.amount > 0 THEN 'in' ELSE 'out' END"
CATEGORY_KINDS = ("expense", "income", "transfer")
SOURCE_FILTERS = ("all", "auto", "manual", "review")

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
    conn: Connection,
    search: str = "",
    limit: int = 500,
    source: str = "all",
    import_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Recent transactions for the category editor.

    source narrows to 'auto' (rule or merchant default), 'manual' or 'review' (see
    NEEDS_REVIEW); import_ids to the rows of particular statement imports.
    """
    where = [
        "(:search = '' OR t.description ILIKE :pattern "
        "OR COALESCE(m.name, '') ILIKE :pattern "
        "OR COALESCE(t.counterparty, '') ILIKE :pattern)"
    ]
    params = {"search": search, "pattern": f"%{search}%", "limit": limit}
    if source == "auto":
        where.append("t.classified_by IN ('rule', 'merchant')")
    elif source == "manual":
        where.append("t.classified_by = 'manual'")
    elif source == "review":
        where.append(NEEDS_REVIEW)
    if import_ids is not None:
        where.append("t.import_id = ANY(:import_ids)")
        params["import_ids"] = list(import_ids)
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
            f"WHERE {' AND '.join(where)} "
            "ORDER BY t.txn_date DESC, t.id DESC LIMIT :limit"
        ),
        conn,
        params=params,
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
            "AND (category_id IS DISTINCT FROM :category_id "
            "OR classified_by IS DISTINCT FROM 'manual')"
        ),
        [
            {"transaction_id": transaction_id, "category_id": category_id}
            for transaction_id, category_id in category_by_transaction.items()
        ],
    )
    return result.rowcount


def reset_to_automatic(conn: Connection, transaction_ids: list[int]) -> int:
    """Drop manual overrides and let the rule engine classify these rows again."""
    if not transaction_ids:
        return 0
    reset = conn.execute(
        text(
            "UPDATE transactions SET classified_by = NULL "
            "WHERE id = ANY(:ids) AND classified_by = 'manual'"
        ),
        {"ids": list(transaction_ids)},
    ).rowcount
    classifier.apply(conn, list(transaction_ids))
    return reset


def main_categories(conn: Connection) -> list[tuple[int, str, str]]:
    """Active main categories as (id, kind, name): where a new subcategory can go."""
    return [
        (int(row.id), row.kind, row.name)
        for row in conn.execute(
            text(
                "SELECT id, kind, name FROM categories "
                "WHERE is_active IS TRUE AND parent_id IS NULL ORDER BY kind, name"
            )
        )
    ]


def create_category(
    conn: Connection, name: str, kind: str, parent_id: int | None = None
) -> int:
    """Add a user category: a main one of kind, or a subcategory of parent_id.

    Raises ValueError with an i18n key (cat_err_*) the page shows translated.
    """
    clean_name = " ".join(name.split())
    if not clean_name or len(clean_name) > 60:
        raise ValueError("cat_err_name")
    if parent_id is not None:
        parent_kind = conn.execute(
            text(
                "SELECT kind FROM categories "
                "WHERE id = :id AND is_active IS TRUE AND parent_id IS NULL"
            ),
            {"id": parent_id},
        ).scalar()
        if parent_kind is None:
            raise ValueError("cat_err_parent")
        kind = parent_kind  # a subcategory always has its main category's kind
    if kind not in CATEGORY_KINDS:
        raise ValueError("cat_err_kind")

    existing = conn.execute(
        text("SELECT id, is_active FROM categories WHERE name = :name AND kind = :kind"),
        {"name": clean_name, "kind": kind},
    ).first()
    if existing is not None and existing.is_active:
        raise ValueError("cat_err_exists")
    if existing is not None:  # an archived category with this name comes back
        conn.execute(
            text("UPDATE categories SET is_active = TRUE, parent_id = :parent_id WHERE id = :id"),
            {"parent_id": parent_id, "id": existing.id},
        )
        return int(existing.id)
    return int(
        conn.execute(
            text(
                "INSERT INTO categories (name, kind, is_default, is_active, parent_id) "
                "VALUES (:name, :kind, FALSE, TRUE, :parent_id) RETURNING id"
            ),
            {"name": clean_name, "kind": kind, "parent_id": parent_id},
        ).scalar_one()
    )


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
