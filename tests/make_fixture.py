"""Build a FAKE Xac Bank statement (same layout, all cells strings) for tests."""

from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

HOLDER = "ТЕСТ ХЭРЭГЛЭГЧ"
ACCOUNT = "5000000001"
OPENING = Decimal("100000.00")
FEE_TEXT = "XACINFO ҮЙЛЧИЛГЭЭНИЙ ШИМТГЭЛ."
FEE_CP = "Цахим банкны хураамжийн орлого-159422510001"
POS_CP = "PRCR/000000978953/14-09-2026 00:00:00/POS-100260040001"

# (date, description, counterparty, income, expense)
TRANSACTIONS: list[tuple[str, str, str, Decimal, Decimal]] = [
    ("2026-09-14", "13174691 UB 498738**1604 CU-334 LENIN CLUB", POS_CP, Decimal("0"), Decimal("4750.00")),
    ("2026-09-14", FEE_TEXT, FEE_CP, Decimal("0"), Decimal("50.00")),
    ("2026-09-15", "70114744 ULAANBAATAR 498738**1604 JUR UR FOOD CITY", POS_CP, Decimal("0"), Decimal("12300.00")),
    ("2026-09-15", FEE_TEXT, FEE_CP, Decimal("0"), Decimal("50.00")),
    ("2026-09-16", "AE000289 Khan-Uul 498738**1604 8 Ner", POS_CP, Decimal("0"), Decimal("3000.00")),
    ("2026-09-16", FEE_TEXT, FEE_CP, Decimal("0"), Decimal("50.00")),
    ("2026-09-18", "QPAY 652579793673756 АЗИ БРЮ ХАУС ХХК 9500 TRX: 95.00 ₮", "ККТТ ХХК-5002092243", Decimal("0"), Decimal("95.00")),
    ("2026-09-18", "qpay 776268535611715, 06024-125-0070, MACR, CHARGE: 95.00 ₮", "АЗИ БРЮ ХАУС ХХК ГОЛОМТ БАНК-1715206611", Decimal("0"), Decimal("9405.00")),
    ("2026-09-20", "EMEE", "БАТ ДОРЖ ХААН БАНК-5600000000", Decimal("60000.00"), Decimal("0")),
    ("2026-09-25", "ШИЛЖҮҮЛЭГ", "ТЕСТ ХЭРЭГЛЭГЧ-5006072649", Decimal("0"), Decimal("15000.00")),
]


def money(value: Decimal) -> str:
    return "-" if value == 0 else f"{value:,.2f}"


def build(path: str | Path, holder: str = HOLDER) -> Path:
    path = Path(path)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "AccountStatement"

    total_in = sum(t[3] for t in TRANSACTIONS)
    total_out = sum(t[4] for t in TRANSACTIONS)
    closing = OPENING + total_in - total_out

    header = [
        ["ДАНСНЫ ХУУЛГА", "", "", "", "", "", ""],
        ["", "", "", "", "", "", ""],
        ["Үндсэн эзэмшигч:", holder, "", "", "", "Орлого:", money(total_in)],
        ["Хаяг:", "УЛААНБААТАР", "", "", "", "Зарлага:", money(total_out)],
        ["Дансны дугаар:", ACCOUNT, "", "", "", "", ""],
        ["Дансны төрөл:", "ХАРИЛЦАХ", "", "", "", "Эхлэх:", "2026-09-14"],
        ["Валют:", "MNT", "", "", "", "Дуусах:", "2026-10-14"],
        ["", "", "", "", "", "", ""],
        ["Огноо", "Гүйлгээний утга", "Харьцсан данс", "Гүйлгээний дугаар", "Орлого", "Зарлага", "Үлдэгдэл"],
        ["", "Эхний үлдэгдэл", "", "", "", "", money(OPENING)],
    ]
    for row in header:
        sheet.append(row)

    balance = OPENING
    for number, (day, description, counterparty, income, expense) in enumerate(TRANSACTIONS, 1):
        balance += income - expense
        sheet.append([
            day, description, counterparty, f"SX{number:07d}",
            money(income), money(expense), money(balance),
        ])

    sheet.append(["", "Эцсийн үлдэгдэл", "", "", money(total_in), money(total_out), money(closing)])
    sheet.append(["", "", "", "", "", "", ""])
    sheet.append(["Хэвлэсэн:", "2026-10-15 10:00:00", "", "", "", "", ""])

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


if __name__ == "__main__":
    print(build(Path(__file__).with_name("fixtures") / "sample_xac.xlsx"))
