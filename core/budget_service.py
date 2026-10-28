"""Database operations and calculations for budgets and savings goals."""

from datetime import date, timedelta
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import Connection, Date, Numeric, bindparam, text

ALERT_THRESHOLD = Decimal("0.80")
CENT = Decimal("0.01")


class BudgetProgress(TypedDict):
    category_id: int | None
    category: str
    monthly_limit: Decimal | None
    spent: Decimal
    remaining: Decimal | None
    percent_used: Decimal | None
    status: str


class SavingsGoal(TypedDict):
    id: int
    name: str
    target_amount: Decimal
    current_amount: Decimal
    deadline: date


def normalize_month(month: date) -> date:
    """Return the first day of the selected calendar month."""
    return date(month.year, month.month, 1)


def _next_month(month: date) -> date:
    if month.month == 12:
        return date(month.year + 1, 1, 1)
    return date(month.year, month.month + 1, 1)


def _money(value: Decimal | int | float | str) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise ValueError("Amounts must be finite numbers.")
    return amount.quantize(CENT)


def expense_categories(conn: Connection) -> list[tuple[int, str]]:
    """Active main expense categories as (id, name); budgets are set on these."""
    return [
        (int(row.id), row.name)
        for row in conn.execute(
            text(
                "SELECT id, name FROM categories "
                "WHERE kind = 'expense' AND is_active IS TRUE AND parent_id IS NULL ORDER BY name"
            )
        )
    ]


def monthly_budget_progress(conn: Connection, month: date) -> list[BudgetProgress]:
    """Budget vs spending per main expense category (subcategories roll up) for a month."""
    month_start = normalize_month(month)
    next_month = _next_month(month_start)
    rows = conn.execute(
        text(
            "SELECT c.id AS category_id, c.name AS category, "
            "b.monthly_limit, COALESCE(SUM(-t.amount), 0) AS spent "
            "FROM categories c "
            "LEFT JOIN category_budgets b "
            "ON b.category_id = c.id AND b.budget_month = :month_start "
            "LEFT JOIN categories child ON COALESCE(child.parent_id, child.id) = c.id "
            "LEFT JOIN transactions t ON t.category_id = child.id "
            "AND t.amount < 0 AND t.txn_date >= :month_start "
            "AND t.txn_date < :next_month "
            "WHERE c.kind = 'expense' AND c.is_active IS TRUE AND c.parent_id IS NULL "
            "GROUP BY c.id, c.name, b.monthly_limit "
            "UNION ALL "
            "SELECT NULL AS category_id, 'Ангилаагүй' AS category, "
            "NULL AS monthly_limit, COALESCE(SUM(-t.amount), 0) AS spent "
            "FROM transactions t WHERE t.category_id IS NULL AND t.amount < 0 "
            "AND t.txn_date >= :month_start AND t.txn_date < :next_month "
            "HAVING COALESCE(SUM(-t.amount), 0) > 0 "
            "ORDER BY category"
        ).bindparams(
            bindparam("month_start", type_=Date()),
            bindparam("next_month", type_=Date()),
        ),
        {"month_start": month_start, "next_month": next_month},
    )

    progress: list[BudgetProgress] = []
    for row in rows:
        spent = _money(row.spent)
        limit = _money(row.monthly_limit) if row.monthly_limit is not None else None
        if limit is None:
            remaining = percent_used = None
            status = "unbudgeted"
        else:
            remaining = limit - spent
            percent_used = spent / limit
            if spent > limit:
                status = "exceeded"
            elif percent_used >= ALERT_THRESHOLD:
                status = "approaching"
            else:
                status = "within"
        progress.append(
            {
                "category_id": int(row.category_id) if row.category_id is not None else None,
                "category": row.category,
                "monthly_limit": limit,
                "spent": spent,
                "remaining": remaining,
                "percent_used": percent_used,
                "status": status,
            }
        )
    return progress


def budget_alerts(conn: Connection, month: date) -> list[BudgetProgress]:
    """Budgets that are exceeded or at least 80% used, exceeded first, then by % used."""
    alerts = [
        item
        for item in monthly_budget_progress(conn, month)
        if item["status"] in ("exceeded", "approaching")
    ]
    return sorted(
        alerts,
        key=lambda item: (item["status"] != "exceeded", -(item["percent_used"] or 0)),
    )


def months_between(start: date, end: date) -> list[date]:
    """First day of every calendar month from start's month to end's month."""
    months, month = [], normalize_month(start)
    while month <= end:
        months.append(month)
        month = _next_month(month)
    return months


def import_months(conn: Connection, import_ids: list[int]) -> list[date]:
    """Calendar months covered by the given statement imports, oldest first."""
    if not import_ids:
        return []
    months: set[date] = set()
    for row in conn.execute(
        text(
            "SELECT period_start, period_end FROM imports WHERE id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": list(import_ids)},
    ):
        if row.period_start and row.period_end:
            months.update(months_between(row.period_start, row.period_end))
    return sorted(months)


def copy_previous_month_budgets(conn: Connection, month: date) -> int:
    """Copy last month's limits into month for categories that have none yet."""
    month_start = normalize_month(month)
    previous = normalize_month(month_start - timedelta(days=1))
    return conn.execute(
        text(
            "INSERT INTO category_budgets (category_id, budget_month, monthly_limit) "
            "SELECT b.category_id, :month_start, b.monthly_limit FROM category_budgets b "
            "JOIN categories c ON c.id = b.category_id "
            "WHERE b.budget_month = :previous AND c.kind = 'expense' AND c.is_active IS TRUE "
            "AND NOT EXISTS (SELECT 1 FROM category_budgets n "
            "WHERE n.category_id = b.category_id AND n.budget_month = :month_start)"
        ).bindparams(
            bindparam("month_start", type_=Date()),
            bindparam("previous", type_=Date()),
        ),
        {"month_start": month_start, "previous": previous},
    ).rowcount


def save_monthly_budgets(
    conn: Connection,
    month: date,
    budgets: dict[int, Decimal | int | float | str | None],
) -> int:
    """Insert/update positive limits; remove a category's budget when its value is None."""
    month_start = normalize_month(month)
    active_categories = {category_id for category_id, _ in expense_categories(conn)}
    invalid_ids = set(budgets) - active_categories
    if invalid_ids:
        raise ValueError("Budgets can only be set for active expense categories.")

    saved = 0
    for category_id, value in budgets.items():
        if value is None:
            conn.execute(
                text(
                    "DELETE FROM category_budgets "
                    "WHERE category_id = :category_id AND budget_month = :month_start"
                ).bindparams(bindparam("month_start", type_=Date())),
                {"category_id": category_id, "month_start": month_start},
            )
            continue

        amount = _money(value)
        if amount <= 0:
            raise ValueError("Monthly budget limits must be greater than zero.")
        conn.execute(
            text(
                "INSERT INTO category_budgets (category_id, budget_month, monthly_limit) "
                "VALUES (:category_id, :month_start, :monthly_limit) "
                "ON CONFLICT (category_id, budget_month) DO UPDATE SET "
                "monthly_limit = EXCLUDED.monthly_limit, updated_at = CURRENT_TIMESTAMP"
            ).bindparams(
                bindparam("month_start", type_=Date()),
                bindparam("monthly_limit", type_=Numeric(14, 2)),
            ),
            {
                "category_id": category_id,
                "month_start": month_start,
                "monthly_limit": amount,
            },
        )
        saved += 1
    return saved


def create_savings_goal(
    conn: Connection,
    name: str,
    target_amount: Decimal | int | float | str,
    current_amount: Decimal | int | float | str,
    deadline: date,
    goal_type: str = "other",
) -> int:
    """Create a savings goal and return its database ID."""
    clean_name = name.strip()
    target = _money(target_amount)
    current = _money(current_amount)
    if not clean_name:
        raise ValueError("A savings goal name is required.")
    if target <= 0:
        raise ValueError("The savings goal target must be greater than zero.")
    if current < 0:
        raise ValueError("The current saved amount cannot be negative.")

    return int(
        conn.execute(
            text(
                "INSERT INTO savings_goals "
                "(name, target_amount, current_amount, deadline, goal_type) "
                "VALUES (:name, :target_amount, :current_amount, :deadline, :goal_type) "
                "RETURNING id"
            ).bindparams(
                bindparam("target_amount", type_=Numeric(14, 2)),
                bindparam("current_amount", type_=Numeric(14, 2)),
                bindparam("deadline", type_=Date()),
            ),
            {
                "name": clean_name,
                "target_amount": target,
                "current_amount": current,
                "deadline": deadline,
                "goal_type": goal_type,
            },
        ).scalar_one()
    )


def list_savings_goals(conn: Connection) -> list[SavingsGoal]:
    """Return active savings goals ordered by deadline and name."""
    return [
        {
            "id": int(row.id),
            "name": row.name,
            "target_amount": _money(row.target_amount),
            "current_amount": _money(row.current_amount),
            "deadline": row.deadline,
        }
        for row in conn.execute(
            text(
                "SELECT id, name, target_amount, current_amount, deadline "
                "FROM savings_goals WHERE is_active IS TRUE "
                "ORDER BY deadline, name"
            )
        )
    ]


def update_savings_goal(
    conn: Connection, goal_id: int, current_amount: Decimal | int | float | str
) -> None:
    """Update the amount saved toward an active goal."""
    current = _money(current_amount)
    if current < 0:
        raise ValueError("The current saved amount cannot be negative.")
    result = conn.execute(
        text(
            "UPDATE savings_goals SET current_amount = :current_amount, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE id = :goal_id AND is_active IS TRUE"
        ).bindparams(bindparam("current_amount", type_=Numeric(14, 2))),
        {"goal_id": goal_id, "current_amount": current},
    )
    if result.rowcount != 1:
        raise ValueError("The selected savings goal is no longer active.")


def archive_savings_goal(conn: Connection, goal_id: int) -> None:
    """Archive an active goal without deleting its history."""
    result = conn.execute(
        text(
            "UPDATE savings_goals SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = :goal_id AND is_active IS TRUE"
        ),
        {"goal_id": goal_id},
    )
    if result.rowcount != 1:
        raise ValueError("The selected savings goal is no longer active.")
