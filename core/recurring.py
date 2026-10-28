"""Recurring bills and subscriptions: schedule, match against statements, settle.

run_check() is the "background" step (called when the app opens, or from Windows Task
Scheduler via `python -m core.recurring`). It only does the safe automatic thing: if a
due bill's payment is already in an imported bank statement, mark it paid and move the
due date forward. It never creates transactions; logging a cash payment needs the user.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text

from core import classifier
from core.merchant import normalize
from core.receipt_service import CASH_BANK, cash_account_id

FREQUENCIES = ("weekly", "monthly", "yearly")
PERIODS_PER_MONTH = {
    "weekly": Decimal(52) / Decimal(12),
    "monthly": Decimal(1),
    "yearly": Decimal(1) / Decimal(12),
}
MATCH_BEFORE_DAYS = 3  # a payment this many days before the due date counts
MATCH_AFTER_DAYS = 7
UPCOMING_DAYS = 7


def add_months(anchor: date, months: int) -> date:
    """anchor + n months, clamped to the month's last day (Jan 31 + 1 -> Feb 28)."""
    total = anchor.month - 1 + months
    year, month = anchor.year + total // 12, total % 12 + 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def following_due(start: date, current: date, frequency: str) -> date:
    """The due date after current, keeping start's day of month (no drift)."""
    if frequency == "weekly":
        return current + timedelta(days=7)
    step = 1 if frequency == "monthly" else 12
    n = 0
    while add_months(start, n) <= current:
        n += step
    return add_months(start, n)


def monthly_cost(amount: Decimal, frequency: str) -> Decimal:
    """Average cost per month (weekly x 52/12, yearly / 12)."""
    return (amount * PERIODS_PER_MONTH[frequency]).quantize(Decimal("0.01"))


@dataclass
class DueItem:
    id: int
    name: str
    amount: Decimal
    direction: str
    frequency: str
    next_due: date
    category: str | None
    status: str  # 'overdue' | 'due' | 'upcoming'


def list_items(conn: Connection, active_only: bool = False) -> list[dict[str, Any]]:
    sql = (
        "SELECT r.id, r.name, r.amount, r.direction, r.frequency, r.start_date, r.next_due, "
        "r.category_id, c.name AS category, r.match_pattern, r.is_active "
        "FROM recurring_items r LEFT JOIN categories c ON c.id = r.category_id "
    )
    if active_only:
        sql += "WHERE r.is_active "
    return [dict(row._mapping) for row in conn.execute(text(sql + "ORDER BY r.next_due, r.name"))]


def save_item(conn: Connection, item: dict[str, Any]) -> int:
    """Insert (no id) or update an item. Validates the fields a user can type."""
    name = (item.get("name") or "").strip()
    amount = Decimal(str(item.get("amount") or 0)).quantize(Decimal("0.01"))
    if not name:
        raise ValueError("name")
    if amount <= 0:
        raise ValueError("amount")
    if item.get("frequency") not in FREQUENCIES:
        raise ValueError("frequency")
    params = {
        "name": name,
        "amount": amount,
        "direction": item.get("direction") or "out",
        "frequency": item["frequency"],
        "next_due": item["next_due"],
        "category_id": item.get("category_id"),
        "pattern": (item.get("match_pattern") or "").strip() or None,
        "active": bool(item.get("is_active", True)),
    }
    if item.get("id") is None:
        return conn.execute(
            text(
                "INSERT INTO recurring_items (name, amount, direction, frequency, start_date, "
                "next_due, category_id, match_pattern, is_active) VALUES (:name, :amount, "
                ":direction, :frequency, :next_due, :next_due, :category_id, :pattern, :active) "
                "RETURNING id"
            ),
            params,
        ).scalar_one()
    # Changing the due date re-anchors the schedule on the new day.
    conn.execute(
        text(
            "UPDATE recurring_items SET name = :name, amount = :amount, direction = :direction, "
            "frequency = :frequency, category_id = :category_id, match_pattern = :pattern, "
            "is_active = :active, start_date = CASE WHEN next_due <> :next_due "
            "THEN :next_due ELSE start_date END, next_due = :next_due WHERE id = :id"
        ),
        {**params, "id": item["id"]},
    )
    return int(item["id"])


def find_payment(conn: Connection, item: dict[str, Any], due: date) -> int | None:
    """A statement transaction that pays this bill near its due date, if any.

    With a match pattern (e.g. 'UNITEL'), the amount may vary (utility bills); without
    one, the amount must be exact. Transactions already linked to a bill are skipped.
    """
    sign = -1 if item["direction"] == "out" else 1
    conditions = [
        "b.code <> :cash",
        "t.txn_date::date BETWEEN :start AND :end",
        "SIGN(t.amount) = :sign",
        "NOT EXISTS (SELECT 1 FROM recurring_occurrences o WHERE o.transaction_id = t.id)",
    ]
    params: dict[str, Any] = {
        "cash": CASH_BANK,
        "start": due - timedelta(days=MATCH_BEFORE_DAYS),
        "end": due + timedelta(days=MATCH_AFTER_DAYS),
        "sign": sign,
        "due": due,
    }
    if item.get("match_pattern"):
        conditions.append(
            "(t.description ILIKE :pattern OR t.counterparty ILIKE :pattern OR m.name ILIKE :pattern)"
        )
        params["pattern"] = f"%{item['match_pattern'].strip()}%"
    else:
        conditions.append("t.amount = :amount")
        params["amount"] = sign * item["amount"]
    return conn.execute(
        text(
            "SELECT t.id FROM transactions t "
            "JOIN accounts a ON a.id = t.account_id JOIN banks b ON b.id = a.bank_id "
            "LEFT JOIN merchants m ON m.id = t.merchant_id "
            f"WHERE {' AND '.join(conditions)} "
            "ORDER BY ABS(t.txn_date::date - CAST(:due AS DATE)), t.id LIMIT 1"
        ),
        params,
    ).scalar()


def settle(
    conn: Connection,
    item_id: int,
    status: str,
    transaction_id: int | None = None,
    expected_due: date | None = None,
) -> date:
    """Record how the current due date was settled and move to the next one.

    With expected_due, nothing happens unless the bill is still due on that date
    (a double-click must not settle the following cycle too).
    """
    item = conn.execute(
        text("SELECT start_date, next_due, frequency FROM recurring_items WHERE id = :id FOR UPDATE"),
        {"id": item_id},
    ).one()
    if expected_due is not None and item.next_due != expected_due:
        return item.next_due
    conn.execute(
        text(
            "INSERT INTO recurring_occurrences (item_id, due_date, status, transaction_id) "
            "VALUES (:id, :due, :status, :txn)"
        ),
        {"id": item_id, "due": item.next_due, "status": status, "txn": transaction_id},
    )
    next_due = following_due(item.start_date, item.next_due, item.frequency)
    conn.execute(
        text("UPDATE recurring_items SET next_due = :next WHERE id = :id"),
        {"next": next_due, "id": item_id},
    )
    return next_due


def log_cash_payment(conn: Connection, item_id: int, expected_due: date | None = None) -> int | None:
    """User-confirmed: record the bill as a cash transaction, then settle it."""
    item = conn.execute(
        text(
            "SELECT name, amount, direction, category_id, next_due FROM recurring_items "
            "WHERE id = :id FOR UPDATE"
        ),
        {"id": item_id},
    ).one()
    if expected_due is not None and item.next_due != expected_due:
        return None
    name = normalize(item.name)
    merchant_id = conn.execute(
        text(
            "INSERT INTO merchants (name, txn_type) VALUES (:name, 'cash') "
            "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id"
        ),
        {"name": name},
    ).scalar_one()
    txn_id = conn.execute(
        text(
            "INSERT INTO transactions (account_id, txn_date, description, counterparty, bank_ref, "
            "amount, txn_type, merchant_id, category_id, classified_by) VALUES (:account, :date, "
            ":description, :counterparty, :ref, :amount, 'cash', :merchant_id, :category_id, "
            "CASE WHEN CAST(:category_id AS BIGINT) IS NULL THEN NULL ELSE 'manual' END) RETURNING id"
        ),
        {
            "account": cash_account_id(conn),
            "date": item.next_due,
            "description": f"Тогтмол төлбөр: {item.name}",
            "counterparty": item.name,
            "ref": f"RECUR-{item_id}-{item.next_due.isoformat()}",
            "amount": item.amount if item.direction == "in" else -item.amount,
            "merchant_id": merchant_id,
            "category_id": item.category_id,
        },
    ).scalar_one()
    if item.category_id is None:
        classifier.apply(conn, [txn_id])
    settle(conn, item_id, "logged", txn_id)
    return txn_id


def run_check(conn: Connection, today: date) -> tuple[int, list[DueItem]]:
    """Auto-settle due bills found in statements; return (#auto-matched, bills needing attention)."""
    matched = 0
    for item in list_items(conn, active_only=True):
        due = item["next_due"]
        while due <= today:  # catch up on missed cycles, but only while payments are found
            txn_id = find_payment(conn, item, due)
            if txn_id is None:
                break
            due = settle(conn, item["id"], "matched", txn_id)
            matched += 1

    attention = []
    for item in list_items(conn, active_only=True):
        due = item["next_due"]
        if due > today + timedelta(days=UPCOMING_DAYS):
            continue
        status = "overdue" if due < today else "due" if due == today else "upcoming"
        attention.append(
            DueItem(item["id"], item["name"], item["amount"], item["direction"],
                    item["frequency"], due, item["category"], status)
        )
    return matched, attention


def history(conn: Connection, limit: int = 30) -> list[dict[str, Any]]:
    return [
        dict(row._mapping)
        for row in conn.execute(
            text(
                "SELECT o.due_date, r.name, o.status, t.txn_date::date AS paid_on, t.amount "
                "FROM recurring_occurrences o JOIN recurring_items r ON r.id = o.item_id "
                "LEFT JOIN transactions t ON t.id = o.transaction_id "
                "ORDER BY o.due_date DESC, o.id DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
    ]


def main() -> None:
    """For Windows Task Scheduler: `python -m core.recurring` prints what needs attention."""
    from core.db import get_engine, init_db

    engine = get_engine()
    init_db(engine)
    with engine.begin() as conn:
        matched, attention = run_check(conn, date.today())
    print(f"Auto-matched from statements: {matched}")
    for item in attention:
        print(f"[{item.status.upper()}] {item.next_due} {item.name}: {item.amount:,.0f} MNT")
    if not attention:
        print("Nothing due in the next 7 days.")


if __name__ == "__main__":
    main()
