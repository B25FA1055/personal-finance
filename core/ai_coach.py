"""Local rule-based financial coach and read-only summary of the user's finances."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text

from core import reports
from core.budget_service import list_savings_goals, monthly_budget_progress
from core.i18n import category_name, t

FOOD_CATEGORIES = ("Хоол хүнс", "Ресторан & Кафе")  # main categories

def _money(value: Any) -> int:
    return int(round(Decimal(str(value or 0))))


def _month_bounds(today: date) -> tuple[date, date, date]:
    """(start of this month, start of last month, end of last month)."""
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    return month_start, last_month_end.replace(day=1), last_month_end


def _categories(conn: Connection, start: date, end: date, kind: str) -> list[dict[str, Any]]:
    df = reports.by_category(conn, start, end, kind)
    return [
        {"category": row.category, "total": _money(row.total), "count": int(row.count)}
        for row in df.itertuples()
    ]


def _merchants(conn: Connection, start: date, end: date, limit: int = 12) -> list[dict[str, Any]]:
    """Card and QPay spending by merchant (businesses only, never person transfers)."""
    rows = conn.execute(
        text(
            "SELECT m.name AS merchant, t.txn_type, COALESCE(p.name, c.name, 'Unclassified') AS category, "
            "COUNT(*) AS count, SUM(-t.amount) AS total "
            "FROM transactions t "
            "JOIN merchants m ON m.id = t.merchant_id "
            "LEFT JOIN categories c ON c.id = t.category_id "
            "LEFT JOIN categories p ON p.id = c.parent_id "
            "WHERE t.amount < 0 AND t.txn_type IN ('pos', 'qpay', 'cash') "
            "AND (c.kind IS NULL OR c.kind <> 'transfer') "
            "AND t.txn_date::date BETWEEN :start AND :end "
            "GROUP BY m.name, t.txn_type, 3 ORDER BY total DESC LIMIT :limit"
        ),
        {"start": start, "end": end, "limit": limit},
    )
    return [
        {
            "merchant": row.merchant,
            "type": row.txn_type,
            "category": row.category,
            "count": int(row.count),
            "total": _money(row.total),
        }
        for row in rows
    ]


def build_context(conn: Connection, today: date, ui_language: str = "mn") -> dict[str, Any]:
    """Aggregated, privacy-safe snapshot of the user's finances. Call inside a transaction."""
    conn.execute(text("SET TRANSACTION READ ONLY"))
    month_start, last_start, last_end = _month_bounds(today)
    history_start = (month_start - timedelta(days=150)).replace(day=1)

    monthly = reports.monthly_summary(conn, history_start, today)
    last_import = conn.execute(text("SELECT MAX(period_end) FROM imports")).scalar()

    budgets = [
        {
            "category": item["category"],
            "limit": _money(item["monthly_limit"]) if item["monthly_limit"] is not None else None,
            "spent": _money(item["spent"]),
            "status": item["status"],
        }
        for item in monthly_budget_progress(conn, month_start)
        if item["monthly_limit"] is not None or item["spent"] > 0
    ]
    goals = [
        {
            "name": goal["name"],
            "target": _money(goal["target_amount"]),
            "saved": _money(goal["current_amount"]),
            "percent": round(float(goal["current_amount"] / goal["target_amount"]) * 100, 1)
            if goal["target_amount"]
            else 0.0,
            "deadline": goal["deadline"].isoformat(),
        }
        for goal in list_savings_goals(conn)
    ]

    return {
        "today": today.isoformat(),
        "ui_language": ui_language,
        "data_until": last_import.isoformat() if last_import else None,
        "monthly": [
            {
                "month": row.month.strftime("%Y-%m"),
                "income": _money(row.income),
                "expense": _money(row.expense),
                "net": _money(row.net),
            }
            for row in monthly.itertuples()
        ],
        "this_month": {
            "period": f"{month_start.isoformat()}..{today.isoformat()}",
            "expense_by_category": _categories(conn, month_start, today, "expense"),
            "income_by_category": _categories(conn, month_start, today, "income"),
            "top_merchants": _merchants(conn, month_start, today),
        },
        "last_month": {
            "period": f"{last_start.isoformat()}..{last_end.isoformat()}",
            "expense_by_category": _categories(conn, last_start, last_end, "expense"),
            "top_merchants": _merchants(conn, last_start, last_end),
        },
        "budgets_this_month": budgets,
        "savings_goals": goals,
    }


# --- Local rule-based coach --------------------------------------------------

# Mongolian keywords are stems: suffixes drop vowels (төсөв -> төсвөөсөө, зорилго -> зорилгоо).
_INTENTS: list[tuple[str, tuple[str, ...]]] = [
    ("savings", ("хуримтл", "зорилг", "хадгал", "saving", "save", "goal")),
    ("food", ("хоол", "хүнс", "ресторан", "кафе", "food", "grocer", "restaurant", "eat")),
    ("budget", ("төсөв", "төсв", "хязгаар", "budget", "limit")),
    ("top", ("хамгийн", "зарцуул", "хаана", "most", "where", "spend", "spent", "top")),
    ("summary", ("орлого", "зарлага", "дүн", "income", "expense", "summary", "net", "overview")),
]


def _detect_intent(question: str) -> str:
    q = question.lower()
    for intent, keywords in _INTENTS:
        if any(keyword in q for keyword in keywords):
            return intent
    return "help"


def _fmt(amount: int) -> str:
    return f"{amount:,}₮"


def _bullets(rows: list[dict[str, Any]], key: str, n: int = 3) -> str:
    # Context keeps the stored (Mongolian) names; show categories in the UI language.
    label = category_name if key == "category" else str
    return "\n".join(f"- {label(row[key])}: **{_fmt(row['total'])}** ({row['count']}×)" for row in rows[:n])


def rule_based_answer(question: str, context: dict[str, Any]) -> str:
    """Return a deterministic answer based on locally queried account summaries."""
    this_month = context["this_month"]
    expenses = this_month["expense_by_category"]
    intent = _detect_intent(question)

    if intent == "top":
        if not expenses:
            return t("coach_no_data")
        top = expenses[0]
        parts = [
            t("coach_top", category=category_name(top["category"]), amount=_fmt(top["total"])),
            _bullets(expenses, "category"),
        ]
        if this_month["top_merchants"]:
            parts += [t("coach_top_merchants"), _bullets(this_month["top_merchants"], "merchant")]
        return "\n\n".join(parts)

    if intent == "food":
        now = sum(c["total"] for c in expenses if c["category"] in FOOD_CATEGORIES)
        before = sum(
            c["total"]
            for c in context["last_month"]["expense_by_category"]
            if c["category"] in FOOD_CATEGORIES
        )
        food_merchants = [m for m in this_month["top_merchants"] if m["category"] in FOOD_CATEGORIES]
        parts = [t("coach_food", now=_fmt(now), before=_fmt(before))]
        if food_merchants:
            parts += [t("coach_food_merchants"), _bullets(food_merchants, "merchant")]
        parts.append(t("coach_food_tips", food=category_name("Хоол хүнс")))
        return "\n\n".join(parts)

    if intent == "savings":
        goals = context["savings_goals"]
        if not goals:
            return t("coach_no_goals")
        lines = [
            t(
                "coach_goal_line",
                name=g["name"],
                saved=_fmt(g["saved"]),
                target=_fmt(g["target"]),
                percent=g["percent"],
                deadline=g["deadline"],
            )
            for g in goals
        ]
        return t("coach_goals_intro") + "\n" + "\n".join(lines)

    if intent == "budget":
        budgets = [b for b in context["budgets_this_month"] if b["limit"] is not None]
        if not budgets:
            return t("coach_no_budgets")
        lines = [
            t(
                "coach_budget_line",
                category=category_name(b["category"]),
                spent=_fmt(b["spent"]),
                limit=_fmt(b["limit"]),
                status=t(f"coach_status_{b['status']}"),
            )
            for b in budgets
        ]
        return t("coach_budgets_intro") + "\n" + "\n".join(lines)

    if intent == "summary" and context["monthly"]:
        m = context["monthly"][-1]
        return t(
            "coach_summary",
            month=m["month"],
            income=_fmt(m["income"]),
            expense=_fmt(m["expense"]),
            net=_fmt(m["net"]),
        )

    return t("coach_help")
