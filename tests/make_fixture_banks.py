"""FAKE Khan, Golomt and bank-less 'teller' statements for parser tests (no real data)."""

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

# (date, description, counterparty, money in, money out)
KHAN_TXNS = [
    (datetime(2026, 10, 2, 9, 15), "Цалин", "ТЕСТ КОМПАНИ ХХК", 1500000, 0),
    (datetime(2026, 10, 3, 12, 0), "POS 1234**5678 CU-101 SANSAR", "", 0, 8500),
    (datetime(2026, 10, 5, 18, 30), "Шилжүүлэг", "ТЕСТ ХЭРЭГЛЭГЧ-5000000001", 0, 200000),
    (datetime(2026, 10, 5, 18, 30), "Шилжүүлэг", "ТЕСТ ХЭРЭГЛЭГЧ-5000000001", 0, 200000),  # identical twin
]
KHAN_OPENING = 100000


def build_khan(path: str | Path) -> Path:
    """Khan-style .xlsx: header labels in A/B, Debit/Credit columns, newest first."""
    wb = Workbook()
    ws = wb.active
    total = sum(i - o for _, _, _, i, o in KHAN_TXNS)
    for row in [
        ["ХААН БАНК"],
        ["ДАНСНЫ ХУУЛГА"],
        ["Дансны дугаар:", "5000000002"],
        ["Данс эзэмшигч:", "ТЕСТ ХЭРЭГЛЭГЧ"],
        ["Хамрах хугацаа:", "2026.10.01 - 2026.10.31"],
        ["Эхний үлдэгдэл:", f"{KHAN_OPENING:,.2f}", "", "Эцсийн үлдэгдэл:", f"{KHAN_OPENING + total:,.2f}"],
        [],
        ["Гүйлгээний огноо", "Гүйлгээний утга", "Дебит", "Кредит", "Үлдэгдэл", "Харьцсан данс"],
    ]:
        ws.append(row)
    balance, body = KHAN_OPENING, []
    for when, desc, cp, money_in, money_out in KHAN_TXNS:
        balance += money_in - money_out
        body.append([when, desc, money_out or None, money_in or None, balance, cp])
    for row in reversed(body):  # newest first
        ws.append(row)
    path = Path(path)
    wb.save(path)
    return path


GOLOMT_ROWS = [
    ("01.10.2026", "QPay EMART HUN KHOT", "", "45,600.00", "GL0001"),
    ("15.10.2026", "Salary October", "2,000,000.00", "", "GL0002"),
    ("20.10.2026", "UNITEL mobile", "", "12,000.00", "GL0003"),
]


def build_golomt(path: str | Path, tamper: bool = False) -> Path:
    """Golomt-style .csv (';'): English headers, day-first dates, Debit/Credit, Total row."""
    balance = 50000.0
    lines = [
        "GOLOMT BANK;;;;;",
        "Statement period;01.10.2026 - 31.10.2026;;;;",
        "Account number;1105000003 MNT;;;;",
        "Account holder;TEST USER;;;;",
        ";;;;;",
        "Date;Description;Credit;Debit;Balance;Reference",
    ]
    for when, desc, credit, debit, ref in GOLOMT_ROWS:
        balance += float(credit.replace(",", "") or 0) - float(debit.replace(",", "") or 0)
        shown = balance + (1 if tamper and ref == "GL0003" else 0)
        lines.append(f'{when};{desc};"{credit}";"{debit}";"{shown:,.2f}";{ref}')
    lines.append("Total;;2,000,000.00;57,600.00;;")
    path = Path(path)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_teller(path: str | Path, merged_offset: bool = False) -> Path:
    """Layout like a 'Депозит дансны хуулга' export: no bank name, Excel serial dates.

    merged_offset puts every column title one cell right of its data, as exports with
    merged header cells do.
    """
    wb = Workbook()
    ws = wb.active
    rows = [
        [],
        ["Хэвлэсэн огноо:  2026/02/23"],
        [],
        ["Депозит дансны хуулга - Иргэн"],
        [],
        ["Харилцагч:  ТЕСТ ХЭРЭГЛЭГЧ (99112233)"],
        ["Дансны дугаар:  400000001 MNT", None, None, "Эхний үлдэгдэл:  0.00"],
        ["Хамрах хугацаа:  2026.01.15 - 2026.02.23", None, None, "Эцсийн үлдэгдэл:  170,000.00"],
        [],
        [],
        ["Огноо", "Теллер", "Орлого", "Зарлага", "Ханш", "Харьцсан данс", "Үлдэгдэл", "Гүйлгээний утга"],
        [],
        [46037.5, "400 - 59", 200000.0, 0.0, 1.0, "ТЕСТ ХОЛБОГДОХ ДАНС", 200000.0, "Орлого шилжүүлэг"],
        [],
        [46040.25, "400 - 12", 0.0, 30000.0, 1.0, "", 170000.0, "Бэлэн зарлага"],
        [],
        ["Нийт:", None, 200000.0, 30000.0],
        [],
        ["Хуудас:  1 - 1"],
    ]
    if merged_offset:
        rows[10] = [None, *rows[10]]
    for row in rows:
        ws.append(row)
    path = Path(path)
    wb.save(path)
    return path
