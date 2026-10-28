from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from core.parsers import (
    GolomtParser,
    KhanParser,
    UnknownBankError,
    XacParser,
    detect_parser,
)
from core.parsers.generic import parse_amount, parse_date
from make_fixture_banks import build_golomt, build_khan, build_teller


def test_khan_detected_and_parsed(tmp_path: Path) -> None:
    path = build_khan(tmp_path / "khan.xlsx")
    parser = detect_parser(path)
    assert isinstance(parser, KhanParser)

    stmt = parser.parse(path)
    assert stmt.bank_code == "khan"
    assert stmt.account_number == "5000000002"
    assert stmt.holder == "ТЕСТ ХЭРЭГЛЭГЧ"
    assert (stmt.period_start, stmt.period_end) == (date(2026, 10, 1), date(2026, 10, 31))
    assert stmt.opening_balance == Decimal("100000.00")
    assert stmt.closing_balance == Decimal("1191500.00")
    # newest-first export is returned oldest first, with signed amounts
    assert [t.amount for t in stmt.txns] == [
        Decimal("1500000.00"), Decimal("-8500.00"), Decimal("-200000.00"), Decimal("-200000.00"),
    ]
    assert stmt.txns[0].txn_date == date(2026, 10, 2)
    assert stmt.txns[2].counterparty == "ТЕСТ ХЭРЭГЛЭГЧ-5000000001"


def test_khan_synthetic_refs_are_unique_and_stable(tmp_path: Path) -> None:
    path = build_khan(tmp_path / "khan.xlsx")
    first = [t.bank_ref for t in KhanParser().parse(path).txns]
    second = [t.bank_ref for t in KhanParser().parse(path).txns]
    assert len(set(first)) == len(first)  # identical twin transfers stay two rows
    assert first == second  # re-importing an overlapping statement de-duplicates


def test_golomt_csv_detected_and_parsed(tmp_path: Path) -> None:
    path = build_golomt(tmp_path / "golomt.csv")
    parser = detect_parser(path)
    assert isinstance(parser, GolomtParser)

    stmt = parser.parse(path)
    assert stmt.account_number == "1105000003"
    assert stmt.currency == "MNT"
    assert stmt.holder == "TEST USER"
    assert [t.bank_ref for t in stmt.txns] == ["GL0001", "GL0002", "GL0003"]
    assert [t.amount for t in stmt.txns] == [Decimal("-45600.00"), Decimal("2000000.00"), Decimal("-12000.00")]
    assert stmt.txns[0].txn_date == date(2026, 10, 1)  # day-first date
    assert stmt.opening_balance == Decimal("50000.00")
    assert stmt.closing_balance == Decimal("1992400.00")


def test_tampered_running_balance_is_rejected(tmp_path: Path) -> None:
    path = build_golomt(tmp_path / "golomt.csv", tamper=True)
    with pytest.raises(ValueError, match="Running balance mismatch"):
        GolomtParser().parse(path)


@pytest.mark.parametrize("merged_offset", [False, True])
def test_bankless_statement_needs_a_manual_bank_choice(tmp_path: Path, merged_offset: bool) -> None:
    path = build_teller(tmp_path / "teller.xlsx", merged_offset)
    with pytest.raises(UnknownBankError):
        detect_parser(path)

    stmt = detect_parser(path, "khan").parse(path)
    assert stmt.bank_code == "khan"
    assert stmt.account_number == "400000001"
    assert stmt.holder == "ТЕСТ ХЭРЭГЛЭГЧ"
    assert (stmt.period_start, stmt.period_end) == (date(2026, 1, 15), date(2026, 2, 23))
    assert [(t.txn_date, t.amount) for t in stmt.txns] == [
        (date(2026, 1, 15), Decimal("200000.00")),  # Excel serial dates
        (date(2026, 1, 18), Decimal("-30000.00")),
    ]
    assert stmt.closing_balance == Decimal("170000.00")


def test_xac_still_detected_although_rows_mention_khan(xac_file: Path) -> None:
    # The Xac fixture has a counterparty "... ХААН БАНК-..." inside the transactions.
    assert isinstance(detect_parser(xac_file), XacParser)


def test_non_statement_is_not_mistaken_for_one(tmp_path: Path) -> None:
    path = tmp_path / "budget.xlsx"
    wb = Workbook()
    wb.active.append(["Нэр", "Дүн"])
    wb.active.append(["Хоол", 1000])
    wb.save(path)
    with pytest.raises(ValueError) as info:
        detect_parser(path)
    assert not isinstance(info.value, UnknownBankError)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1,234.50", "1234.50"), ("(1,234.50)", "-1234.50"), ("-", "0.00"), ("12 000 ₮", "12000.00"), (2500.0, "2500.00")],
)
def test_parse_amount(raw, expected) -> None:
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026/01/31", date(2026, 1, 31)),
        ("2026.01.31 14:22", date(2026, 1, 31)),
        ("31.01.2026", date(2026, 1, 31)),
        (46056.67, date(2026, 2, 3)),
        ("Нийт:", None),
    ],
)
def test_parse_date(raw, expected) -> None:
    assert parse_date(raw) == expected


@pytest.mark.parametrize(
    ("description", "counterparty", "expected"),
    [
        ("POS 1234**5678 CU-101 SANSAR", "", ("pos", "CU-101 SANSAR")),
        ("PURCHASE 456712XXXXXX1234 EMART", "", ("pos", "EMART")),
        ("QPay EMART HUN KHOT", "", ("qpay", "EMART HUN KHOT")),
        ("13174691 UB 498738**1604 CU-334 LENIN CLUB", "PRCR/1", ("pos", "CU-334 LENIN CLUB")),  # Xac unchanged
    ],
)
def test_merchants_from_other_banks(description, counterparty, expected) -> None:
    from core.merchant import extract_merchant

    assert extract_merchant(description, counterparty) == expected
