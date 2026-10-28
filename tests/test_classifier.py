from decimal import Decimal

from core.classifier import Ctx, Rule, classify, rule_matches

GROCERIES, RESTAURANT, GIFT, TRANSFER, FEES = 1, 2, 3, 4, 5


def rule(id: int, field: str, match: str, pattern: str, category_id: int,
         direction: str = "any", priority: int = 100) -> Rule:
    return Rule(id, field, match, pattern, direction, category_id, priority)


def txn(description: str = "", counterparty: str = "", merchant: str | None = None,
        amount: str = "-1000", merchant_id: int | None = None) -> dict:
    return {
        "description": description,
        "counterparty": counterparty,
        "merchant": merchant,
        "merchant_id": merchant_id,
        "amount": Decimal(amount),
    }


def ctx(*rules: Rule, defaults: dict[int, int] | None = None) -> Ctx:
    ordered = sorted(rules, key=lambda r: (r.priority, r.id))
    return Ctx(ordered, {"5006072649"}, defaults or {}, TRANSFER)


def test_match_kinds_case_insensitive() -> None:
    t = txn(merchant="CU-334 LENIN CLUB")
    assert rule_matches(rule(1, "merchant", "startswith", "cu-", GROCERIES), t)
    assert rule_matches(rule(1, "merchant", "contains", "lenin", GROCERIES), t)
    assert rule_matches(rule(1, "merchant", "exact", "cu-334 lenin club", GROCERIES), t)
    assert rule_matches(rule(1, "merchant", "regex", r"^CU-\d+", GROCERIES), t)
    assert not rule_matches(rule(1, "merchant", "exact", "CU-334", GROCERIES), t)


def test_cyrillic_and_invalid_regex() -> None:
    t = txn(merchant="АЗИ БРЮ ХАУС ХХК")
    assert rule_matches(rule(1, "merchant", "contains", "брю хаус", RESTAURANT), t)
    assert not rule_matches(rule(1, "merchant", "regex", "([", RESTAURANT), t)


def test_direction_filter() -> None:
    gift = rule(1, "description", "exact", "EMEE", GIFT, direction="in")
    assert rule_matches(gift, txn("EMEE", amount="60000"))
    assert not rule_matches(gift, txn("EMEE", amount="-60000"))


def test_priority_order_wins() -> None:
    c = ctx(
        rule(1, "merchant", "contains", "CU", GROCERIES, priority=100),
        rule(2, "merchant", "contains", "CU", RESTAURANT, priority=50),
    )
    assert classify(txn(merchant="CU-334"), c) == (RESTAURANT, "rule")


def test_own_account_beats_rules() -> None:
    c = ctx(rule(1, "description", "contains", "ШИЛЖҮҮЛЭГ", GIFT))
    t = txn("ШИЛЖҮҮЛЭГ", "ТЕСТ ХЭРЭГЛЭГЧ-5006072649")
    assert classify(t, c) == (TRANSFER, "rule")


def test_fee_naming_own_account_stays_fee() -> None:
    c = ctx(rule(1, "description", "startswith", "Банк хоорондын шилжүүлгийн шимтгэл", FEES))
    t = txn("Банк хоорондын шилжүүлгийн шимтгэл",
            "Банк хоорондын шилжүүлгийн шимтгэл-5006072649", amount="-200")
    t["txn_type"] = "fee"
    assert classify(t, c) == (FEES, "rule")


def test_merchant_default_then_none() -> None:
    c = ctx(rule(1, "description", "startswith", "XACINFO", FEES), defaults={7: RESTAURANT})
    assert classify(txn(merchant="TUTS", merchant_id=7), c) == (RESTAURANT, "merchant")
    assert classify(txn(merchant="UNKNOWN", merchant_id=8), c) == (None, None)


def test_localized_rules_classify_food_fees_and_smart_card() -> None:
    food, fees, transport = 10, 11, 12
    c = ctx(
        rule(1, "description", "startswith", "XACINFO", fees, priority=1),
        rule(2, "merchant", "startswith", "CU-", food, direction="out", priority=20),
        rule(3, "merchant", "startswith", "EMART", food, direction="out", priority=20),
        rule(4, "merchant", "startswith", "KIOSK", food, direction="out", priority=20),
        rule(5, "counterparty", "contains", "УЛААНБААТАР СМАРТ КАРТ",
             transport, direction="out", priority=20),
    )
    assert classify(txn("XACINFO үйлчилгээний шимтгэл"), c) == (fees, "rule")
    assert classify(txn(merchant="CU-334 LENIN CLUB"), c) == (food, "rule")
    assert classify(txn(merchant="EMART CENTRAL"), c) == (food, "rule")
    assert classify(txn(merchant="KIOSK 24"), c) == (food, "rule")
    assert classify(
        txn(counterparty="УЛААНБААТАР СМАРТ КАРТ ГОЛОМТ БАНК", amount="-1000"),
        c,
    ) == (transport, "rule")


def test_other_is_default_by_transaction_direction() -> None:
    other_income, other_expense = 20, 21
    c = Ctx([], set(), {}, TRANSFER, other_income, other_expense)
    assert classify(txn("unknown income", amount="2500"), c) == (
        other_income,
        "merchant",
    )
    assert classify(txn("unknown expense", amount="-2500"), c) == (
        other_expense,
        "merchant",
    )
