from datetime import date
from decimal import Decimal

import pytest

from core.classifier import Ctx, Rule, classify
from core.goals import evaluate, months_left, project
from core.seed import SEED_RULES, TAXONOMY

# Category ids stand in as names, so assertions read naturally.
RULES = sorted(
    (Rule(i, field, match, pattern, direction, category, priority)
     for i, (pattern, field, match, direction, category, priority) in enumerate(SEED_RULES, 1)),
    key=lambda r: (r.priority, r.id),
)
CTX = Ctx(RULES, {"5006072649"}, {}, "Дотоод шилжүүлэг", "Бусад(орлого)", "Бусад", "Банкны шимтгэл")


def cat(merchant: str = "", description: str = "", counterparty: str = "", amount: str = "-1000", txn_type: str = "pos"):
    return classify(
        {"merchant": merchant, "description": description, "counterparty": counterparty,
         "amount": Decimal(amount), "merchant_id": None, "txn_type": txn_type},
        CTX,
    )[0]


@pytest.mark.parametrize(
    ("merchant", "expected"),
    [
        ("CU-334 LENIN CLUB", "Хүнсний дэлгүүр"),
        ("GS25 SANSAR", "Супермаркет"),  # 'SANSAR' supermarket rule outranks GS25
        ("GS25 ZAISAN", "Хүнсний дэлгүүр"),
        ("SANSAR_EMART_KIOSK-2", "Супермаркет"),
        ("MEGA-NOMINMACRO", "Супермаркет"),
        ("NOMIN ELECTRONICS", "Электроник"),  # not food
        ("NOMIN TAVAN BOGD", "Супермаркет"),
        ("TOM N TOMS COFFEE", "Кафе & Кофе шоп"),
        ("SEZIS BUFFET", "Ресторан"),  # canteen, not the university
        ("SEZS - TSAINII GAZAR", "Ресторан"),
        ("KFC CENTRAL TOWER", "Түргэн хоол"),
        ("GLOWUP.MN", "Гоо сайхны бүтээгдэхүүн"),
        ("BEAUTY SALON NOMI", "Гоо сайхны бүтээгдэхүүн"),
        ("HAIR SALON 7", "Салон & Үйлчилгээ"),
        ("PETROVIS 12", "Шатахуун"),
        ("SHUNKHLAI LLC", "Шатахуун"),
        ("UB PARKING", "Зогсоол"),
        ("UNITEL SHOP", "Гар утас"),
        ("UNIVISION LLC", "Интернет & ТВ"),
        ("INTERNOM BOOKSTORE", "Ном & Хэрэгсэл"),
        ("AZOD ONLINE SHOP2", "Хувцас"),
        ("PC MALL", "Электроник"),
        ("ZOLO DENT", "Эрүүл мэнд"),
        ("SOME UNKNOWN SHOP", "Бусад"),
    ],
)
def test_merchant_keywords(merchant, expected) -> None:
    assert cat(merchant=merchant) == expected


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("XACINFO ҮЙЛЧИЛГЭЭНИЙ ШИМТГЭЛ.", "Банкны шимтгэл"),
        ("МАНДАХ ИС сургалтын төлбөр", "Сургалтын төлбөр"),
        ("NUM tuition fall", "Сургалтын төлбөр"),
        ("НОМИН ДЭЛГҮҮР", "Бусад"),  # 'НОМ' must not match inside 'НОМИН' (description rule)
        ("Англи хэлний курс", "Курс & Сургалт"),
        ("Байрны түрээс 10 сар", "Түрээс"),
        ("CURRENT ACCOUNT TOPUP", "Бусад"),  # 'RENT' must not match inside 'CURRENT'
        ("Хадгаламж руу", "Хуримтлал"),
        ("UBCAB taxi ride", "Такси"),
        ("ЗЭЭЛИЙН ТӨЛБӨР 10 сар", "Зээлийн төлбөр"),
    ],
)
def test_description_keywords(description, expected) -> None:
    assert cat(description=description, txn_type="transfer") == expected


def test_fee_fallback_and_own_account_transfer() -> None:
    assert cat(description="Unknown bank charge", txn_type="fee") == "Банкны шимтгэл"
    assert cat(description="ШИЛЖҮҮЛЭГ", counterparty="ТЕСТ-5006072649", txn_type="transfer") == "Дотоод шилжүүлэг"


def test_every_rule_targets_a_seeded_category() -> None:
    names = {name for main, _, subs in TAXONOMY for name in (main, *subs)}
    assert {category for *_, category, _ in SEED_RULES} <= names


def test_months_left() -> None:
    assert months_left(date(2026, 10, 21), date(2027, 10, 21)) == 12
    assert months_left(date(2026, 10, 21), date(2026, 10, 25)) == 1
    assert months_left(date(2026, 10, 21), date(2026, 10, 1)) == 0


@pytest.mark.parametrize(
    ("saved", "today", "status"),
    [
        ("1000000", date(2026, 6, 1), "done"),
        ("700000", date(2026, 7, 1), "ahead"),  # 70% saved, ~50% expected
        ("450000", date(2026, 7, 1), "on_track"),
        ("100000", date(2026, 7, 1), "behind"),
        ("100000", date(2027, 2, 1), "overdue"),
    ],
)
def test_goal_status(saved, today, status) -> None:
    result = evaluate(Decimal("1000000"), Decimal(saved), date(2026, 1, 1), date(2026, 12, 31), today)
    assert result["status"] == status


def test_monthly_needed() -> None:
    result = evaluate(Decimal("1200000"), Decimal("0"), date(2026, 10, 21), date(2027, 10, 21), date(2026, 10, 21))
    assert result["months_left"] == 12
    assert result["monthly_needed"] == Decimal("100000")


def test_multiple_goal_funding_sources_project_completion_and_shortfall() -> None:
    today = date(2026, 1, 15)
    result = project(
        Decimal("1000"),
        Decimal("100"),
        [
            {
                "name": "Salary",
                "kind": "monthly",
                "amount": Decimal("100"),
                "start_month": date(2026, 1, 1),
                "end_month": date(2026, 3, 1),
            },
            {
                "name": "Side income",
                "kind": "monthly",
                "amount": Decimal("50"),
                "start_month": date(2026, 2, 1),
                "end_month": date(2026, 7, 1),
            },
            {
                "name": "Bonus",
                "kind": "lump_sum",
                "amount": Decimal("300"),
                "start_month": date(2026, 4, 1),
            },
            {
                "name": "Mortgage",
                "kind": "loan",
                "amount": Decimal("100"),
                "start_month": date(2026, 6, 1),
            },
        ],
        today,
        date(2026, 6, 30),
    )

    assert result["monthly_plan"] == Decimal("150")
    assert result["loan_total"] == Decimal("100")
    assert result["planned_by_deadline"] == Decimal("850")
    assert result["shortfall"] == Decimal("50")
    assert result["extra_per_month"] == Decimal("10")
    assert result["projected_month"] == date(2026, 7, 1)
    assert result["plan_status"] == "gap"
