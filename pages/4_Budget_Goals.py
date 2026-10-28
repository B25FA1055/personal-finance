"""Monthly budgets per main category and long-term savings goals."""

from datetime import date, timedelta
from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from core import goals as goal_service
from core.budget_service import (
    archive_savings_goal,
    copy_previous_month_budgets,
    create_savings_goal,
    expense_categories,
    monthly_budget_progress,
    normalize_month,
    save_monthly_budgets,
    update_savings_goal,
)
from core.i18n import category_name, t
from core.theme import palette, style_chart
from core.ui import engine, fmt_mnt, page, show_budget_alerts

page("nav_budget", "🎯")

db = engine()
today = date.today()
if flash := st.session_state.pop("budget_flash", None):
    st.success(flash)

tab_budget, tab_goals = st.tabs([t("tab_budget"), t("tab_goals")])

# --- Monthly budget ------------------------------------------------------------------
with tab_budget:
    selected_date = st.date_input(t("budget_month"), value=today.replace(day=1), format="YYYY-MM-DD")
    budget_month = normalize_month(selected_date)
    with db.connect() as conn:
        categories = expense_categories(conn)
        progress = monthly_budget_progress(conn, budget_month)
        show_budget_alerts(conn, budget_month, link=False)

    st.subheader(t("monthly_budgets", month=f"{budget_month:%Y-%m}"))
    if not categories:
        st.warning(t("no_expense_categories"))
    else:
        current_limits = {
            int(item["category_id"]): item["monthly_limit"]
            for item in progress
            if item["category_id"] is not None and item["monthly_limit"] is not None
        }
        if not current_limits and st.button(t("copy_budgets"), icon=":material/content_copy:"):
            with db.begin() as conn:
                copied = copy_previous_month_budgets(conn, budget_month)
            if copied:
                st.session_state["budget_flash"] = t("budgets_copied", count=copied)
                st.rerun()
            st.info(t("nothing_to_copy"))

        budget_table = pd.DataFrame(
            [
                {
                    "category_id": category_id,
                    "category": category_name(name),
                    "monthly_limit": float(current_limits[category_id]) if category_id in current_limits else None,
                }
                for category_id, name in categories
            ]
        )
        with st.form(f"budget_form_{budget_month.isoformat()}"):
            edited_budgets = st.data_editor(
                budget_table,
                hide_index=True,
                width="stretch",
                disabled=["category_id", "category"],
                column_config={
                    "category_id": None,
                    "category": st.column_config.TextColumn(t("col_category")),
                    "monthly_limit": st.column_config.NumberColumn(
                        t("col_monthly_limit"), min_value=0.01, step=1000.0, format="localized",
                        help=t("limit_help"),
                    ),
                },
            )
            save_budgets = st.form_submit_button(t("save_limits"), type="primary")
        if save_budgets:
            values = {
                int(row.category_id): (
                    None if pd.isna(row.monthly_limit)
                    else Decimal(str(row.monthly_limit)).quantize(Decimal("0.01"))
                )
                for row in edited_budgets.itertuples()
            }
            with db.begin() as conn:
                saved_count = save_monthly_budgets(conn, budget_month, values)
            st.session_state["budget_flash"] = t("limits_saved", count=saved_count)
            st.rerun()

    budgeted = [item for item in progress if item["monthly_limit"] is not None]
    unbudgeted = [item for item in progress if item["monthly_limit"] is None and item["spent"] > 0]

    # Budget vs actual chart
    if budgeted:
        with st.container(border=True, key="card_budget_vs_actual"):
            st.subheader(t("budget_vs_actual"))
            colors = palette()
            limit_label, spent_label = t("col_monthly_limit"), t("m_spent")
            chart_data = pd.DataFrame(
                [
                    {"category": category_name(item["category"]), "type": label, "amount": float(value)}
                    for item in budgeted
                    for label, value in ((limit_label, item["monthly_limit"]), (spent_label, item["spent"]))
                ]
            )
            chart = (
                alt.Chart(chart_data)
                .mark_bar(cornerRadiusEnd=3)
                .encode(
                    y=alt.Y("category:N", title=None, sort=[category_name(i["category"]) for i in budgeted]),
                    yOffset=alt.YOffset("type:N", sort=[limit_label, spent_label]),
                    x=alt.X("amount:Q", title="₮", axis=alt.Axis(format=",.0f", tickCount=5)),
                    color=alt.Color(
                        "type:N",
                        scale=alt.Scale(domain=[limit_label, spent_label], range=[colors.border, colors.expense]),
                        legend=alt.Legend(title=None, orient="top"),
                    ),
                    tooltip=[
                        alt.Tooltip("category:N", title=t("col_category")),
                        alt.Tooltip("type:N", title=t("col_type")),
                        alt.Tooltip("amount:Q", title=t("col_amount"), format=",.0f"),
                    ],
                )
                .properties(height=min(320, max(160, 46 * len(budgeted))))  # compact: at most 320px
            )
            st.altair_chart(style_chart(chart), width="stretch", theme=None)

    # Progress per budgeted category
    st.subheader(t("spending_progress"))
    if not budgeted:
        st.info(t("no_budgets_yet"))
    for item in budgeted:
        with st.container(border=True):
            limit, spent, remaining = item["monthly_limit"], item["spent"], item["remaining"]
            ratio = item["percent_used"]
            st.markdown(f"**{category_name(item['category'])}**")
            st.progress(
                min(float(ratio), 1.0),
                text=t("progress_of", spent=fmt_mnt(spent), limit=fmt_mnt(limit), pct=f"{ratio:.0%}"),
            )
            spent_col, remaining_col = st.columns(2)
            spent_col.metric(t("m_spent"), fmt_mnt(spent))
            remaining_col.metric(
                t("m_remaining") if remaining >= 0 else t("m_over_budget"),
                fmt_mnt(remaining if remaining >= 0 else -remaining),
            )
            if item["status"] == "exceeded":
                st.error(t("budget_exceeded", amount=fmt_mnt(-remaining)))
            elif item["status"] == "approaching":
                st.warning(t("budget_approaching"))
    if unbudgeted:
        with st.expander(t("unbudgeted_spending", count=len(unbudgeted))):
            for item in sorted(unbudgeted, key=lambda i: -i["spent"]):
                label = category_name(item["category"])
                st.markdown(f"- {label}: **{fmt_mnt(item['spent'])}**")

# --- Long-term goals -----------------------------------------------------------------
GOAL_ICONS = {
    "emergency": ":material/health_and_safety:",
    "education": ":material/school:",
    "purchase": ":material/shopping_bag:",
    "travel": ":material/flight:",
    "other": ":material/flag:",
}
STATUS_COLORS = {"done": "green", "ahead": "green", "on_track": "blue", "behind": "orange", "overdue": "red"}

with tab_goals:
    with db.connect() as conn:
        goals = goal_service.goal_progress(conn, today)
        unassigned = goal_service.unassigned_savings(conn)

    if goals:
        total_monthly = sum((g["monthly_needed"] for g in goals if g["status"] not in ("done",)), Decimal("0"))
        c1, c2, c3 = st.columns(3)
        c1.metric(t("goal_m_saved"), fmt_mnt(sum((g["saved"] for g in goals), Decimal("0"))), border=True,
                  icon=":material/savings:")
        c2.metric(t("goal_m_target"), fmt_mnt(sum((g["target"] for g in goals), Decimal("0"))), border=True,
                  icon=":material/flag:")
        c3.metric(t("goal_m_monthly"), fmt_mnt(total_monthly), border=True, icon=":material/calendar_month:",
                  help=t("goal_monthly_help"))

    with st.expander(t("create_goal"), expanded=not goals, icon=":material/add:"):
        with st.form("create_savings_goal", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            goal_name = c1.text_input(t("goal_name"), max_chars=120, placeholder=t("goal_name_placeholder"))
            goal_type = c2.selectbox(t("goal_type"), goal_service.GOAL_TYPES,
                                     format_func=lambda g: t(f"goal_type_{g}"))
            c3, c4, c5 = st.columns(3)
            target_amount = c3.number_input(t("target_amount"), min_value=0.01, step=100000.0, value=1000000.0)
            current_amount = c4.number_input(t("already_saved"), min_value=0.0, step=10000.0, value=0.0)
            deadline = c5.date_input(t("deadline"), value=today + timedelta(days=365), min_value=today,
                                     format="YYYY-MM-DD")
            create = st.form_submit_button(t("create_goal"), type="primary")
        if create:
            try:
                with db.begin() as conn:
                    create_savings_goal(conn, goal_name, Decimal(str(target_amount)),
                                        Decimal(str(current_amount)), deadline, goal_type)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state["budget_flash"] = t("goal_created", name=goal_name.strip())
                st.rerun()

    if not goals:
        st.info(t("no_goals"))
    for goal in goals:
        with st.container(border=True, key=f"card_goal_{goal['id']}"):
            head, badge = st.columns([4, 1], vertical_alignment="center")
            head.markdown(f"{GOAL_ICONS[goal['goal_type']]} **{goal['name']}** · {t('goal_type_' + goal['goal_type'])}")
            badge.markdown(f":{STATUS_COLORS[goal['status']]}-badge[{t('goal_status_' + goal['status'])}]")
            st.progress(
                min(goal["percent"] / 100, 1.0),
                text=t("progress_of", spent=fmt_mnt(goal["saved"]), limit=fmt_mnt(goal["target"]),
                       pct=f"{goal['percent']:.0f}%"),
            )
            m1, m2, m3 = st.columns(3)
            m1.metric(t("goal_monthly_needed"), fmt_mnt(goal["monthly_needed"]) if goal["status"] != "done" else "—")
            m2.metric(t("goal_months_left"), goal["months_left"])
            m3.metric(t("m_remaining"), fmt_mnt(goal["remaining"]))
            st.caption(
                t("goal_breakdown", start=fmt_mnt(goal["starting"]), contributed=fmt_mnt(goal["contributed"]),
                  count=goal["contributions"], deadline=goal["deadline"], expected=f"{goal['expected_percent']:.0f}")
            )
            with st.form(f"goal_form_{goal['id']}"):
                starting = st.number_input(t("goal_starting"), min_value=0.0, step=10000.0,
                                           value=float(goal["starting"]), key=f"goal_start_{goal['id']}",
                                           help=t("goal_starting_help"))
                u, a = st.columns(2)
                update_goal = u.form_submit_button(t("update_saved"))
                archive_goal = a.form_submit_button(t("archive_goal"))
            if update_goal:
                with db.begin() as conn:
                    update_savings_goal(conn, goal["id"], Decimal(str(starting)))
                st.session_state["budget_flash"] = t("goal_updated", name=goal["name"])
                st.rerun()
            if archive_goal:
                with db.begin() as conn:
                    archive_savings_goal(conn, goal["id"])
                st.session_state["budget_flash"] = t("goal_archived", name=goal["name"])
                st.rerun()

    # Savings transactions -> goals
    st.subheader(t("assign_title"))
    st.caption(t("assign_help", savings=category_name("Хуримтлал")))
    if not unassigned:
        st.info(t(
            "assign_none",
            savings_path=f"{category_name('Шилжүүлэг & Хуримтлал')} › {category_name('Хуримтлал')}",
        ))
    elif not goals:
        st.info(t("assign_need_goal"))
    else:
        goal_names = {g["id"]: g["name"] for g in goals}
        default_goal = goals[0]["name"] if len(goals) == 1 else None
        table = pd.DataFrame(
            {
                "id": [u["id"] for u in unassigned],
                "date": [u["date"] for u in unassigned],
                "description": [u["description"] for u in unassigned],
                "amount": [float(u["amount"]) for u in unassigned],
                "goal": [default_goal] * len(unassigned),
            }
        )
        edited = st.data_editor(
            table,
            hide_index=True,
            width="stretch",
            disabled=["date", "description", "amount"],
            key=f"assign_{len(unassigned)}_{len(goals)}",
            column_config={
                "id": None,
                "date": st.column_config.DateColumn(t("col_date"), format="YYYY-MM-DD"),
                "description": t("col_description"),
                "amount": st.column_config.NumberColumn(t("col_amount"), format="localized"),
                "goal": st.column_config.SelectboxColumn(t("assign_goal"), options=list(goal_names.values())),
            },
        )
        if st.button(t("assign_save"), type="primary"):
            ids_by_name = {name: gid for gid, name in goal_names.items()}
            assignments = {
                int(row.id): ids_by_name[row.goal] for row in edited.itertuples() if pd.notna(row.goal)
            }
            with db.begin() as conn:
                count = goal_service.assign(conn, assignments)
            st.session_state["budget_flash"] = t("assigned_n", count=count)
            st.rerun()
