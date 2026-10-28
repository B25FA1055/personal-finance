import re
import string
from pathlib import Path

from core.i18n import LANGUAGES, TEXTS

ROOT = Path(__file__).resolve().parent.parent


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_text_has_all_languages_with_same_placeholders() -> None:
    for key, entry in TEXTS.items():
        assert set(entry) == set(LANGUAGES), key
        assert all(entry.values()), key
        assert _fields(entry["mn"]) == _fields(entry["en"]), key


def test_every_key_used_in_pages_exists() -> None:
    sources = [ROOT / "app.py", ROOT / "core" / "ui.py", ROOT / "core" / "ai_coach.py", *sorted((ROOT / "pages").glob("*.py"))]
    used = {
        key
        for path in sources
        for key in re.findall(r"""\bt\(\s*["']([a-z_]+)["']\s*[,)]""", path.read_text(encoding="utf-8"))
    }
    assert used, "no t() calls found"
    assert used <= TEXTS.keys(), used - TEXTS.keys()


def test_every_seeded_category_has_an_english_name() -> None:
    from core.i18n import CATEGORY_EN
    from core.seed import TAXONOMY

    names = {name for main, _, subs in TAXONOMY for name in (main, *subs)}
    assert sorted(names - CATEGORY_EN.keys()) == []


def test_category_name_follows_language() -> None:
    from core.i18n import category_name

    assert category_name("Хоол хүнс", "en") == "Food & Groceries"
    assert category_name("Хоол хүнс", "mn") == "Хоол хүнс"
    assert category_name("Миний ангилал", "en") == "Миний ангилал"  # user-made: shown as typed
    for placeholder in ("Unclassified", "Ангилаагүй", None):
        assert category_name(placeholder, "en") == "Unclassified"
        assert category_name(placeholder, "mn") == "Ангилаагүй"
