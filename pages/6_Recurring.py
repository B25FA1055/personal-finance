"""Subscriptions and fixed bills: due alerts, add/edit, payment history."""

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from core import recurring
from core.i18n import t
from core.ui import category_options, engine, fmt_mnt, page, show_recurring_alerts

page("nav_recurring", "🔁")

db = engine()
today = date.today()
if flash := st.session_state.pop("recurring_flash", None):
    st.success(flash)

with db.begin() as conn:  # the check may auto-settle bills found in statements
    show_recurring_alerts(conn, today)
with db.connect() as conn:
    items = recurring.list_items(conn)
    categories = category_options(conn)
    past = recurring.history(conn)

label_to_id = {label: category_id for category_id, label in categories}
id_to_label = {category_id: label for category_id, label in categories}
freq_labels = {f: t(f"freq_{f}") for f in recurring.FREQUENCIES}
freq_codes = {label: code for code, label in freq_labels.items()}
dir_labels = {"out": t("dir_out"), "in": t("dir_in")}
dir_codes = {label: code for code, label in dir_labels.items()}

# --- Summary -----------------------------------------------------------------------
active = [i for i in items if i["is_active"]]
monthly_out = sum(
    (recurring.monthly_cost(i["amount"], i["frequency"]) for i in active if i["direction"] == "out"),
    Decimal("0"),
)
cols = st.columns(3)
cols[0].metric(t("rec_m_monthly"), fmt_mnt(monthly_out), border=True, icon=":material/event_repeat:")
cols[1].metric(t("rec_m_active"), len(active), border=True, icon=":material/subscriptions:")
cols[2].metric(
    t("rec_m_next"),
    f"{active[0]['next_due']} · {active[0]['name']}" if active else "—",
    border=True,
    icon=":material/event:",
)

# --- Add ---------------------------------------------------------------------------
with st.expander(t("rec_add"), expanded=not items, icon=":material/add:"):
    with st.form("recurring_add", clear_on_submit=True):
        name = st.text_input(t("rec_name"), placeholder=t("rec_name_placeholder"))
        c1, c2, c3 = st.columns(3)
        amount = c1.number_input(t("rec_amount"), min_value=0.0, step=1000.0, format="%.0f")
        frequency = c2.selectbox(t("rec_frequency"), recurring.FREQUENCIES, index=1, format_func=freq_labels.get)
        next_due = c3.date_input(t("rec_next_due"), value=today, format="YYYY-MM-DD")
        c4, c5, c6 = st.columns(3)
        direction = c4.segmented_control(
            t("col_direction"), ["out", "in"], default="out", format_func=dir_labels.get
        )
        category = c5.selectbox(t("col_category"), [None, *label_to_id], format_func=lambda v: v or "—")
        pattern = c6.text_input(t("rec_pattern"), help=t("rec_pattern_help"))
        if st.form_submit_button(t("rec_save_new"), type="primary"):
            try:
                with db.begin() as conn:
                    recurring.save_item(conn, {
                        "name": name, "amount": amount, "frequency": frequency,
                        "next_due": next_due, "direction": direction or "out",
                        "category_id": label_to_id.get(category), "match_pattern": pattern,
                    })
            except ValueError as exc:
                st.warning(t(f"rec_invalid_{exc}"))
            else:
                st.session_state["recurring_flash"] = t("rec_added", name=name.strip())
                st.rerun()

# --- View / edit -------------------------------------------------------------------
st.subheader(t("rec_list"))
if not items:
    st.info(t("rec_empty"))
else:
    table = pd.DataFrame(
        {
            "id": [i["id"] for i in items],
            "is_active": [i["is_active"] for i in items],
            "name": [i["name"] for i in items],
            "amount": [float(i["amount"]) for i in items],
            "direction": [dir_labels[i["direction"]] for i in items],
            "frequency": [freq_labels[i["frequency"]] for i in items],
            "next_due": [i["next_due"] for i in items],
            "category": [id_to_label.get(i["category_id"]) for i in items],
            "match_pattern": [i["match_pattern"] or "" for i in items],
            "monthly": [float(recurring.monthly_cost(i["amount"], i["frequency"])) for i in items],
        }
    )
    edited = st.data_editor(
        table,
        hide_index=True,
        width="stretch",
        key=f"recurring_editor_{st.session_state.get('recurring_version', 0)}",
        disabled=["monthly"],
        column_config={
            "id": None,
            "is_active": st.column_config.CheckboxColumn(t("rec_active")),
            "name": st.column_config.TextColumn(t("rec_name"), required=True),
            "amount": st.column_config.NumberColumn(t("rec_amount"), min_value=0.01, format="localized", step=1),
            "direction": st.column_config.SelectboxColumn(t("col_direction"), options=list(dir_codes), required=True),
            "frequency": st.column_config.SelectboxColumn(t("rec_frequency"), options=list(freq_codes), required=True),
            "next_due": st.column_config.DateColumn(t("rec_next_due"), format="YYYY-MM-DD", required=True),
            "category": st.column_config.SelectboxColumn(t("col_category"), options=list(label_to_id)),
            "match_pattern": st.column_config.TextColumn(t("rec_pattern"), help=t("rec_pattern_help")),
            "monthly": st.column_config.NumberColumn(t("rec_monthly"), format="localized"),
        },
    )
    st.caption(t("rec_edit_help"))
    if st.button(t("rec_save_changes"), type="primary"):
        changed = edited[(edited.fillna("") != table.fillna("")).any(axis=1)]  # NaN != NaN
        try:
            with db.begin() as conn:
                for row in changed.itertuples():
                    recurring.save_item(conn, {
                        "id": int(row.id), "name": row.name, "amount": row.amount,
                        "direction": dir_codes[row.direction], "frequency": freq_codes[row.frequency],
                        "next_due": pd.Timestamp(row.next_due).date(),
                        "category_id": label_to_id.get(row.category) if pd.notna(row.category) else None,
                        "match_pattern": row.match_pattern if pd.notna(row.match_pattern) else "",
                        "is_active": bool(row.is_active),
                    })
        except ValueError as exc:
            st.warning(t(f"rec_invalid_{exc}"))
        else:
            st.session_state["recurring_flash"] = t("rec_updated", count=len(changed))
            st.session_state["recurring_version"] = st.session_state.get("recurring_version", 0) + 1
            st.rerun()

# --- History -----------------------------------------------------------------------
st.subheader(t("rec_history"))
if not past:
    st.caption(t("rec_history_empty"))
else:
    st.dataframe(
        pd.DataFrame(past).assign(
            status=lambda df: df["status"].map(lambda s: t(f"rec_hist_{s}")),
            amount=lambda df: df["amount"].astype(float),
        ),
        hide_index=True,
        width="stretch",
        column_config={
            "due_date": st.column_config.DateColumn(t("rec_next_due"), format="YYYY-MM-DD"),
            "name": t("rec_name"),
            "status": t("rec_status"),
            "paid_on": st.column_config.DateColumn(t("rec_paid_on"), format="YYYY-MM-DD"),
            "amount": st.column_config.NumberColumn(t("col_amount"), format="localized"),
        },
    )
