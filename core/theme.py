"""Sidebar theme switcher: colour palettes applied with CSS, plus matching chart styling."""

from dataclasses import dataclass

import altair as alt
import streamlit as st

from core.i18n import persisted_choice, sync_url, t


@dataclass(frozen=True)
class Palette:
    dark: bool
    primary: str  # buttons, active tab, progress; must contrast with white text
    background: str
    secondary: str  # inputs, metric cards
    text: str
    border: str
    sidebar: str
    sidebar_text: str
    sidebar_input: str
    income: str
    expense: str
    chart: tuple[str, ...]  # categorical chart colours


THEMES: dict[str, Palette] = {
    "light": Palette(
        dark=False, primary="#ff4b4b", background="#ffffff", secondary="#f0f2f6",
        text="#31333f", border="#d9dce3", sidebar="#f0f2f6", sidebar_text="#31333f",
        sidebar_input="#ffffff", income="#2e9e6a", expense="#d1495b",
        chart=("#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2", "#b279a2", "#eeca3b", "#9d755d", "#ff9da6", "#79706e"),
    ),
    "dark": Palette(
        dark=True, primary="#e5484d", background="#0e1117", secondary="#1b1e27",
        text="#fafafa", border="#3a3d48", sidebar="#1b1e27", sidebar_text="#fafafa",
        sidebar_input="#262a35", income="#4cc38a", expense="#ff6b6b",
        chart=("#60a5fa", "#fbbf24", "#34d399", "#f87171", "#a78bfa", "#22d3ee", "#f472b6", "#a3a3a3", "#fb923c", "#4ade80"),
    ),
    "pastel": Palette(
        dark=False, primary="#a8578a", background="#fdf8f6", secondary="#f6ebf1",
        text="#3d3a4b", border="#ead7e2", sidebar="#eef6ef", sidebar_text="#3d3a4b",
        sidebar_input="#ffffff", income="#5f9f84", expense="#d27a8c",
        chart=("#b5578f", "#6aa58b", "#e09f6b", "#7f8fcf", "#d6a7c8", "#9ccfb0", "#c9a66b", "#a3b4e8", "#e6b8a2", "#8e7cc3"),
    ),
    "emerald": Palette(
        dark=False, primary="#047857", background="#f6fbf8", secondary="#e3f2ea",
        text="#10291d", border="#c6e3d3", sidebar="#0f5132", sidebar_text="#e8f5ee",
        sidebar_input="#17663f", income="#059669", expense="#c2410c",
        chart=("#047857", "#34d399", "#0e7490", "#a3e635", "#f59e0b", "#6d28d9", "#be123c", "#64748b", "#14b8a6", "#ca8a04"),
    ),
    "blue": Palette(
        dark=False, primary="#1d4ed8", background="#f7f9fc", secondary="#e8eef7",
        text="#1b2a41", border="#cfd9e8", sidebar="#1e3a5f", sidebar_text="#e6eef8",
        sidebar_input="#28507f", income="#15803d", expense="#b91c1c",
        chart=("#1d4ed8", "#0891b2", "#64748b", "#f59e0b", "#7c3aed", "#059669", "#db2777", "#94a3b8", "#ea580c", "#4f46e5"),
    ),
    "modern_dark": Palette(
        dark=True, primary="#7c5cff", background="#111318", secondary="#1c1f26",
        text="#e6e8ee", border="#2a2e37", sidebar="#0b0c10", sidebar_text="#e6e8ee",
        sidebar_input="#1c1f26", income="#2dd4bf", expense="#fb7185",
        chart=("#7c5cff", "#2dd4bf", "#fbbf24", "#fb7185", "#38bdf8", "#a3e635", "#f472b6", "#94a3b8", "#f97316", "#c084fc"),
    ),
}
DEFAULT_THEME = "light"

# Plain session key (not a widget key) so the choice survives page switches.
_STATE_KEY = "ui_theme"
_WIDGET_KEY = "_theme_selector"


def current_theme() -> str:
    return persisted_choice(_STATE_KEY, "theme", THEMES, DEFAULT_THEME)


def palette() -> Palette:
    return THEMES[current_theme()]


def theme_selector() -> None:
    """Sidebar theme picker; kept for the session and in the URL."""

    def remember_choice() -> None:
        st.session_state[_STATE_KEY] = st.session_state[_WIDGET_KEY]

    names = list(THEMES)
    st.sidebar.selectbox(
        "🎨 " + t("theme"),
        names,
        index=names.index(current_theme()),
        format_func=lambda name: t(f"theme_{name}"),
        key=_WIDGET_KEY,
        on_change=remember_choice,
    )
    sync_url("theme", current_theme(), DEFAULT_THEME)
    # Canvas tables and date pickers follow Streamlit's own light/dark base, not CSS.
    if palette().dark and st.context.theme.type != "dark":
        st.sidebar.caption(t("theme_dark_tip"))


def apply_theme() -> None:
    """Inject card styling for every theme, plus palette CSS for non-default themes."""
    p = palette()
    css = _card_css(p)
    if current_theme() != DEFAULT_THEME:
        css = _css(p) + css
    st.html(f"<style>{css}</style>")


def _mix(a: str, b: str, weight_b: float) -> str:
    """Blend two #rrggbb colours (weight_b of b)."""
    channels = [
        round(int(a[i : i + 2], 16) * (1 - weight_b) + int(b[i : i + 2], 16) * weight_b)
        for i in (1, 3, 5)
    ]
    return "#" + "".join(f"{c:02x}" for c in channels)


def _card_css(p: Palette) -> str:
    """Compact layout for every theme: page header, section cards, metric cards."""
    shadow = "0 2px 10px rgba(0, 0, 0, 0.45)" if p.dark else "0 1px 3px rgba(16, 24, 40, 0.06), 0 4px 14px rgba(16, 24, 40, 0.06)"
    return f"""
/* Page header: Streamlit reserves 6rem above the content; the opaque header bar is 3.75rem. */
/* 4rem, not less: anything above the header's bottom edge is hidden under it. */
[data-testid="stMainBlockContainer"] {{ padding-top: 4rem; padding-bottom: 2rem; }}
/* Tighter vertical rhythm: smaller gaps between blocks, dividers and sub-headings. */
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] {{ gap: 0.7rem; }}
[data-testid="stMainBlockContainer"] hr {{ margin: 0.5rem 0; }}
[data-testid="stMainBlockContainer"] [data-testid="stHeading"] h2,
[data-testid="stMainBlockContainer"] [data-testid="stHeading"] h3 {{ padding: 0.1rem 0 0.25rem; }}
[data-testid="stMainBlockContainer"] [data-testid="stHeading"] h2 {{ font-size: 1.35rem; }}
/* Section headings (st.subheader); the card rule below makes in-card ones smaller still. */
[data-testid="stMainBlockContainer"] [data-testid="stHeading"] h3 {{ font-size: 1.2rem; }}
[data-testid="stMainBlockContainer"] [data-testid="stHeading"] h1 {{
  font-size: 1.9rem;
  padding: 0.1rem 0 0.3rem;
}}

/* Section cards (containers keyed 'card_...') with a smaller heading */
[class*="st-key-card_"] {{
  background-color: {_mix(p.background, p.secondary, 0.35)};
  border: 1px solid {p.border} !important;
  border-radius: 14px;
  box-shadow: {shadow};
  padding: 0.75rem 1rem 0.5rem;
}}
[class*="st-key-card_"] [data-testid="stHeading"] h3 {{
  font-size: 1.1rem;
  padding: 0.1rem 0 0.35rem;
}}

/* Metric cards: one padding only (bordered metrics add their own inner padding),
   13px labels and 20px values so amounts like 325,225₮ fit without being cut off. */
[data-testid="stMetric"] {{
  background-color: {p.secondary};
  border: 1px solid {p.border};
  border-left: 4px solid {p.primary};
  border-radius: 10px;
  padding: 0.5rem 0.75rem 0.45rem;
  box-shadow: {shadow};
}}
[data-testid="stMetric"] > div {{ padding: 0 !important; }}
[data-testid="stMetric"] [data-testid="stMetricLabel"],
[data-testid="stMetric"] [data-testid="stMetricLabel"] p {{ font-size: 13px; }}
/* In narrow cards a long label wraps to a second line instead of ending in "…". */
[data-testid="stMetric"] [data-testid="stMetricLabel"] * {{
  white-space: normal !important;
  text-overflow: clip !important;
}}
[data-testid="stMetric"] [data-testid="stMetricIcon"] {{ font-size: 1rem; }}
/* Label text takes the free width; the "?" help icon only its own size. */
[data-testid="stMetric"] [data-testid="stMetricLabel"] {{
  grid-template-columns: minmax(0, 1fr) auto !important;
}}
@media (max-width: 1200px) {{
  /* Narrow cards: give the label the icon's room so words don't break mid-word. */
  [data-testid="stMetric"] [data-testid="stMetricLabel"] :has(> [data-testid="stMetricIcon"]) {{
    display: none;
  }}
}}
[data-testid="stMetric"] [data-testid="stMetricValue"] {{
  font-size: 20px;
  font-weight: 600;
  line-height: 1.3;
  white-space: nowrap;               /* amounts never break across lines */
  font-variant-numeric: tabular-nums; /* digits line up between cards */
}}
[data-testid="stMetric"] [data-testid="stMetricDelta"],
[data-testid="stMetric"] [data-testid="stMetricDeltaDescription"] {{ font-size: 12px; }}
"""


def _css(p: Palette) -> str:
    primary_buttons = (
        '[data-testid="stBaseButton-primary"], '
        '[data-testid="stBaseButton-primaryFormSubmit"]'
    )
    secondary_buttons = (
        '[data-testid="stBaseButton-secondary"], '
        '[data-testid="stBaseButton-secondaryFormSubmit"]'
    )
    inputs = (
        '[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], '
        '[data-baseweb="select"] > div, [data-baseweb="input"] input, textarea'
    )
    return f"""
:root {{
  --ft-primary: {p.primary}; --ft-bg: {p.background}; --ft-secondary: {p.secondary};
  --ft-text: {p.text}; --ft-border: {p.border}; --ft-sidebar: {p.sidebar};
  --ft-sidebar-text: {p.sidebar_text}; --ft-sidebar-input: {p.sidebar_input};
}}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] {{
  background-color: var(--ft-bg);
  color: var(--ft-text);
}}
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp label, .stApp li,
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] {{
  color: var(--ft-text);
}}
.stApp a {{ color: var(--ft-primary); }}

/* Sidebar */
[data-testid="stSidebar"], [data-testid="stSidebarContent"] {{
  background-color: var(--ft-sidebar);
  border-right: 1px solid var(--ft-border);
}}
[data-testid="stSidebar"] * {{ color: var(--ft-sidebar-text) !important; }}
[data-testid="stSidebar"] [data-baseweb="select"] > div {{
  background-color: var(--ft-sidebar-input) !important;
  border-color: var(--ft-border) !important;
}}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {{
  background-color: var(--ft-sidebar-input);
}}

/* Buttons */
{primary_buttons} {{
  background-color: var(--ft-primary) !important;
  border-color: var(--ft-primary) !important;
}}
{primary_buttons}, {primary_buttons.replace('"]', '"] *')} {{ color: #ffffff !important; }}
{primary_buttons.replace('"]', '"]:hover')} {{ filter: brightness(1.1); }}
{secondary_buttons} {{
  background-color: var(--ft-secondary) !important;
  border-color: var(--ft-border) !important;
  color: var(--ft-text) !important;
}}
{secondary_buttons.replace('"]', '"]:hover')} {{
  border-color: var(--ft-primary) !important;
  color: var(--ft-primary) !important;
}}

/* Inputs, uploader, dropdown menus */
{inputs} {{
  background-color: var(--ft-secondary) !important;
  color: var(--ft-text) !important;
  border-color: var(--ft-border) !important;
}}
[data-testid="stFileUploaderDropzone"] {{
  background-color: var(--ft-secondary);
  border: 1px dashed var(--ft-primary);
}}
[data-baseweb="popover"] ul, [data-baseweb="popover"] li {{
  background-color: var(--ft-secondary);
  color: var(--ft-text);
}}

/* Tabs, metrics, progress, tables, alerts */
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{ color: var(--ft-primary); }}
[data-baseweb="tab-highlight"] {{ background-color: var(--ft-primary); }}
[data-baseweb="tab-border"] {{ background-color: var(--ft-border); }}
[data-testid="stProgress"] div[role="progressbar"] > div > div {{
  background-color: var(--ft-primary) !important;
}}
[data-testid="stDataFrame"] {{
  border: 1px solid var(--ft-border);
  border-radius: 8px;
}}
{'[data-testid="stAlertContainer"] { background-color: var(--ft-secondary); }' if p.dark else ''}
"""


def style_chart(chart: alt.TopLevelMixin) -> alt.TopLevelMixin:
    """Apply the palette's colours to an Altair chart (render with theme=None)."""
    p = palette()
    return (
        chart.configure(background="transparent", font="Source Sans Pro, sans-serif")
        .configure_view(stroke=None)
        .configure_axis(
            labelColor=p.text,
            titleColor=p.text,
            gridColor=p.border,
            gridOpacity=0.6,
            domainColor=p.border,
            tickColor=p.border,
            labelFontSize=12,
            titleFontSize=12,
            labelPadding=6,
            labelLimit=260,  # long Mongolian category names stay readable
        )
        .configure_legend(
            labelColor=p.text,
            titleColor=p.text,
            labelFontSize=12,
            symbolType="circle",
            labelLimit=260,
        )
        .configure_bar(color=p.primary)
        .configure_range(category=list(p.chart))
    )
