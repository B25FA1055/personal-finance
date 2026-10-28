from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from core.merchant import clean_counterparty, extract_merchant, normalize
from core.parsers import XacParser, detect_parser
from core.parsers.xac import parse_amount

REAL_FILE = Path(__file__).with_name("fixtures") / "real_xac.xlsx"


# --- amounts ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4,750.00", Decimal("4750.00")),
        ("199,000.00", Decimal("199000.00")),
        ("313,270.69", Decimal("313270.69")),
        ("50", Decimal("50.00")),
        ("-", Decimal("0.00")),
        ("", Decimal("0.00")),
        (None, Decimal("0.00")),
    ],
)
def test_parse_amount(raw: str | None, expected: Decimal) -> None:
    result = parse_amount(raw)
    assert isinstance(result, Decimal)
    assert result == expected


def test_parse_amount_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_amount("abc")


# --- statement parser ------------------------------------------------------

def test_parse_statement(xac_file: Path) -> None:
    stmt = XacParser().parse(xac_file)

    assert len(stmt.txns) == 10
    assert stmt.bank_code == "xac"
    assert stmt.account_number == "5000000001"
    assert stmt.holder == "ТЕСТ ХЭРЭГЛЭГЧ"
    assert stmt.currency == "MNT"
    assert stmt.period_start == date(2026, 9, 14)
    assert stmt.period_end == date(2026, 10, 14)
    assert stmt.opening_balance == Decimal("100000.00")
    assert stmt.closing_balance == Decimal("115300.00")


def test_header_row_is_found_dynamically(xac_file: Path) -> None:
    workbook = load_workbook(xac_file)
    workbook["AccountStatement"].insert_rows(9)
    workbook.save(xac_file)

    stmt = XacParser().parse(xac_file)

    assert len(stmt.txns) == 10
    assert stmt.account_number == "5000000001"


def test_transaction_columns_are_resolved_from_headers(xac_file: Path) -> None:
    workbook = load_workbook(xac_file)
    sheet = workbook["AccountStatement"]
    column_order = (1, 2, 5, 6, 7, 4, 3)
    for row_index in range(9, sheet.max_row + 1):
        original_values = [
            sheet.cell(row_index, column).value for column in range(1, 8)
        ]
        for target_column, source_column in enumerate(column_order, start=1):
            sheet.cell(row_index, target_column).value = original_values[source_column - 1]
    workbook.save(xac_file)

    statement = XacParser().parse(xac_file)

    assert statement.account_number == "5000000001"
    assert statement.txns[0].txn_date == date(2026, 9, 14)
    assert statement.txns[0].description == (
        "13174691 UB 498738**1604 CU-334 LENIN CLUB"
    )
    assert statement.txns[0].amount == Decimal("-4750.00")
    assert statement.txns[0].balance == Decimal("95250.00")


def test_amounts_signed_and_balances_consistent(xac_file: Path) -> None:
    stmt = XacParser().parse(xac_file)

    first = stmt.txns[0]
    assert first.txn_date == date(2026, 9, 14)
    assert first.bank_ref == "SX0000001"
    assert first.amount == Decimal("-4750.00")
    assert first.balance == Decimal("95250.00")

    gift = next(t for t in stmt.txns if t.description == "EMEE")
    assert gift.amount == Decimal("60000.00")

    running = stmt.opening_balance
    for txn in stmt.txns:
        assert isinstance(txn.amount, Decimal)
        running += txn.amount
        assert txn.balance == running
    assert running == stmt.closing_balance


def test_detect_parser(xac_file: Path) -> None:
    assert isinstance(detect_parser(xac_file), XacParser)


def test_tampered_balance_raises(xac_file: Path) -> None:
    workbook = load_workbook(xac_file)
    sheet = workbook["AccountStatement"]
    for row in sheet.iter_rows():
        if row[1].value == "Эцсийн үлдэгдэл":
            row[6].value = "999,999.00"
    workbook.save(xac_file)

    with pytest.raises(ValueError, match="Balance mismatch"):
        XacParser().parse(xac_file)


def test_can_parse_false_for_other_workbook(tmp_path: Path) -> None:
    path = tmp_path / "empty.xlsx"
    Workbook().save(path)
    assert XacParser().can_parse(path) is False
    with pytest.raises(ValueError):
        detect_parser(path)


@pytest.mark.skipif(not REAL_FILE.exists(), reason="no local real_xac.xlsx")
def test_real_statement_parses() -> None:
    stmt = XacParser().parse(REAL_FILE)
    assert stmt.txns


# --- merchant extraction ---------------------------------------------------

POS_CP = "PRCR/000000978953/14-09-2026 00:00:00/POS-100260040001"


@pytest.mark.parametrize(
    ("description", "counterparty", "txn_type", "merchant"),
    [
        ("13174691 UB 498738**1604 CU-334 LENIN CLUB", POS_CP, "pos", "CU-334 LENIN CLUB"),
        ("AE000289 Khan-Uul 498738**1604 8 Ner", POS_CP, "pos", "8 NER"),
        ("OMSKYTEL 90908989 498738**1604 OMSKYTEL", POS_CP, "pos", "OMSKYTEL"),
        ("XACINFO ҮЙЛЧИЛГЭЭНИЙ ШИМТГЭЛ.", "Цахим банкны хураамжийн орлого-159422510001", "fee", None),
        ("Банк хоорондын шилжүүлгийн шимтгэл", "ХААН БАНК-5000000000", "fee", None),
        ("QPAY 652579793673756 АЗИ БРЮ ХАУС ХХК 9500 TRX: 95.00 ₮", "ККТТ ХХК-5002092243", "fee", None),
        ("qpay 776268535611715, 06024-125-0070, MACR, CHARGE: 95.00 ₮",
         "АЗИ БРЮ ХАУС ХХК ГОЛОМТ БАНК-1715206611", "qpay", "АЗИ БРЮ ХАУС ХХК"),
        ("qpay 896300400502986, 13302956, SALBAR1",
         "УЛААНБААТАР СМАРТ КАРТ ГОЛОМТ БАНК-8115105694", "qpay", "УЛААНБААТАР СМАРТ КАРТ"),
        ("ШИЛЖҮҮЛЭГ", "ТЕСТ ХЭРЭГЛЭГЧ-5006072649", "transfer", "ТЕСТ ХЭРЭГЛЭГЧ"),
        ("EMEE", "БАТ ДОРЖ ХААН БАНК-5600000000", "transfer", "БАТ ДОРЖ"),
        ("ШИЛЖҮҮЛЭГ", "", "transfer", None),
    ],
)
def test_extract_merchant(
    description: str, counterparty: str, txn_type: str, merchant: str | None
) -> None:
    assert extract_merchant(description, counterparty) == (txn_type, merchant)


def test_clean_counterparty_keeps_cyrillic() -> None:
    assert clean_counterparty("  ӨСӨХ   ЭНХЛЭН ХААН БАНК-5000000000 ") == "ӨСӨХ ЭНХЛЭН"


def test_normalize() -> None:
    assert normalize("  Jur  ur food   city ") == "JUR UR FOOD CITY"


def test_shared_bank_ref_gets_unique_suffix(xac_file: Path) -> None:
    # Xac gives an inter-bank fee the same reference as its transfer.
    workbook = load_workbook(xac_file)
    sheet = workbook["AccountStatement"]
    for row in sheet.iter_rows():
        if row[3].value == "SX0000002":
            row[3].value = "SX0000001"
    workbook.save(xac_file)

    refs = [txn.bank_ref for txn in XacParser().parse(xac_file).txns]
    assert refs[:2] == ["SX0000001", "SX0000001#2"]
    assert len(set(refs)) == len(refs)
