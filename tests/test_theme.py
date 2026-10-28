import altair as alt
import pandas as pd

from core.i18n import TEXTS
from core.theme import THEMES, _css, style_chart


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_every_theme_is_readable() -> None:
    for name, p in THEMES.items():
        assert _contrast(p.text, p.background) >= 4.5, name
        assert _contrast(p.text, p.secondary) >= 4.5, name
        assert _contrast(p.sidebar_text, p.sidebar) >= 4.5, name
        assert _contrast(p.sidebar_text, p.sidebar_input) >= 4.5, name
        # Primary buttons render white text (WCAG AA for large/bold UI text).
        assert _contrast("#ffffff", p.primary) >= 3.0, name


def test_every_theme_has_a_name_in_both_languages() -> None:
    for name in THEMES:
        assert f"theme_{name}" in TEXTS


def test_css_uses_palette_colours() -> None:
    p = THEMES["emerald"]
    css = _css(p)
    assert p.primary in css and p.sidebar in css
    assert css.count("{") == css.count("}")


def test_style_chart_sets_category_colours() -> None:
    chart = alt.Chart(pd.DataFrame({"a": ["x"], "b": [1]})).mark_bar().encode(x="a", y="b")
    spec = style_chart(chart).to_dict()
    assert spec["config"]["range"]["category"] == list(THEMES["light"].chart)


def test_palettes_have_ten_distinct_chart_colours() -> None:
    # Ten covers every seeded expense category without colours repeating in the donut.
    for name, p in THEMES.items():
        assert len(set(p.chart)) >= 10, name
