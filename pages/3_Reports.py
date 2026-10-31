"""Income vs expense, spending by category, and top POS merchants."""

from datetime import date

import altair as alt
import streamlit as st

from core import report_export, reports
from core.i18n import category_name, current_language, t
from core.theme import palette, style_chart
from core.ui import engine, fmt_mnt, page

page("nav_reports", "📊", show_title=False)  # the title sits in the toolbar row below
st.html(
    """
    <style>
    /* No page top-padding override here: the header bar covers the top 3.75rem, so the
       shared theme's 4rem is the minimum that keeps the title and presets visible. */
    [class*="st-key-report_controls"] {
      gap: 0.35rem !important;
      margin-bottom: 0.1rem;
    }
    [class*="st-key-report_controls"] [data-testid="stHeading"] h1 {
      font-size: 1.45rem !important;
      line-height: 1.15;
      margin: 0;
      padding: 0;
    }
    [class*="st-key-report_controls"] [data-testid="stBaseButton"],
    [class*="st-key-report_controls"] [data-testid="stDownloadButton"] button {
      min-height: 2rem;
      padding-top: 0.2rem;
      padding-bottom: 0.2rem;
    }
    [class*="st-key-report_kpis"] [data-testid="stMetric"] {
      min-height: 4.25rem;
      padding: 0.25rem 0.4rem 0.2rem;
    }
    [class*="st-key-report_kpis"] [data-testid="stMetricLabel"],
    [class*="st-key-report_kpis"] [data-testid="stMetricLabel"] p {
      font-size: 13px !important;
      line-height: 1.2;
    }
    [class*="st-key-report_kpis"] [data-testid="stMetricValue"] {
      font-size: 18px !important;
      line-height: 1.2;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }
    [class*="st-key-report_kpis"] [data-testid="stMetricDelta"],
    [class*="st-key-report_kpis"] [data-testid="stMetricDeltaDescription"] {
      font-size: 11px !important;
      line-height: 1.15;
    }
    @media (max-width: 700px) {
      [class*="st-key-report_controls"] [data-testid="stHeading"] h1 {
        font-size: 1.3rem !important;
      }
    }
    </style>
    """
)

db = engine()

today = date.today()
with db.connect() as conn:
    first_date = reports.first_transaction_date(conn)

PERIOD_KEY = "report_period"
PRESET_KEY = "report_preset"


def matching_preset(period) -> str | None:
    """The quick range equal to period, if any (a hand-picked range has none)."""
    if not isinstance(period, (tuple, list)) or len(period) != 2:
        return None
    return next(
        (p for p in reports.PRESETS if tuple(period) == reports.preset_range(p, today, first_date)),
        None,
    )


if PERIOD_KEY not in st.session_state:
    st.session_state[PERIOD_KEY] = reports.preset_range("this_year", today, first_date)
if PRESET_KEY not in st.session_state:
    st.session_state[PRESET_KEY] = matching_preset(st.session_state[PERIOD_KEY])


def apply_preset() -> None:
    # Runs before the rerun draws the date picker, so the picker shows the new range.
    preset = st.session_state[PRESET_KEY]
    if preset is None:  # clicking the selected pill again clears it: keep range and selection
        st.session_state[PRESET_KEY] = matching_preset(st.session_state[PERIOD_KEY])
        return
    st.session_state[PERIOD_KEY] = reports.preset_range(preset, today, first_date)


def sync_preset() -> None:
    st.session_state[PRESET_KEY] = matching_preset(st.session_state[PERIOD_KEY])


# Toolbar: title, quick ranges, then date picker + exports as one group, so when the
# row wraps on narrow screens the export buttons stay next to the date picker.
export_labels = {key: t(key) for key in report_export.LABEL_KEYS}
export_lang = current_language()
with st.container(horizontal=True, vertical_alignment="center", gap="small", key="report_controls"):
    st.title(t("nav_reports"), width="content")
    st.segmented_control(
        t("quick_range"),
        reports.PRESETS,
        key=PRESET_KEY,
        format_func=lambda p: t(f"preset_{p}"),
        on_change=apply_preset,
        label_visibility="collapsed",
    )
    with st.container(horizontal=True, vertical_alignment="center", gap="small", width="content"):
        period = st.date_input(
            t("period"), key=PERIOD_KEY, format="YYYY-MM-DD", on_change=sync_preset,
            label_visibility="collapsed", width=210,
        )
        complete = isinstance(period, tuple) and len(period) == 2
        if complete:
            start, end = period
            stem = report_export.file_stem(start, end)
            # Built only when clicked (on a worker thread, so texts are translated above);
            # the click doesn't rerun the page.
            st.download_button(
                t("export_excel"),
                data=lambda: report_export.export(db, start, end, export_labels, "xlsx", export_lang),
                file_name=f"{stem}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/table_view:",
                help=t("export_help"),
                on_click="ignore",
            )
            st.download_button(
                t("export_pdf"),
                data=lambda: report_export.export(db, start, end, export_labels, "pdf", export_lang),
                file_name=f"{stem}.pdf",
                mime="application/pdf",
                icon=":material/picture_as_pdf:",
                help=t("export_help"),
                on_click="ignore",
            )
if not complete:
    st.info(t("pick_range"))
    st.stop()

with db.connect() as conn:
    monthly = reports.monthly_summary(conn, start, end)
    expense_cats = reports.by_category(conn, start, end, "expense")
    income_cats = reports.by_category(conn, start, end, "income")
    merchants = reports.top_merchants(conn, start, end, txn_type="pos")
    # Totals straight from SQL as Decimal (read_sql would coerce money to float).
    income, expense, _ = reports.period_totals(conn, start, end)
    prev_start, prev_end = reports.previous_period(start, end)
    prev_income, prev_expense, prev_count = reports.period_totals(conn, prev_start, prev_end)

if monthly.empty:
    st.info(t("no_txns_period"))
    st.stop()

# --- KPI cards: totals with change vs the previous period of equal length -------
net = income - expense
rate = float(net / income) * 100 if income else None
has_prev = prev_count > 0
prev_net = prev_income - prev_expense
prev_rate = float(prev_net / prev_income) * 100 if prev_income else None


def money_delta(now, before) -> str | None:
    if not has_prev:
        return None
    diff = now - before
    return ("+" if diff >= 0 else "-") + fmt_mnt(abs(diff))


compare = {
    "help": t("delta_help", start=prev_start, end=prev_end),
    "delta_description": t("vs_previous") if has_prev else None,
    "border": True,
}
rate_delta = (
    t("points", value=f"{rate - prev_rate:+.1f}")
    if has_prev and rate is not None and prev_rate is not None
    else None
)
with st.container(key="report_kpis"):
    cols = st.columns(4, gap="small")  # equal-width cards; Streamlit stacks them on phone-sized screens
    cols[0].metric(
        t("m_total_income"), fmt_mnt(income), money_delta(income, prev_income),
        icon=":material/trending_up:", **compare,
    )
    cols[1].metric(
        t("m_total_expense"), fmt_mnt(expense), money_delta(expense, prev_expense),
        delta_color="inverse", icon=":material/trending_down:", **compare,
    )
    cols[2].metric(
        t("m_net_balance"), fmt_mnt(net), money_delta(net, prev_net),
        icon=":material/account_balance_wallet:", **compare,
    )
    cols[3].metric(
        t("m_savings_rate"), f"{rate:.1f}%" if rate is not None else "—", rate_delta,
        icon=":material/savings:", **compare,
    )

CHART_HEIGHT = 280  # px; category charts may grow to MAX_CHART_HEIGHT for long lists
MAX_CHART_HEIGHT = 320
money = alt.Axis(format=",.0f")
colors = palette()
income_label, expense_label = t("kind_income"), t("kind_expense")
category_columns = {
    "category": t("col_category"),
    "total": st.column_config.NumberColumn(t("col_total"), format="localized", step=1),
    "pct": st.column_config.NumberColumn(t("col_pct"), format="%.1f"),
    "count": t("col_count"),
}

# --- Monthly income vs expense (full width) --------------------------------------
with st.container(border=True, key="card_monthly"):
    st.subheader(t("monthly_chart"))
    chart_data = monthly.assign(
        month=monthly["month"].astype(str).str[:7],
        income=monthly["income"].astype(float),
        expense=monthly["expense"].astype(float),
    ).melt(id_vars="month", value_vars=["income", "expense"], var_name="type", value_name="amount")
    chart_data["type"] = chart_data["type"].map({"income": income_label, "expense": expense_label})
    monthly_chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("month:N", title=None, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("type:N", sort=[income_label, expense_label]),
            y=alt.Y("amount:Q", title="₮", axis=money),
            color=alt.Color(
                "type:N",
                scale=alt.Scale(domain=[income_label, expense_label], range=[colors.income, colors.expense]),
                legend=alt.Legend(title=None, orient="top", direction="horizontal"),
            ),
            tooltip=[
                alt.Tooltip("month:N", title=t("col_month")),
                alt.Tooltip("type:N", title=t("col_type")),
                alt.Tooltip("amount:Q", title=t("col_amount"), format=",.0f"),
            ],
        )
        .properties(height=CHART_HEIGHT)
    )
    st.altair_chart(style_chart(monthly_chart), width="stretch", theme=None)

# --- Spending by category: bar + donut side by side ------------------------------
with st.container(border=True, key="card_categories"):
    st.subheader(t("spending_by_category"))
    if expense_cats.empty:
        st.caption(t("no_expenses"))
    else:
        cats = expense_cats.assign(
            total=expense_cats["total"].astype(float), category=expense_cats["category"].map(category_name)
        )
        # ~30px per category bar, capped so the card stays on screen.
        height = min(MAX_CHART_HEIGHT, max(220, 30 * len(cats)))
        tooltip = [
            alt.Tooltip("category:N", title=t("col_category")),
            alt.Tooltip("total:Q", title=t("col_total"), format=",.0f"),
            alt.Tooltip("pct:Q", title=t("col_pct"), format=".1f"),
            alt.Tooltip("count:Q", title=t("col_count")),
        ]
        order = list(cats["category"])
        base = alt.Chart(cats).encode(
            y=alt.Y("category:N", sort=order, title=None),
            x=alt.X(
                "total:Q", title="₮", axis=alt.Axis(format=",.0f", tickCount=5),
                scale=alt.Scale(domain=[0, float(cats["total"].max()) * 1.18]),  # room for labels
            ),
            tooltip=tooltip,
        )
        bar_chart = (
            base.mark_bar(cornerRadiusEnd=4)
            + base.mark_text(align="left", dx=4, color=colors.text, fontSize=11).encode(
                text=alt.Text("total:Q", format=",.0f")
            )
        ).properties(height=height)
        donut_chart = (
            alt.Chart(cats)
            .mark_arc(innerRadius=70, padAngle=0.01, cornerRadius=3)
            .encode(
                theta="total:Q",
                color=alt.Color(
                    "category:N",
                    sort=order,
                    legend=alt.Legend(title=None, orient="right", symbolLimit=0, labelLimit=170),
                ),
                order=alt.Order("total:Q", sort="descending"),
                tooltip=tooltip,
            )
            .properties(height=height)
        )
        left, right = st.columns(2, gap="large")
        left.altair_chart(style_chart(bar_chart), width="stretch", theme=None)
        right.altair_chart(style_chart(donut_chart), width="stretch", theme=None)
        with st.expander(t("subcategory_breakdown"), icon=":material/table_rows:"):
            st.dataframe(
                cats[["category", "total", "pct", "count"]],
                hide_index=True,
                width="stretch",
                column_config=category_columns,
            )
            with db.connect() as conn:
                subs = reports.by_category(conn, start, end, "expense", level="sub")
            st.dataframe(
                subs.assign(
                    total=subs["total"].astype(float),
                    main=subs["main"].map(category_name),
                    category=subs["category"].map(lambda c: c if c == "—" else category_name(c)),
                )[["main", "category", "total", "pct", "count"]],
                hide_index=True,
                width="stretch",
                column_config={**category_columns, "main": t("col_main_category"), "category": t("col_subcategory")},
            )

# --- Top merchants and income sources --------------------------------------------
def table_height(rows: int) -> int:
    return min(320, 38 + 35 * max(rows, 1))


left, right = st.columns(2)
with left.container(border=True, key="card_merchants"):
    st.subheader(t("top_pos"))
    st.dataframe(
        merchants.assign(
            total=merchants["total"].astype(float),
            txn_type=merchants["txn_type"].map(lambda code: t(f"type_{code}")),
        ),
        hide_index=True,
        width="stretch",
        column_config={
            "merchant": t("col_merchant"),
            "txn_type": t("col_type"),
            "count": t("col_count"),
            "total": st.column_config.NumberColumn(t("col_total"), format="localized", step=1),
        },
        height=table_height(len(merchants)),
    )
with right.container(border=True, key="card_income"):
    st.subheader(t("income_by_category"))
    st.dataframe(
        income_cats.assign(
            total=income_cats["total"].astype(float), category=income_cats["category"].map(category_name)
        )[["category", "total", "pct", "count"]],
        hide_index=True,
        width="stretch",
        column_config=category_columns,
        height=table_height(len(income_cats)),
    )
