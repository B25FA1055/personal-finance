"""FinTrack home page."""

from datetime import date
from decimal import Decimal

import streamlit as st

from core import reports
from core.dti import DTI_TARGET_PERCENT, monthly_dti
from core.i18n import t
from core.ui import engine, fmt_mnt, page, show_budget_alerts, show_recurring_alerts

page("nav_home", "💰", title="FinTrack")

today = date.today()
month_start = today.replace(day=1)
with engine().connect() as conn:
    metrics = reports.home_metrics(conn, month_start, today)
    dti = monthly_dti(conn, today)
    income, expense, _ = reports.period_totals(conn, month_start, today)

# --- KPI cards: this month so far ----------------------------------------------
net = income - expense
rate = float(net / income) * 100 if income else None
st.html(
    """
    <style>
    [class*="st-key-home_kpis"] [data-testid="stMetric"] {
      min-height: 4.25rem;
      padding: 0.25rem 0.4rem 0.2rem;
    }
    [class*="st-key-home_kpis"] [data-testid="stMetricLabel"],
    [class*="st-key-home_kpis"] [data-testid="stMetricLabel"] p {
      font-size: 13px !important;
      line-height: 1.2;
    }
    [class*="st-key-home_kpis"] [data-testid="stMetricValue"] {
      font-size: 18px !important;
      line-height: 1.2;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }
    </style>
    """
)
with st.container(key="home_kpis"):
    cols = st.columns(4, gap="small")
    cols[0].metric(t("m_total_income"), fmt_mnt(income), icon=":material/trending_up:")
    cols[1].metric(t("m_total_expense"), fmt_mnt(expense), icon=":material/trending_down:")
    cols[2].metric(t("m_net_balance"), fmt_mnt(net), icon=":material/account_balance_wallet:")
    cols[3].metric(
        t("m_savings_rate"), f"{rate:.1f}%" if rate is not None else "—", icon=":material/savings:"
    )
last_import = metrics["last_import"]
st.caption(
    t(
        "home_counts",
        count=f"{metrics['transactions']:,}",
        review=f"{metrics['unclassified']:,}",
        last=last_import.strftime("%Y-%m-%d") if last_import else "—",
    )
)

# --- DTI benchmark card ----------------------------------------------------------
DTI_BADGE_COLORS = {"safe": "green", "moderate": "orange", "high_risk": "red", "unavailable": "gray"}
ratio = dti["ratio_percent"]
with st.container(border=True, key="card_dti"):
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.subheader(t("dti_title"), width="content")
        st.badge(t(f"dti_badge_{dti['status']}"), color=DTI_BADGE_COLORS[dti["status"]])
        st.caption(
            f"{t('dti_month', month=f'{today:%Y-%m}')} · "  # %B would always be English
            f"{t('dti_benchmark', limit=f'{DTI_TARGET_PERCENT:.0f}')}"
        )
    dti_cols = st.columns(3)
    dti_cols[0].metric(
        t("dti_title"),
        f"{ratio:.1f}%" if ratio is not None else "—",
        delta=f"{ratio - DTI_TARGET_PERCENT:+.1f} pp" if ratio is not None else None,
        delta_color="inverse",
        delta_description=t("dti_limit", limit=f"{DTI_TARGET_PERCENT:.0f}"),
    )
    dti_cols[1].metric(t("dti_income"), fmt_mnt(dti["gross_income"]))
    dti_cols[2].metric(t("dti_debt"), fmt_mnt(dti["monthly_debt_payments"]))

    if dti["status"] == "unavailable":
        st.info(t("dti_unavailable"))
    else:
        st.progress(
            min(float(ratio / DTI_TARGET_PERCENT), 1.0),
            text=f"{ratio:.1f}% / {DTI_TARGET_PERCENT:.0f}%",
        )
        if dti["status"] == "moderate":
            st.caption(t("dti_moderate_tip"))
        elif dti["status"] == "high_risk":
            st.warning(t("dti_high_alert"))
            reduction = (
                dti["monthly_debt_payments"]
                - dti["gross_income"] * DTI_TARGET_PERCENT / Decimal("100")
            )
            st.info(t("dti_reduce", amount=fmt_mnt(reduction)))

with engine().connect() as conn:
    show_budget_alerts(conn, today.replace(day=1))
with engine().begin() as conn:  # may auto-settle bills found in statements
    show_recurring_alerts(conn, today)

st.divider()
st.page_link("pages/1_Upload.py", label=t("nav_upload"), icon="📤")
st.page_link("pages/2_Classify.py", label=t("home_classify_link"), icon="🏷️")
st.page_link("pages/3_Reports.py", label=t("nav_reports"), icon="📊")
st.page_link("pages/4_Budget_Goals.py", label=t("nav_budget"), icon="🎯")
st.page_link("pages/6_Recurring.py", label=t("nav_recurring"), icon="🔁")
st.page_link("pages/5_AI_Assistant.py", label=t("nav_ai"), icon="🤖")
