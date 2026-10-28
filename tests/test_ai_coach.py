import pytest
import streamlit as st

from core.ai_coach import rule_based_answer

CONTEXT = {
    "today": "2026-10-21",
    "ui_language": "mn",
    "data_until": "2026-10-14",
    "monthly": [{"month": "2026-10", "income": 334000, "expense": 528973, "net": -194973}],
    "this_month": {
        "period": "2026-10-01..2026-10-21",
        "expense_by_category": [
            {"category": "Хоол хүнс", "total": 120000, "count": 9},
            {"category": "Ресторан & Кафе", "total": 50000, "count": 4},
            {"category": "Үйлчилгээ / Шимтгэл", "total": 2000, "count": 30},
        ],
        "income_by_category": [],
        "top_merchants": [
            {"merchant": "CU-334 LENIN CLUB", "type": "pos", "category": "Хоол хүнс", "count": 5, "total": 40000},
            {"merchant": "OMSKYTEL", "type": "pos", "category": "Ашиглалт, холбоо", "count": 1, "total": 7000},
        ],
    },
    "last_month": {
        "period": "2026-09-01..2026-09-30",
        "expense_by_category": [{"category": "Хоол хүнс", "total": 90000, "count": 8}],
        "top_merchants": [],
    },
    "budgets_this_month": [
        {"category": "Хоол хүнс", "limit": 100000, "spent": 120000, "status": "exceeded"},
        {"category": "Бусад", "limit": None, "spent": 5000, "status": "unbudgeted"},
    ],
    "savings_goals": [
        {"name": "Laptop", "target": 3000000, "saved": 750000, "percent": 25.0, "deadline": "2027-06-01"}
    ],
}


@pytest.fixture(params=["mn", "en"])
def lang(request):
    st.session_state["lang"] = request.param
    yield request.param
    st.session_state.pop("lang", None)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Энэ сард хамгийн их юунд зарцуулсан бэ?", "120,000₮"),
        ("Where did I spend the most this month?", "CU-334 LENIN CLUB"),
        ("Хоол хүнсний зардлаа яаж бууруулах вэ?", "170,000₮"),
        ("How can I reduce my food expenses?", "90,000₮"),
        ("Миний хуримтлалын явц ямар байна?", "750,000₮"),
        ("Am I over budget anywhere?", "100,000₮"),
        ("Төсвөөсөө хэтэрсэн ангилал байна уу?", "100,000₮"),
        ("Зорилгоо хэр биелүүлж байна?", "750,000₮"),
        ("Give me a summary of income", "334,000₮"),
    ],
)
def test_rule_based_answers_use_real_numbers(lang, question, expected) -> None:
    assert expected in rule_based_answer(question, CONTEXT)


def test_rule_based_help_for_unknown_question(lang) -> None:
    assert rule_based_answer("asdf", CONTEXT)
