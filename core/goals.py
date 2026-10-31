"""Long-term goals: progress, multi-source funding plans, timelines and monthly savings.

A goal's saved amount = its starting amount (typed in when created/updated) + every
savings transaction assigned to it. Savings transactions are payments classified as
'Хуримтлал' (a transfer, so they are not counted as spending).

A goal can also have planned funding sources: monthly streams (a share of salary, a
partner's contribution), one-off amounts (a bonus) and loans (e.g. a mortgage paid out at
purchase). project() adds them up month by month to give the completion month and any
shortfall.
"""

import math
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, bindparam, text

from core.classifier import SAVINGS

GOAL_TYPES = ("emergency", "education", "purchase", "travel", "other")
FUNDING_KINDS = ("monthly", "lump_sum", "loan")
DAYS_PER_MONTH = 30.44
ON_TRACK_MARGIN = 5.0  # percentage points behind the straight line that still count as on track
MAX_PROJECTION_MONTHS = 600  # 50 years: beyond this the plan "never" reaches the goal


def _money(value: Decimal | int | float | str) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise ValueError("Amounts must be finite numbers.")
    return amount.quantize(Decimal("0.01"))


def _month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


def _normalize_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _date_value(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _month_start(index: int) -> date:
    return date(index // 12, index % 12 + 1, 1)


def source_inflow(source: dict[str, Any], month_index: int, today: date) -> Decimal:
    """What one funding source adds in a month (only money still to come after today)."""
    start = _month_index(source["start_month"])
    if source["kind"] == "monthly":
        end = _month_index(source["end_month"]) if source.get("end_month") else None
        active = start <= month_index and (end is None or month_index <= end)
        # This month's contributions are recorded as transactions; plan from next month.
        return source["amount"] if active and month_index > _month_index(today) else Decimal("0")
    # lump_sum / loan: once, in its month, if it is still expected (dated after today)
    return source["amount"] if month_index == start and source["start_month"] > today else Decimal("0")


def project(
    target: Decimal, saved: Decimal, sources: list[dict[str, Any]], today: date, deadline: date
) -> dict[str, Any]:
    """Combine all funding sources month by month (pure; tested without a database).

    Returns the planned amount by the deadline, the projected completion month, the
    shortfall, how much extra to save per month to close it, and the monthly plan.
    """
    remaining = max(target - saved, Decimal("0"))
    first = _month_index(today) + 1
    last_needed = _month_index(deadline)
    planned_by_deadline = Decimal("0")
    projected = _month_start(_month_index(today)) if remaining == 0 else None
    last_inflow = max(
        [_month_index(s["end_month"]) if s.get("end_month") else first + MAX_PROJECTION_MONTHS
         for s in sources if s["kind"] == "monthly"]
        + [_month_index(s["start_month"]) for s in sources if s["kind"] != "monthly"],
        default=first - 1,
    )
    cumulative = Decimal("0")
    for month in range(first, min(last_inflow, first + MAX_PROJECTION_MONTHS) + 1):
        inflow = sum((source_inflow(s, month, today) for s in sources), Decimal("0"))
        cumulative += inflow
        if month <= last_needed:
            planned_by_deadline += inflow
        if projected is None and cumulative >= remaining:
            projected = _month_start(month)
        if projected is not None and month >= last_needed:
            break
    months_to_deadline = max(last_needed - first + 1, 0)
    shortfall = max(remaining - planned_by_deadline, Decimal("0"))
    extra = (
        Decimal(math.ceil(shortfall / months_to_deadline)) if months_to_deadline and shortfall else shortfall
    )
    if remaining == 0:
        plan_status = "done"
    elif not sources:
        plan_status = "no_plan"
    else:
        plan_status = "covered" if shortfall == 0 else "gap"
    return {
        "planned_by_deadline": planned_by_deadline,
        "projected_month": projected,
        "shortfall": shortfall,
        "extra_per_month": extra,
        "monthly_plan": sum((source_inflow(s, first, today) for s in sources if s["kind"] == "monthly"),
                            Decimal("0")),
        "loan_total": sum((s["amount"] for s in sources if s["kind"] == "loan"), Decimal("0")),
        "plan_status": plan_status,
    }


def monthly_funding_totals(conn: Connection, month: date) -> dict[str, Decimal]:
    """Planned goal savings and actual savings-category transfers in a calendar month."""
    month_start = _month_start(_month_index(month))
    next_month = _month_start(_month_index(month_start) + 1)
    planned = conn.execute(
        text(
            "SELECT COALESCE(SUM(fs.amount), 0) FROM goal_funding_sources fs "
            "JOIN savings_goals g ON g.id = fs.goal_id "
            "WHERE g.is_active IS TRUE AND ((fs.kind = 'monthly' "
            "AND fs.start_month <= :month_start "
            "AND (fs.end_month IS NULL OR fs.end_month >= :month_start)) "
            "OR (fs.kind = 'lump_sum' AND fs.start_month = :month_start))"
        ),
        {"month_start": month_start},
    ).scalar_one()
    actual = conn.execute(
        text(
            "SELECT COALESCE(SUM(-t.amount), 0) FROM transactions t "
            "JOIN categories c ON c.id = t.category_id "
            "WHERE c.name = :savings AND c.kind = 'transfer' AND t.amount < 0 "
            "AND t.txn_date >= :month_start AND t.txn_date < :next_month"
        ),
        {"savings": SAVINGS, "month_start": month_start, "next_month": next_month},
    ).scalar_one()
    return {"planned": Decimal(str(planned)), "actual": Decimal(str(actual))}


def months_left(today: date, deadline: date) -> int:
    """Whole months to save in (at least 1 while the deadline is today or later)."""
    days = (deadline - today).days
    return max(1, math.ceil(days / DAYS_PER_MONTH)) if days >= 0 else 0


def evaluate(
    target: Decimal, saved: Decimal, created: date, deadline: date, today: date
) -> dict[str, Any]:
    """Progress and the monthly amount needed to reach one goal by its deadline."""
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
    """Active goals, actual savings, and projections from all planned funding sources."""
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
    goal_rows = list(rows)
    if not goal_rows:
        return []

    sources_by_goal: dict[int, list[dict[str, Any]]] = {
        int(row.id): [] for row in goal_rows
    }
    source_rows = conn.execute(
        text(
            "SELECT id, goal_id, name, kind, amount, start_month, end_month "
            "FROM goal_funding_sources WHERE goal_id IN :goal_ids ORDER BY name"
        ).bindparams(bindparam("goal_ids", expanding=True)),
        {"goal_ids": list(sources_by_goal)},
    )
    for row in source_rows:
        sources_by_goal[int(row.goal_id)].append(
            {
                "id": int(row.id),
                "name": row.name,
                "kind": row.kind,
                "amount": Decimal(row.amount),
                "start_month": _date_value(row.start_month),
                "end_month": _date_value(row.end_month),
            }
        )

    goals: list[dict[str, Any]] = []
    for row in goal_rows:
        start, contributed = Decimal(row.current_amount), Decimal(row.contributed)
        saved = start + contributed
        funding_plan = sources_by_goal[int(row.id)]
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
                **evaluate(
                    Decimal(row.target_amount),
                    saved,
                    row.created,
                    row.deadline,
                    today,
                ),
                **project(
                    Decimal(row.target_amount),
                    saved,
                    funding_plan,
                    today,
                    row.deadline,
                ),
            }
        )
    return goals


def list_goal_funding_sources(conn: Connection, goal_id: int) -> list[dict[str, Any]]:
    """Planned monthly, one-off, and loan funding sources for an active goal."""
    return [
        {
            "id": int(row.id),
            "name": row.name,
            "kind": row.kind,
            "amount": Decimal(row.amount),
            "start_month": _date_value(row.start_month),
            "end_month": _date_value(row.end_month),
        }
        for row in conn.execute(
            text(
                "SELECT fs.id, fs.name, fs.kind, fs.amount, fs.start_month, fs.end_month "
                "FROM goal_funding_sources fs "
                "JOIN savings_goals g ON g.id = fs.goal_id "
                "WHERE fs.goal_id = :goal_id AND g.is_active IS TRUE "
                "ORDER BY fs.name"
            ),
            {"goal_id": goal_id},
        )
    ]


def save_goal_funding_sources(
    conn: Connection,
    goal_id: int,
    sources: list[dict[str, Any]],
) -> int:
    """Replace a goal's planned funding sources; return the number saved."""
    if conn.execute(
        text("SELECT 1 FROM savings_goals WHERE id = :goal_id AND is_active IS TRUE"),
        {"goal_id": goal_id},
    ).first() is None:
        raise ValueError("The selected savings goal is no longer active.")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        name = str(source.get("name") or "").strip()
        if not name or len(name) > 100:
            raise ValueError("Funding source names must contain 1 to 100 characters.")
        key = name.casefold()
        if key in seen:
            raise ValueError("Funding source names must be unique within a goal.")
        seen.add(key)
        kind = str(source.get("kind") or "")
        if kind not in FUNDING_KINDS:
            raise ValueError("Choose monthly, lump-sum, or loan funding for each source.")
        amount = _money(source["amount"])
        if amount <= 0:
            raise ValueError("Funding source amounts must be greater than zero.")
        start_month = source.get("start_month")
        if isinstance(start_month, str):
            start_month = date.fromisoformat(start_month)
        if not isinstance(start_month, date):
            raise ValueError("Choose a start month for each funding source.")
        start_month = _normalize_month(start_month)
        end_month = source.get("end_month")
        if isinstance(end_month, str):
            end_month = date.fromisoformat(end_month) if end_month else None
        if end_month is not None:
            if not isinstance(end_month, date):
                raise ValueError("Choose a valid end month.")
            end_month = _normalize_month(end_month)
        if kind == "monthly" and end_month is not None and end_month < start_month:
            raise ValueError("The funding source end month cannot be before its start month.")
        if kind != "monthly" and end_month is not None:
            raise ValueError("Only monthly funding sources can have an end month.")
        normalized.append(
            {
                "name": name,
                "kind": kind,
                "amount": amount,
                "start_month": start_month,
                "end_month": end_month,
            }
        )

    conn.execute(
        text("DELETE FROM goal_funding_sources WHERE goal_id = :goal_id"),
        {"goal_id": goal_id},
    )
    for source in normalized:
        conn.execute(
            text(
                "INSERT INTO goal_funding_sources "
                "(goal_id, name, kind, amount, start_month, end_month, source_name, monthly_amount) "
                "VALUES (:goal_id, :name, :kind, :amount, :start_month, :end_month, :name, "
                "CASE WHEN :kind = 'monthly' THEN :amount ELSE NULL END)"
            ),
            {
                "goal_id": goal_id,
                **source,
                "amount": str(source["amount"]),
            },
        )
    return len(normalized)


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


def assign(
    conn: Connection,
    assignments: dict[int, int | tuple[int, int | None]],
) -> int:
    """Assign savings transactions to goals and, optionally, named funding sources."""
    count = 0
    for transaction_id, target in assignments.items():
        goal_id, source_id = target if isinstance(target, tuple) else (target, None)
        count += conn.execute(
            text(
                "INSERT INTO goal_contributions (goal_id, transaction_id, source_id) "
                "SELECT :goal_id, :transaction_id, :source_id WHERE EXISTS "
                "(SELECT 1 FROM savings_goals WHERE id = :goal_id AND is_active IS TRUE) "
                "AND (:source_id IS NULL OR EXISTS "
                "(SELECT 1 FROM goal_funding_sources WHERE id = :source_id AND goal_id = :goal_id)) "
                "ON CONFLICT (transaction_id) DO NOTHING"
            ),
            {"goal_id": goal_id, "transaction_id": transaction_id, "source_id": source_id},
        ).rowcount
    return count
