"""Shared Streamlit helpers: page frame, one-time DB setup, formatting, category lists."""

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlalchemy import Connection, Engine, text

from core.budget_service import budget_alerts
from core.classify_service import reset_to_automatic, set_transaction_categories
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


def category_editor(
    transactions: pd.DataFrame, categories: list[tuple[int, str]], key: str, flash_key: str
) -> None:
    """Editable transaction table (from classification_transactions) with a save bar.

    A changed category is saved as a manual override, which automatic classification
    never touches again; the "back to automatic" choice removes the override.
    """
    label_to_id = {label: category_id for category_id, label in categories}
    id_to_label = {category_id: label for category_id, label in categories}
    auto_label = t("classify_auto_option")
    type_labels = {code: t(f"type_{code}") for code in ("pos", "qpay", "transfer", "fee", "cash", "other")}
    source_labels = {
        "Automatic rule": t("src_rule"),
        "Automatic default": t("src_merchant"),
        "Manual": t("src_manual"),
        "Unclassified": t("src_none"),
    }
    original_ids = {
        int(row.id): None if pd.isna(row.category_id) else int(row.category_id)
        for row in transactions.itertuples()
    }
    manual_ids = {int(i) for i in transactions.loc[transactions["classified_by"] == "Manual", "id"]}
    # Category and its source come before the long description, so they stay in view.
    editable = pd.DataFrame(
        {
            "id": transactions["id"],
            "date": transactions["date"],
            "merchant": transactions["merchant"],
            "amount": transactions["amount"].astype(float),
            "category": [id_to_label.get(original_ids[int(i)]) for i in transactions["id"]],
            "classified_by": transactions["classified_by"].map(source_labels),
            "description": transactions["description"],
            "txn_type": transactions["txn_type"].map(type_labels).fillna(transactions["txn_type"]),
        }
    )
    version = st.session_state.get(f"{key}_version", 0)
    # Edits are stored by row position: a new row set (search, filter) needs a fresh editor.
    rows = hash(tuple(original_ids)) & 0xFFFFFFFF
    edited = st.data_editor(
        editable,
        hide_index=True,
        width="stretch",
        key=f"{key}_{version}_{rows}",
        disabled=[column for column in editable.columns if column != "category"],
        column_config={
            "id": None,
            "date": st.column_config.DateColumn(t("col_date"), width=90),
            "merchant": st.column_config.TextColumn(t("col_merchant"), width=180),
            "amount": st.column_config.NumberColumn(t("col_amount"), format="localized", step=1, width=90),
            "category": st.column_config.SelectboxColumn(
                t("col_category"), options=[auto_label, *label_to_id], required=False, width=320
            ),
            "classified_by": st.column_config.TextColumn(t("col_source"), width=130),
            "description": st.column_config.TextColumn(t("col_description"), width="medium"),
            "txn_type": st.column_config.TextColumn(t("col_type"), width="small"),
        },
    )

    overrides: dict[int, int] = {}
    resets: list[int] = []
    for row in edited.itertuples():
        transaction_id = int(row.id)
        if row.category == auto_label:
            if transaction_id in manual_ids:
                resets.append(transaction_id)
        elif pd.notna(row.category) and label_to_id[row.category] != original_ids[transaction_id]:
            overrides[transaction_id] = label_to_id[row.category]

    pending = len(overrides) + len(resets)
    with st.container(horizontal=True, vertical_alignment="center", key=f"{key}_bar"):
        save = st.button(
            t("classify_save"), type="primary", icon=":material/save:",
            disabled=not pending, key=f"{key}_save_{version}",
        )
        if pending:
            st.markdown(f":orange-badge[:material/edit: {t('classify_pending', count=pending)}]")
        else:
            st.caption(t("classify_hint"))
    if save:
        with engine().begin() as conn:
            updated = set_transaction_categories(conn, overrides)
            reset = reset_to_automatic(conn, resets)
        messages = [t("classify_updated", count=updated)] if updated else []
        if reset:
            messages.append(t("classify_reset_n", count=reset))
        st.session_state[flash_key] = " ".join(messages) or t("classify_no_changes")
        st.session_state[f"{key}_version"] = version + 1
        st.rerun()
