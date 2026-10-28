"""Shared Streamlit helpers: page frame, one-time DB setup, formatting, category lists."""

from datetime import date
from decimal import Decimal

import streamlit as st
from sqlalchemy import Connection, Engine, text

from core.budget_service import budget_alerts
from core.i18n import category_name, language_selector, t
from core.recurring import log_cash_payment, run_check, settle
from core.theme import apply_theme, theme_selector

# (script path, text key, icon) for the translated sidebar menu.
NAV_PAGES: list[tuple[str, str, str]] = [
    ("app.py", "nav_home", "🏠"),
    ("pages/1_Upload.py", "nav_upload", "📤"),
    ("pages/2_Classify.py", "nav_classify", "🏷️"),
    ("pages/3_Reports.py", "nav_reports", "📊"),
    ("pages/4_Budget_Goals.py", "nav_budget", "🎯"),
    ("pages/6_Recurring.py", "nav_recurring", "🔁"),
    ("pages/5_AI_Assistant.py", "nav_ai", "🤖"),
]


def page(title_key: str, icon: str, title: str | None = None, show_title: bool = True) -> None:
    """Page config + sidebar (language, theme, translated menu) + page title.

    show_title=False lets a page draw its title itself (e.g. in a toolbar row).
    """
    heading = title or t(title_key)
    st.set_page_config(page_title=f"{heading} · FinTrack", page_icon=icon, layout="wide")
    language_selector()
    theme_selector()
    apply_theme()
    st.sidebar.divider()
    for path, key, nav_icon in NAV_PAGES:
        st.sidebar.page_link(path, label=t(key), icon=nav_icon)
    if show_title:
        st.title(heading)


@st.cache_resource
def _setup() -> Engine:
    # Imported here so a missing .env shows a friendly error instead of a traceback.
    from core.db import get_engine, init_db
    from core.seed import seed

    engine = get_engine()
    init_db(engine)
    seed(engine)
    return engine


def engine() -> Engine:
    """Return the DB engine (schema + seed run once per server), or stop the page."""
    try:
        return _setup()
    except Exception as exc:
        st.error(t("db_error", details=exc))
        st.stop()


def fmt_mnt(value: Decimal | float | int | None) -> str:
    """Format money as '1,234,567₮'."""
    amount = Decimal(str(value)) if value is not None else Decimal("0")
    return f"{amount:,.0f}₮"


def show_budget_alerts(conn: Connection, month: date, link: bool = True) -> int:
    """Box listing budgets that are exceeded or 80%+ used in month; returns how many."""
    alerts = budget_alerts(conn, month)
    if not alerts:
        return 0
    with st.container(border=True):
        st.markdown(f"**{t('alerts_title', month=f'{month:%Y-%m}')}**")
        for item in alerts:
            spent, limit = item["spent"], item["monthly_limit"]
            if item["status"] == "exceeded":
                st.error(
                    t(
                        "alert_exceeded",
                        category=category_name(item["category"]),
                        spent=fmt_mnt(spent),
                        limit=fmt_mnt(limit),
                        over=fmt_mnt(spent - limit),
                    ),
                    icon=":material/error:",
                )
            else:
                st.warning(
                    t(
                        "alert_approaching",
                        category=category_name(item["category"]),
                        pct=f"{item['percent_used']:.0%}",
                        spent=fmt_mnt(spent),
                        limit=fmt_mnt(limit),
                    ),
                    icon=":material/warning:",
                )
        if link:  # not on the Budget page itself
            st.page_link("pages/4_Budget_Goals.py", label=t("alerts_open_budget"), icon="🎯")
    return len(alerts)


def _settle_bill(item_id: int, due: date, action: str) -> None:
    # Button callback: runs before the rerun, so the alert disappears right away.
    with engine().begin() as conn:
        if action == "log":
            log_cash_payment(conn, item_id, expected_due=due)
        else:
            settle(conn, item_id, action, expected_due=due)
    st.toast(t(f"rec_done_{action}"), icon=":material/check_circle:")


def show_recurring_alerts(conn: Connection, today: date) -> int:
    """Run the recurring-bill check and list bills due within 7 days; returns how many."""
    matched, attention = run_check(conn, today)
    if matched:
        st.toast(t("rec_auto_matched", count=matched), icon=":material/link:")
    if not attention:
        return 0
    with st.container(border=True, key="card_recurring_alerts"):
        st.markdown(f"**{t('rec_alerts_title')}**")
        for bill in attention:
            color = {"overdue": "red", "due": "orange", "upcoming": "blue"}[bill.status]
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(
                    f":{color}[**{t('rec_status_' + bill.status)}**] · {bill.next_due} · "
                    f"**{bill.name}** — {fmt_mnt(bill.amount)}"
                )
                if bill.status != "upcoming":
                    for action, icon in (
                        ("confirmed", ":material/done:"),
                        ("log", ":material/payments:"),
                        ("skipped", ":material/skip_next:"),
                    ):
                        st.button(
                            t(f"rec_action_{action}"),
                            key=f"rec_{action}_{bill.id}_{bill.next_due}",
                            icon=icon,
                            on_click=_settle_bill,
                            args=(bill.id, bill.next_due, action),
                        )
        st.caption(t("rec_alerts_help"))
    return len(attention)


def category_options(conn: Connection) -> list[tuple[int, str]]:
    """Active categories as (id, 'Зарлага · Хоол хүнс › Супермаркет'), mains before their subs."""
    rows = conn.execute(
        text(
            "SELECT c.id, c.kind, c.name, p.name AS parent FROM categories c "
            "LEFT JOIN categories p ON p.id = c.parent_id WHERE c.is_active "
            "ORDER BY c.kind, COALESCE(p.name, c.name), c.parent_id IS NOT NULL, c.name"
        )
    )
    return [
        (row.id, f"{t('kind_' + row.kind)} · " + (f"{category_name(row.parent)} › {category_name(row.name)}" if row.parent else category_name(row.name)))
        for row in rows
    ]
