"""Long-term goals: progress from savings transactions, monthly saving needed, on-track status.

A goal's saved amount = its starting amount (typed in when created/updated) + every
savings transaction assigned to it. Savings transactions are payments classified as
'Хуримтлал' (a transfer, so they are not counted as spending).
"""

import math
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text

from core.classifier import SAVINGS

GOAL_TYPES = ("emergency", "education", "purchase", "travel", "other")
DAYS_PER_MONTH = 30.44
ON_TRACK_MARGIN = 5.0  # percentage points behind the straight line that still count as on track


def months_left(today: date, deadline: date) -> int:
    """Whole months to save in (at least 1 while the deadline is today or later)."""
    days = (deadline - today).days
    return max(1, math.ceil(days / DAYS_PER_MONTH)) if days >= 0 else 0


def evaluate(
    target: Decimal, saved: Decimal, created: date, deadline: date, today: date
) -> dict[str, Any]:
    """Pure progress maths for one goal (tested without a database)."""
    remaining = max(target - saved, Decimal("0"))
    left = months_left(today, deadline)
    percent = float(saved / target) * 100 if target else 0.0
    span = max((deadline - created).days, 1)
    expected = min(max((today - created).days / span, 0.0), 1.0) * 100
    if saved >= target:
        status = "done"
    elif left == 0:
        status = "overdue"
    elif percent >= expected + 10:
        status = "ahead"
    elif percent >= expected - ON_TRACK_MARGIN:
        status = "on_track"
    else:
        status = "behind"
    monthly = (remaining / left).quantize(Decimal("1")) if left else remaining
    return {
        "remaining": remaining,
        "months_left": left,
        "monthly_needed": monthly,
        "percent": percent,
        "expected_percent": expected,
        "status": status,
    }


def goal_progress(conn: Connection, today: date) -> list[dict[str, Any]]:
    """Active goals with saved amount (start + assigned savings) and their evaluation."""
    rows = conn.execute(
        text(
            "SELECT g.id, g.name, g.goal_type, g.target_amount, g.current_amount, g.deadline, "
            "g.created_at::date AS created, "
            "COALESCE(SUM(-t.amount), 0) AS contributed, COUNT(t.id) AS contributions "
            "FROM savings_goals g "
            "LEFT JOIN goal_contributions gc ON gc.goal_id = g.id "
            "LEFT JOIN transactions t ON t.id = gc.transaction_id "
            "WHERE g.is_active IS TRUE "
            "GROUP BY g.id ORDER BY g.deadline, g.name"
        )
    )
    goals = []
    for row in rows:
        start, contributed = Decimal(row.current_amount), Decimal(row.contributed)
        saved = start + contributed
        goals.append(
            {
                "id": row.id,
                "name": row.name,
                "goal_type": row.goal_type if row.goal_type in GOAL_TYPES else "other",
                "target": Decimal(row.target_amount),
                "starting": start,
                "contributed": contributed,
                "contributions": row.contributions,
                "saved": saved,
                "deadline": row.deadline,
                **evaluate(Decimal(row.target_amount), saved, row.created, row.deadline, today),
            }
        )
    return goals


def unassigned_savings(conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
    """Savings payments ('Хуримтлал', money out) not yet assigned to any goal."""
    rows = conn.execute(
        text(
            "SELECT t.id, t.txn_date::date AS date, t.description, -t.amount AS amount "
            "FROM transactions t JOIN categories c ON c.id = t.category_id "
            "WHERE c.name = :savings AND c.kind = 'transfer' AND t.amount < 0 "
            "AND NOT EXISTS (SELECT 1 FROM goal_contributions gc WHERE gc.transaction_id = t.id) "
            "ORDER BY t.txn_date DESC, t.id DESC LIMIT :limit"
        ),
        {"savings": SAVINGS, "limit": limit},
    )
    return [dict(row._mapping) for row in rows]


def assign(conn: Connection, assignments: dict[int, int]) -> int:
    """Assign savings transactions to goals ({transaction_id: goal_id}); returns how many."""
    count = 0
    for transaction_id, goal_id in assignments.items():
        count += conn.execute(
            text(
                "INSERT INTO goal_contributions (goal_id, transaction_id) "
                "SELECT :goal_id, :transaction_id WHERE EXISTS "
                "(SELECT 1 FROM savings_goals WHERE id = :goal_id AND is_active IS TRUE) "
                "ON CONFLICT (transaction_id) DO NOTHING"
            ),
            {"goal_id": goal_id, "transaction_id": transaction_id},
        ).rowcount
    return count
