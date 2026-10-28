"""Parser for Xac Bank 'AccountStatement' .xlsx exports (every cell is text)."""

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from core.parsers.base import BaseParser, Statement, Txn

SHEET_TITLE = "AccountStatement"
TITLE_TEXT = "ДАНСНЫ ХУУЛГА"
HEADER_TEXT = "Огноо"
OPENING_TEXT = "Эхний үлдэгдэл"
CLOSING_TEXT = "Эцсийн үлдэгдэл"

LABEL_ACCOUNT = "Дансны дугаар:"
LABEL_HOLDER = "Үндсэн эзэмшигч:"
LABEL_CURRENCY = "Валют:"
LABEL_START = "Эхлэх:"
LABEL_END = "Дуусах:"

_HEADER_ALIASES = {
    "date": ("Огноо", "Date", "Transaction Date"),
    "description": (
        "Гүйлгээний утга",
        "Гүйлгээний тайлбар",
        "Description",
        "Transaction Description",
    ),
    "counterparty": ("Харьцсан данс", "Counterparty"),
    "bank_ref": ("Гүйлгээний дугаар", "Reference", "Transaction ID"),
    "income": ("Орлого", "Credit", "Income"),
    "expense": ("Зарлага", "Debit", "Expense"),
    "balance": ("Үлдэгдэл", "Balance"),
}

_CENT = Decimal("0.01")


def cell_text(value: Any) -> str:
    """Return a stripped string for any cell value (None -> '')."""
    return "" if value is None else str(value).strip()


def parse_amount(value: Any) -> Decimal:
    """Parse '4,750.00' -> Decimal('4750.00'); '-', '' and None -> Decimal('0.00')."""
    text = cell_text(value).replace(",", "").replace(" ", "")
    if text in ("", "-"):
        return Decimal("0.00")
    try:
        return Decimal(text).quantize(_CENT)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid amount: {value!r}") from exc


def parse_date(value: Any) -> date:
    """Parse 'YYYY-MM-DD' (optionally followed by a time) into a date."""
    if isinstance(value, date):
        return value
    text = cell_text(value)
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"Invalid date: {value!r}") from exc


def _find_label_value(rows: list[tuple[str, ...]], label: str) -> str:
    """Return the cell right of the first cell whose text equals label."""
    for row in rows:
        for index, text in enumerate(row[:-1]):
            if text == label:
                return row[index + 1]
    return ""


def _find_header_row(rows: list[tuple[str, ...]]) -> tuple[int, dict[str, int]]:
    for index, row in enumerate(rows):
        normalized = {cell.casefold(): column for column, cell in enumerate(row) if cell}
        if HEADER_TEXT.casefold() not in normalized:
            continue

        columns: dict[str, int] = {}
        for field, aliases in _HEADER_ALIASES.items():
            for alias in aliases:
                column = normalized.get(alias.casefold())
                if column is not None:
                    columns[field] = column
                    break

        required_fields = {"date", "description", "bank_ref", "income", "expense", "balance"}
        missing_fields = required_fields - columns.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"Xac Bank header is missing required columns: {missing}")
        return index, columns
    raise ValueError(f"Header row with '{HEADER_TEXT}' not found")


def _read_rows(path: str | Path) -> list[tuple[str, ...]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[SHEET_TITLE]
        # Xac exports declare a bogus 1-cell dimension; read-only mode trusts
        # it and would return a single empty row unless it is reset.
        sheet.reset_dimensions()
        rows = [
            tuple(cell_text(value) for value in row)
            for row in sheet.iter_rows(values_only=True)
        ]
    finally:
        workbook.close()
    width = max((len(row) for row in rows), default=0)
    return [row + ("",) * (width - len(row)) for row in rows]


class XacParser(BaseParser):
    bank_code = "xac"

    def can_parse(self, path: str | Path) -> bool:
        if Path(path).suffix.lower() != ".xlsx":
            return False
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
        except Exception:  # corrupt or not a workbook: simply not a Xac export
            return False
        try:
            if SHEET_TITLE not in workbook.sheetnames:
                return False
            sheet = workbook[SHEET_TITLE]
            sheet.reset_dimensions()
            first_row = next(sheet.iter_rows(max_row=1, values_only=True), ())
            return any(
                cell_text(value).casefold() == TITLE_TEXT.casefold()
                for value in first_row
            )
        finally:
            workbook.close()

    def parse(self, path: str | Path) -> Statement:
        rows = _read_rows(path)
        header_index, columns = _find_header_row(rows)
        header_rows = rows[:header_index]

        period_start = _find_label_value(header_rows, LABEL_START)
        period_end = _find_label_value(header_rows, LABEL_END)

        opening: Decimal | None = None
        closing: Decimal | None = None
        txns: list[Txn] = []
        ref_counts: dict[str, int] = {}

        for row in rows[header_index + 1:]:
            description = row[columns["description"]]
            if description == OPENING_TEXT:
                opening = parse_amount(row[columns["balance"]])
                continue
            if description == CLOSING_TEXT:
                closing = parse_amount(row[columns["balance"]])
                break
            bank_ref = row[columns["bank_ref"]]
            if not bank_ref:
                continue
            # An inter-bank fee shares the transfer's reference; suffix repeats
            # ('SX7000325#2') so both rows survive UNIQUE(account_id, bank_ref).
            ref_counts[bank_ref] = ref_counts.get(bank_ref, 0) + 1
            if ref_counts[bank_ref] > 1:
                bank_ref = f"{bank_ref}#{ref_counts[bank_ref]}"
            txns.append(
                Txn(
                    txn_date=parse_date(row[columns["date"]]),
                    description=description,
                    counterparty=(
                        row[columns["counterparty"]]
                        if "counterparty" in columns
                        else ""
                    ),
                    bank_ref=bank_ref,
                    amount=(
                        parse_amount(row[columns["income"]])
                        - parse_amount(row[columns["expense"]])
                    ),
                    balance=parse_amount(row[columns["balance"]]),
                )
            )

        if opening is None:
            raise ValueError(f"'{OPENING_TEXT}' row not found")
        if closing is None:
            raise ValueError(f"'{CLOSING_TEXT}' row not found")

        total = sum((txn.amount for txn in txns), Decimal("0.00"))
        if opening + total != closing:
            raise ValueError(
                f"Balance mismatch: opening {opening} + transactions {total} "
                f"!= closing {closing}"
            )

        return Statement(
            bank_code=self.bank_code,
            account_number=_find_label_value(header_rows, LABEL_ACCOUNT),
            holder=_find_label_value(header_rows, LABEL_HOLDER),
            currency=_find_label_value(header_rows, LABEL_CURRENCY) or "MNT",
            period_start=parse_date(period_start) if period_start else None,
            period_end=parse_date(period_end) if period_end else None,
            opening_balance=opening,
            closing_balance=closing,
            txns=txns,
        )
