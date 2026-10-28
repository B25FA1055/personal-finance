"""Export the Reports page as an Excel workbook or a PDF summary.

build_report() gathers everything for a period (KPIs, months, categories, merchants,
transactions); to_excel() / to_pdf() render it. Labels are passed in already translated,
because Streamlit runs download callables on a separate thread without session state.
"""

import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import Connection, Engine, text

from core import reports
from core.i18n import category_name

# Windows fonts with Mongolian Cyrillic (Ө, Ү) and the ₮ sign; first one found is used.
FONT_CANDIDATES = [
    (Path(r"C:\Windows\Fonts\segoeui.ttf"), Path(r"C:\Windows\Fonts\segoeuib.ttf")),
    (Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")),
    (Path(r"C:\Windows\Fonts\calibri.ttf"), Path(r"C:\Windows\Fonts\calibrib.ttf")),
]


# Text keys the exports use; the page translates them on the main thread.
LABEL_KEYS = (
    "report_title", "report_metric", "report_value", "report_generated", "report_page",
    "report_sheet_summary", "report_sheet_categories", "report_sheet_merchants",
    "report_sheet_transactions", "report_top_merchants", "report_transactions",
    "m_total_income", "m_total_expense", "m_net_balance", "m_savings_rate", "m_net",
    "kind_income", "kind_expense", "period", "monthly_chart", "spending_by_category",
    "income_by_category", "col_month", "col_category", "col_total", "col_pct", "col_count",
    "col_merchant", "col_type", "col_date", "col_bank", "col_description", "col_amount",
    "type_pos", "type_qpay", "type_cash",
)


@dataclass
class ReportData:
    start: date
    end: date
    income: Decimal
    expense: Decimal
    monthly: pd.DataFrame
    expense_categories: pd.DataFrame
    income_categories: pd.DataFrame
    merchants: pd.DataFrame
    transactions: pd.DataFrame
    generated: datetime = field(default_factory=datetime.now)

    @property
    def net(self) -> Decimal:
        return self.income - self.expense

    @property
    def savings_rate(self) -> float | None:
        return float(self.net / self.income) * 100 if self.income else None


def _translated(df: pd.DataFrame, lang: str) -> pd.DataFrame:
    """Category names in the export language (stored names are Mongolian)."""
    named = df["category"].map(lambda name: category_name(name or None, lang))
    return df.assign(category=named)


def build_report(conn: Connection, start: date, end: date, lang: str = "mn") -> ReportData:
    income, expense, _ = reports.period_totals(conn, start, end)
    transactions = pd.read_sql(
        text(
            "SELECT t.txn_date::date AS date, b.name AS bank, t.description, "
            "COALESCE(m.name, '') AS merchant, "
            "COALESCE(c.name, '') AS category, t.amount "
            "FROM transactions t JOIN accounts a ON a.id = t.account_id "
            "JOIN banks b ON b.id = a.bank_id "
            "LEFT JOIN merchants m ON m.id = t.merchant_id "
            "LEFT JOIN categories c ON c.id = t.category_id "
            "WHERE t.txn_date::date BETWEEN :start AND :end ORDER BY t.txn_date, t.id"
        ),
        conn,
        params={"start": start, "end": end},
        coerce_float=False,
    )
    return ReportData(
        start=start,
        end=end,
        income=income,
        expense=expense,
        monthly=reports.monthly_summary(conn, start, end),
        expense_categories=_translated(reports.by_category(conn, start, end, "expense"), lang),
        income_categories=_translated(reports.by_category(conn, start, end, "income"), lang),
        merchants=reports.top_merchants(conn, start, end),
        transactions=_translated(transactions, lang),
    )


def file_stem(start: date, end: date) -> str:
    return f"fintrack_{start:%Y%m%d}_{end:%Y%m%d}"


def _money(value) -> str:
    return f"{Decimal(str(value or 0)):,.0f}₮"


def _kpis(data: ReportData, labels: dict[str, str]) -> list[tuple[str, str]]:
    rate = data.savings_rate
    return [
        (labels["m_total_income"], _money(data.income)),
        (labels["m_total_expense"], _money(data.expense)),
        (labels["m_net_balance"], _money(data.net)),
        (labels["m_savings_rate"], f"{rate:.1f}%" if rate is not None else "—"),
    ]


# --- Excel --------------------------------------------------------------------------


def _write_table(writer, sheet: str, df: pd.DataFrame, row: int, money_cols: tuple[str, ...] = (), title: str = "") -> int:
    """Write df at row (0-based) under an optional bold title; style header and money columns.

    Returns the next free row, leaving one blank row after the table.
    """
    from openpyxl.styles import Font, PatternFill

    if title:
        row += 1
    df.to_excel(writer, sheet_name=sheet, index=False, startrow=row)
    ws = writer.book[sheet]
    if title:
        ws.cell(row=row, column=1, value=title).font = Font(bold=True, size=12)
    header_row = row + 1  # openpyxl is 1-based
    for col, name in enumerate(df.columns, start=1):
        cell = ws.cell(row=header_row, column=col)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="E8EEF7")
        if name in money_cols:
            for r in range(header_row + 1, header_row + 1 + len(df)):
                ws.cell(row=r, column=col).number_format = "#,##0"
    return row + len(df) + 2


def to_excel(data: ReportData, labels: dict[str, str]) -> bytes:
    """Workbook with Summary, Categories, Merchants and Transactions sheets."""
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    L = labels
    money = (L["col_total"], L["col_amount"], L["kind_income"], L["kind_expense"], L["m_net"])
    category_names = {"category": L["col_category"], "total": L["col_total"], "pct": L["col_pct"], "count": L["col_count"]}

    def categories(df: pd.DataFrame) -> pd.DataFrame:
        return df.assign(total=df["total"].astype(float))[["category", "total", "pct", "count"]].rename(columns=category_names)

    summary = pd.DataFrame(_kpis(data, L), columns=[L["report_metric"], L["report_value"]])
    monthly = data.monthly.assign(
        month=data.monthly["month"].astype(str).str[:7],
        income=data.monthly["income"].astype(float),
        expense=data.monthly["expense"].astype(float),
        net=data.monthly["net"].astype(float),
    ).rename(columns={"month": L["col_month"], "income": L["kind_income"], "expense": L["kind_expense"], "net": L["m_net"]})
    merchants = data.merchants.assign(
        total=data.merchants["total"].astype(float),
        txn_type=data.merchants["txn_type"].map(lambda code: L.get(f"type_{code}", code)),
    ).rename(
        columns={"merchant": L["col_merchant"], "txn_type": L["col_type"], "count": L["col_count"], "total": L["col_total"]}
    )
    transactions = data.transactions.assign(amount=data.transactions["amount"].astype(float)).rename(
        columns={"date": L["col_date"], "bank": L["col_bank"], "description": L["col_description"],
                 "merchant": L["col_merchant"], "category": L["col_category"], "amount": L["col_amount"]}
    )

    sheets = (L["report_sheet_summary"], L["report_sheet_categories"], L["report_sheet_merchants"], L["report_sheet_transactions"])
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        row = _write_table(writer, sheets[0], summary, 2)
        _write_table(writer, sheets[0], monthly, row, money, L["monthly_chart"])
        ws = writer.book[sheets[0]]
        ws["A1"] = f"{L['report_title']} · {data.start} – {data.end}"
        ws["A1"].font = Font(bold=True, size=14)

        row = _write_table(writer, sheets[1], categories(data.expense_categories), 0, money, L["spending_by_category"])
        _write_table(writer, sheets[1], categories(data.income_categories), row, money, L["income_by_category"])
        _write_table(writer, sheets[2], merchants, 0, money)
        _write_table(writer, sheets[3], transactions, 0, money)

        tx = writer.book[sheets[3]]
        tx.freeze_panes = "A2"
        tx.auto_filter.ref = tx.dimensions
        for ws in writer.book.worksheets:
            for column in ws.columns:
                width = max((len(str(c.value)) for c in column if c.value is not None and c.row > 1), default=8)
                ws.column_dimensions[get_column_letter(column[0].column)].width = min(max(width + 2, 10), 60)
    return out.getvalue()


# --- PDF ----------------------------------------------------------------------------


def _font_paths() -> tuple[Path, Path]:
    for regular, bold in FONT_CANDIDATES:
        if regular.exists() and bold.exists():
            return regular, bold
    raise RuntimeError("No font with Mongolian Cyrillic found (Segoe UI, Arial or Calibri).")


def to_pdf(data: ReportData, labels: dict[str, str]) -> bytes:
    """A4 summary: KPIs, months, category bars, merchants and the transaction list."""
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    regular, bold = _font_paths()
    # Embedding Segoe UI logs harmless "MERG NOT subset" notes; keep the terminal clean.
    logging.getLogger("fontTools.subset").setLevel(logging.ERROR)

    class Report(FPDF):
        def footer(self) -> None:
            self.set_y(-12)
            self.set_font("ui", size=8)
            self.set_text_color(120)
            self.cell(0, 6, f"FinTrack · {labels['report_page']} {self.page_no()}/{{nb}}", align="C")

    pdf = Report(format="A4")
    pdf.add_font("ui", "", str(regular))
    pdf.add_font("ui", "B", str(bold))
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(14, 14, 14)
    pdf.add_page()
    heading = FontFace(emphasis="BOLD", fill_color=(232, 238, 247))
    # Explicit zebra fill: tables otherwise inherit the last fill colour (the red bars).
    zebra = {"cell_fill_color": (248, 250, 252), "cell_fill_mode": "ROWS", "headings_style": heading}

    def section(title: str) -> None:
        pdf.ln(4)
        pdf.set_font("ui", "B", 12)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0)
        pdf.set_fill_color(255)  # zebra rows alternate with the current fill colour
        pdf.set_font("ui", size=9)

    # Title
    pdf.set_font("ui", "B", 18)
    pdf.cell(0, 10, labels["report_title"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("ui", size=10)
    pdf.set_text_color(90)
    pdf.cell(0, 6, f"{labels['period']}: {data.start} – {data.end}   ·   "
                   f"{labels['report_generated']}: {data.generated:%Y-%m-%d %H:%M}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)

    # KPI cards
    pdf.ln(4)
    card_w = (pdf.epw - 3 * 4) / 4
    y = pdf.get_y()
    for i, (label, value) in enumerate(_kpis(data, labels)):
        x = pdf.l_margin + i * (card_w + 4)
        pdf.set_fill_color(246, 248, 251)
        pdf.set_draw_color(210, 216, 226)
        pdf.rect(x, y, card_w, 20, style="DF", round_corners=True, corner_radius=2)
        pdf.set_xy(x + 3, y + 3)
        pdf.set_font("ui", size=8)
        pdf.set_text_color(90)
        pdf.cell(card_w - 6, 5, label)
        pdf.set_xy(x + 3, y + 9)
        pdf.set_font("ui", "B", 12)
        pdf.set_text_color(0)
        pdf.cell(card_w - 6, 8, value)
    pdf.set_y(y + 24)

    # Monthly
    if not data.monthly.empty:
        section(labels["monthly_chart"])
        with pdf.table(col_widths=(25, 25, 25, 25), text_align=("LEFT", "RIGHT", "RIGHT", "RIGHT"),
                       **zebra, line_height=6) as table:
            table.row([labels["col_month"], labels["kind_income"], labels["kind_expense"], labels["m_net"]])
            for row in data.monthly.itertuples():
                table.row([str(row.month)[:7], _money(row.income), _money(row.expense), _money(row.net)])

    # Expense categories with proportional bars
    if not data.expense_categories.empty:
        section(labels["spending_by_category"])
        top = float(data.expense_categories["total"].max()) or 1.0
        name_w, bar_w = 62, pdf.epw - 62 - 50
        for row in data.expense_categories.itertuples():
            pdf.set_font("ui", size=9)
            pdf.cell(name_w, 6, str(row.category)[:40])
            x, y = pdf.get_x(), pdf.get_y()
            pdf.set_fill_color(209, 73, 91)
            pdf.rect(x, y + 1.2, max(bar_w * float(row.total) / top, 0.5), 3.6, style="F")
            pdf.set_x(x + bar_w + 2)
            pdf.cell(48, 6, f"{_money(row.total)}  ({row.pct:.1f}%)", align="R", new_x="LMARGIN", new_y="NEXT")

    # Income categories and top merchants
    if not data.income_categories.empty:
        section(labels["income_by_category"])
        with pdf.table(col_widths=(50, 25, 12, 13), text_align=("LEFT", "RIGHT", "RIGHT", "RIGHT"),
                       **zebra, line_height=6) as table:
            table.row([labels["col_category"], labels["col_total"], labels["col_pct"], labels["col_count"]])
            for row in data.income_categories.itertuples():
                table.row([str(row.category), _money(row.total), f"{row.pct:.1f}", str(row.count)])
    if not data.merchants.empty:
        section(labels["report_top_merchants"])
        with pdf.table(col_widths=(55, 20, 10, 25), text_align=("LEFT", "LEFT", "RIGHT", "RIGHT"),
                       **zebra, line_height=6) as table:
            table.row([labels["col_merchant"], labels["col_type"], labels["col_count"], labels["col_total"]])
            for row in data.merchants.itertuples():
                table.row([str(row.merchant), labels.get(f"type_{row.txn_type}", str(row.txn_type)), str(row.count), _money(row.total)])

    # Transactions
    section(f"{labels['report_transactions']} ({len(data.transactions)})")
    pdf.set_font("ui", size=7.5)
    with pdf.table(col_widths=(16, 50, 34, 30, 20), text_align=("LEFT", "LEFT", "LEFT", "LEFT", "RIGHT"),
                   **zebra, line_height=4.6, repeat_headings=1) as table:
        table.row([labels["col_date"], labels["col_description"], labels["col_merchant"],
                   labels["col_category"], labels["col_amount"]])
        for row in data.transactions.itertuples():
            description = str(row.description)
            table.row([
                str(row.date), description[:70] + ("…" if len(description) > 70 else ""),
                str(row.merchant)[:40], str(row.category), _money(row.amount),
            ])
    return bytes(pdf.output())


def export(
    engine: Engine, start: date, end: date, labels: dict[str, str], kind: str, lang: str = "mn"
) -> bytes:
    """Build and render in one go (used as the lazy download callable)."""
    with engine.connect() as conn:
        data = build_report(conn, start, end, lang)
    return to_excel(data, labels) if kind == "xlsx" else to_pdf(data, labels)
