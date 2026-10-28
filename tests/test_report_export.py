import io
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from openpyxl import load_workbook

from core.i18n import TEXTS
from core.report_export import LABEL_KEYS, ReportData, file_stem, to_excel, to_pdf

LABELS = {key: TEXTS[key]["mn"] for key in LABEL_KEYS}


@pytest.fixture
def data() -> ReportData:
    D = Decimal
    return ReportData(
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
        income=D("300000"),
        expense=D("120500"),
        monthly=pd.DataFrame({"month": [date(2026, 9, 1)], "income": [D("300000")],
                              "expense": [D("120500")], "net": [D("179500")]}),
        expense_categories=pd.DataFrame({"category": ["Хоол хүнс", "Үйлчилгээ / Шимтгэл"],
                                         "total": [D("120000"), D("500")], "count": [5, 10], "pct": [99.6, 0.4]}),
        income_categories=pd.DataFrame({"category": ["Бэлэг"], "total": [D("300000")], "count": [1], "pct": [100.0]}),
        merchants=pd.DataFrame({"merchant": ["CU-334 LENIN CLUB"], "txn_type": ["pos"], "count": [5], "total": [D("120000")]}),
        transactions=pd.DataFrame({
            "date": [date(2026, 9, 2), date(2026, 9, 3)],
            "bank": ["Xac Bank", "Xac Bank"],
            "description": ["EMEE", "13174691 UB 498738**1604 CU-334 LENIN CLUB " * 3],  # long text wraps
            "merchant": ["", "CU-334 LENIN CLUB"],
            "category": ["Бэлэг", "Хоол хүнс"],
            "amount": [D("300000"), D("-120500")],
        }),
    )


def test_every_label_is_translated() -> None:
    assert [k for k in LABEL_KEYS if k not in TEXTS] == []


def test_excel_has_four_sheets_and_exact_totals(data: ReportData) -> None:
    wb = load_workbook(io.BytesIO(to_excel(data, LABELS)))
    assert wb.sheetnames == ["Хураангуй", "Ангилал", "Газрууд", "Гүйлгээ"]
    tx = wb["Гүйлгээ"]
    assert [c.value for c in tx[1]] == ["Огноо", "Банк", "Гүйлгээний утга", "Харилцагч", "Ангилал", "Дүн ₮"]
    assert sum(row[5] for row in tx.iter_rows(min_row=2, values_only=True)) == 179500
    assert tx.freeze_panes == "A2" and tx.cell(2, 6).number_format == "#,##0"
    summary = [row for row in wb["Хураангуй"].iter_rows(values_only=True) if row[0]]
    assert ("Нийт орлого", "300,000₮") in [row[:2] for row in summary]
    assert wb["Газрууд"].cell(2, 2).value == "Карт (POS)"  # translated type


def test_pdf_is_valid_and_contains_cyrillic_font(data: ReportData) -> None:
    pdf = to_pdf(data, LABELS)
    assert pdf.startswith(b"%PDF") and b"%%EOF" in pdf[-1024:]
    assert b"FontFile2" in pdf  # TrueType font embedded (needed for Ө, Ү, ₮)


def test_file_stem() -> None:
    assert file_stem(date(2026, 1, 1), date(2026, 10, 21)) == "fintrack_20260101_20261021"
