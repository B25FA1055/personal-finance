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
        savings_totals = goal_service.monthly_funding_totals(conn, budget_month)
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

    # Budget vs actual chart, including the savings plan for this month.
    if budgeted or savings_totals["planned"] or savings_totals["actual"]:
        with st.container(border=True, key="card_budget_vs_actual"):
            st.subheader(t("budget_vs_actual"))
            colors = palette()
            limit_label, spent_label = t("col_monthly_limit"), t("m_spent")
            comparison = [
                {
                    "category": category_name(item["category"]),
                    "planned": item["monthly_limit"],
                    "actual": item["spent"],
                }
                for item in budgeted
            ]
            comparison.append(
                {
                    "category": category_name(goal_service.SAVINGS),
                    "planned": savings_totals["planned"],
                    "actual": savings_totals["actual"],
                }
            )
            chart_data = pd.DataFrame(
                [
                    {"category": item["category"], "type": label, "amount": float(value)}
                    for item in comparison
                    for label, value in ((limit_label, item["planned"]), (spent_label, item["actual"]))
                ]
            )
            category_order = [item["category"] for item in comparison]
            chart = (
                alt.Chart(chart_data)
                .mark_bar(cornerRadiusEnd=3)
                .encode(
                    y=alt.Y("category:N", title=None, sort=category_order),
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
                .properties(height=min(320, max(160, 46 * len(comparison))))  # compact: at most 320px
            )
            st.altair_chart(style_chart(chart), width="stretch", theme=None)

    # Progress per budgeted category
    st.subheader(t("spending_progress"))
    if savings_totals["planned"] > 0:
        with st.container(border=True):
            ratio = savings_totals["actual"] / savings_totals["planned"]
            st.markdown(f"**{category_name(goal_service.SAVINGS)}**")
            st.progress(
                min(float(ratio), 1.0),
                text=t(
                    "progress_of",
                    spent=fmt_mnt(savings_totals["actual"]),
                    limit=fmt_mnt(savings_totals["planned"]),
                    pct=f"{ratio:.0%}",
                ),
            )
            if ratio >= 1:
                st.success(t("goal_savings_plan_met"))
            else:
                st.info(t("goal_savings_plan_remaining", amount=fmt_mnt(
                    savings_totals["planned"] - savings_totals["actual"]
                )))
    elif savings_totals["actual"] > 0:
        st.info(t("goal_savings_unplanned", amount=fmt_mnt(savings_totals["actual"])))
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
        funding_sources = {
            goal["id"]: goal_service.list_goal_funding_sources(conn, goal["id"])
            for goal in goals
        }

    if goals:
        total_monthly = sum((g["monthly_needed"] for g in goals if g["status"] not in ("done",)), Decimal("0"))
        total_planned = sum((g["monthly_plan"] for g in goals), Decimal("0"))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(t("goal_m_saved"), fmt_mnt(sum((g["saved"] for g in goals), Decimal("0"))), border=True,
                  icon=":material/savings:")
        c2.metric(t("goal_m_target"), fmt_mnt(sum((g["target"] for g in goals), Decimal("0"))), border=True,
                  icon=":material/flag:")
        c3.metric(t("goal_m_monthly"), fmt_mnt(total_monthly), border=True, icon=":material/calendar_month:",
                  help=t("goal_monthly_help"))
        c4.metric(t("goal_m_planned"), fmt_mnt(total_planned), border=True, icon=":material/account_balance:")

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
            m1, m2, m3, m4 = st.columns(4)
            m1.metric(
                t("goal_monthly_needed"),
                fmt_mnt(goal["monthly_needed"]) if goal["status"] != "done" else "—",
                help=t("goal_monthly_help"),
            )
            m2.metric(t("goal_planned_monthly"), fmt_mnt(goal["monthly_plan"]))
            m3.metric(t("goal_plan_shortfall"), fmt_mnt(goal["shortfall"]))
            m4.metric(
                t("goal_projected_date"),
                goal["projected_month"].strftime("%Y-%m") if goal["projected_month"] else "—",
            )
            st.caption(
                t(
                    "goal_plan_status_" + goal["plan_status"],
                    amount=fmt_mnt(goal["shortfall"]),
                    extra=fmt_mnt(goal["extra_per_month"]),
                )
            )
            st.caption(
                t("goal_breakdown", start=fmt_mnt(goal["starting"]), contributed=fmt_mnt(goal["contributed"]),
                  count=goal["contributions"], deadline=goal["deadline"], expected=f"{goal['expected_percent']:.0f}")
            )
            with st.expander(t("goal_funding_sources"), icon=":material/account_balance:"):
                st.caption(t("goal_funding_help"))
                source_rows = funding_sources[goal["id"]]
                source_table = pd.DataFrame(
                    {
                        "name": [row["name"] for row in source_rows],
                        "kind": [row["kind"] for row in source_rows],
                        "amount": [float(row["amount"]) for row in source_rows],
                        "start_month": [row["start_month"] for row in source_rows],
                        "end_month": [row["end_month"] for row in source_rows],
                    }
                )
                if source_table.empty:
                    source_table = pd.DataFrame(
                        {
                            "name": [""],
                            "kind": [None],
                            "amount": [None],
                            "start_month": [None],
                            "end_month": [None],
                        }
                    )
                with st.form(f"goal_funding_form_{goal['id']}"):
                    edited_sources = st.data_editor(
                        source_table,
                        hide_index=True,
                        width="stretch",
                        num_rows="dynamic",
                        column_config={
                            "name": st.column_config.TextColumn(
                                t("goal_funding_source"), max_chars=100, required=True
                            ),
                            "kind": st.column_config.SelectboxColumn(
                                t("goal_funding_kind"),
                                options=goal_service.FUNDING_KINDS,
                                format_func=lambda kind: t(f"goal_funding_kind_{kind}"),
                                required=True,
                            ),
                            "amount": st.column_config.NumberColumn(
                                t("goal_funding_amount"),
                                min_value=0.01,
                                step=1000.0,
                                format="localized",
                                required=True,
                            ),
                            "start_month": st.column_config.DateColumn(
                                t("goal_funding_start"),
                                format="YYYY-MM",
                                default=today.replace(day=1),
                                required=True,
                            ),
                            "end_month": st.column_config.DateColumn(
                                t("goal_funding_end"),
                                format="YYYY-MM",
                            ),
                        },
                        key=f"goal_funding_editor_{goal['id']}",
                    )
                    save_funding = st.form_submit_button(t("goal_funding_save"))
                if save_funding:
                    source_plan: list[dict] = []
                    incomplete = False
                    for row in edited_sources.itertuples():
                        name = "" if pd.isna(row.name) else str(row.name).strip()
                        kind = "" if pd.isna(row.kind) else str(row.kind)
                        amount = None if pd.isna(row.amount) else Decimal(str(row.amount))
                        start_month = None if pd.isna(row.start_month) else row.start_month
                        end_month = None if pd.isna(row.end_month) else row.end_month
                        if not name and not kind and amount is None and start_month is None and end_month is None:
                            continue
                        if not name or not kind or amount is None or start_month is None:
                            incomplete = True
                            break
                        source_plan.append(
                            {
                                "name": name,
                                "kind": kind,
                                "amount": amount,
                                "start_month": start_month,
                                "end_month": end_month,
                            }
                        )
                    if incomplete:
                        st.error(t("goal_funding_incomplete"))
                    else:
                        try:
                            with db.begin() as conn:
                                goal_service.save_goal_funding_sources(conn, goal["id"], source_plan)
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            st.session_state["budget_flash"] = t("goal_funding_saved")
                            st.rerun()
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
        funding_source_labels = {}
        for goal_id, sources in funding_sources.items():
            for source in sources:
                label = (
                    f"{goal_names[goal_id]} · {source['name']} "
                    f"({t('goal_funding_kind_' + source['kind'])})"
                )
                funding_source_labels[label] = (goal_id, source["id"])
        table = pd.DataFrame(
            {
                "id": [u["id"] for u in unassigned],
                "date": [u["date"] for u in unassigned],
                "description": [u["description"] for u in unassigned],
                "amount": [float(u["amount"]) for u in unassigned],
                "goal": [default_goal] * len(unassigned),
                "funding_source": [""] * len(unassigned),
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
                "funding_source": st.column_config.SelectboxColumn(
                    t("assign_funding_source"),
                    options=["", *funding_source_labels],
                    required=False,
                ),
            },
        )
        if st.button(t("assign_save"), type="primary"):
            ids_by_name = {name: gid for gid, name in goal_names.items()}
            assignments: dict[int, tuple[int, int | None]] = {}
            invalid_source = False
            for row in edited.itertuples():
                if pd.isna(row.goal):
                    continue
                goal_id = ids_by_name[row.goal]
                label = "" if pd.isna(row.funding_source) else str(row.funding_source)
                source_goal_id, source_id = funding_source_labels.get(label, (goal_id, None))
                if label and source_goal_id != goal_id:
                    invalid_source = True
                    break
                assignments[int(row.id)] = (goal_id, source_id if label else None)
            if invalid_source:
                st.error(t("assign_source_goal_mismatch"))
            else:
                with db.begin() as conn:
                    count = goal_service.assign(conn, assignments)
                st.session_state["budget_flash"] = t("assigned_n", count=count)
                st.rerun()
