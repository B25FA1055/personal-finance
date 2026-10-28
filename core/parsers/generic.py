"""Header-driven statement parser shared by banks whose exact layout may vary.

Instead of fixed cell positions it finds the transaction table by its column names
(Mongolian or English), reads account details from "label: value" cells above it, and
validates the result against the balances. A subclass only names its bank and the
words that identify it in the file header.
"""

import hashlib
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from core.parsers.base import BaseParser, Statement, Txn
from core.parsers.reader import SUPPORTED_SUFFIXES, read_rows

# Column name -> field. Compared case-insensitively after collapsing whitespace.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("огноо", "гүйлгээний огноо", "огноо/цаг", "date", "transaction date", "txn date", "posting date"),
    "description": ("гүйлгээний утга", "утга", "тайлбар", "гүйлгээний тайлбар", "description", "details", "narrative"),
    "counterparty": ("харьцсан данс", "харилцагч", "хүлээн авагч", "харьцсан дансны нэр", "counterparty", "beneficiary"),
    "income": ("орлого", "кредит", "credit", "орлогын дүн", "credit amount", "deposit"),
    "expense": ("зарлага", "дебит", "debit", "зарлагын дүн", "debit amount", "withdrawal"),
    "amount": ("дүн", "гүйлгээний дүн", "amount", "transaction amount"),
    "balance": ("үлдэгдэл", "balance", "гүйлгээний дараах үлдэгдэл", "running balance"),
    "ref": ("гүйлгээний дугаар", "лавлах дугаар", "журналын дугаар", "reference", "ref", "transaction id"),
}

LABELS = {
    "account": ("дансны дугаар", "account number", "account no", "данс"),
    "holder": ("харилцагч", "данс эзэмшигч", "эзэмшигч", "үндсэн эзэмшигч", "account holder", "customer", "нэр"),
    "opening": ("эхний үлдэгдэл", "opening balance", "beginning balance"),
    "closing": ("эцсийн үлдэгдэл", "closing balance", "ending balance"),
    "period": ("хамрах хугацаа", "хугацаа", "period", "statement period"),
}

TOTAL_ROW = re.compile(r"^\s*(нийт|бүгд|total|дүн)\b", re.I)
OPENING_ROW = re.compile(r"эхний үлдэгдэл|opening balance", re.I)
CLOSING_ROW = re.compile(r"эцсийн үлдэгдэл|closing balance", re.I)
DATE_RE = re.compile(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})|(\d{1,2})[./-](\d{1,2})[./-](\d{4})")
CENT = Decimal("0.01")


class UnknownBankError(ValueError):
    """The file looks like a statement but the bank could not be identified."""


def _key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().strip(":").casefold()


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))  # account numbers / refs read from Excel as 457200933.0
    return str(value).strip()


def parse_amount(value: Any) -> Decimal:
    """'1,234.50', '(1,234.50)', '-1 234,50'? -> Decimal. Empty or '-' -> 0."""
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(CENT)
    raw = text(value).replace("₮", "").replace("MNT", "").replace("−", "-").replace(" ", "")
    if raw in ("", "-"):
        return Decimal("0.00")
    negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.strip("()").replace(",", "")
    try:
        amount = Decimal(raw).quantize(CENT)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid amount: {value!r}") from exc
    return -amount if negative else amount


def parse_date(value: Any) -> date | None:
    """datetime, Excel serial number, or text like 2026/01/31, 2026.01.31 or 31.01.2026."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and 30000 < value < 80000:  # Excel serial day
        return date(1899, 12, 30) + timedelta(days=int(value))
    match = DATE_RE.search(text(value))
    if not match:
        return None
    if match.group(1):
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
    else:
        d, m, y = int(match.group(4)), int(match.group(5)), int(match.group(6))
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _match_columns(row: list[Any]) -> dict[str, int]:
    names = [_key(cell) for cell in row]
    columns: dict[str, int] = {}
    for field, aliases in COLUMN_ALIASES.items():
        for index, name in enumerate(names):
            if name in aliases and index not in columns.values():
                columns[field] = index
                break
    return columns


def _align_columns(rows: list[list[Any]], header_index: int, columns: dict[str, int]) -> dict[str, int]:
    """Move each column onto where its values really are.

    Exports with merged header cells put a title one or more cells right of its data
    ('Огноо' in column B, dates in column A). For each field, pick the nearby column
    (within 3) that is filled most often in the first data rows; ties go to the closest.
    """
    sample = [
        row for row in rows[header_index + 1 : header_index + 120]
        if any(text(value) for value in row)
    ][:25]
    if not sample:
        return columns

    def filled(field: str, column: int) -> int:
        values = [row[column] if column < len(row) else None for row in sample]
        if field == "date":
            return sum(parse_date(value) is not None for value in values)
        return sum(bool(text(value)) for value in values)

    if filled("date", columns["date"]):
        return columns  # titles sit over their data: a normal table, leave it alone

    # 1) One shift for the whole table (titles usually move together); dates decide.
    def table_score(shift: int) -> tuple[int, int, int]:
        moved = {f: c + shift for f, c in columns.items()}
        if min(moved.values()) < 0:
            return (-1, -1, 0)
        return (filled("date", moved["date"]), sum(bool(filled(f, c)) for f, c in moved.items()), -abs(shift))

    shift = max(range(-3, 4), key=table_score)
    aligned = {field: column + shift for field, column in columns.items()}

    # 2) Fine-tune columns that are still empty (merged cells can differ per column).
    for field, column in sorted(aligned.items(), key=lambda item: item[1]):
        if filled(field, column):
            continue
        taken = set(aligned.values()) - {column}
        nearby = sorted((c for c in range(max(0, column - 3), column + 4) if c not in taken), key=lambda c: abs(c - column))
        aligned[field] = next((c for c in nearby if filled(field, c)), column)
    return aligned


def find_table(rows: list[list[Any]]) -> tuple[int, dict[str, int]] | None:
    """Index and column map of the transaction header row, if the file has one."""
    for index, row in enumerate(rows[:60]):
        columns = _match_columns(row)
        has_money = ("income" in columns and "expense" in columns) or "amount" in columns
        if "date" in columns and "description" in columns and has_money:
            return index, _align_columns(rows, index, columns)
    return None


def _label_value(rows: list[list[Any]], labels: tuple[str, ...]) -> str:
    """Value for 'Label: value' (same cell) or 'Label' | value (next non-empty cell)."""
    for row in rows:
        for index, cell in enumerate(row):
            raw = text(cell)
            if ":" in raw:
                label, _, rest = raw.partition(":")
                if _key(label) in labels and rest.strip():
                    return rest.strip()
            if _key(raw) in labels:
                for value in row[index + 1 :]:
                    if text(value):
                        return text(value)
    return ""


def _synthetic_ref(txn_date: date, amount: Decimal, balance: Decimal | None, description: str, seen: dict) -> str:
    """Stable id for banks without a reference column, so re-imports are de-duplicated."""
    base = f"{txn_date}|{amount}|{balance}|{description}"
    seen[base] = seen.get(base, 0) + 1
    return "H" + hashlib.sha1(f"{base}|{seen[base]}".encode()).hexdigest()[:16]


class TableParser(BaseParser):
    """Generic parser; subclasses set bank_code and header markers that identify the bank."""

    markers: tuple[str, ...] = ()

    def _header_text(self, path: str | Path) -> tuple[list[list[Any]], str] | None:
        if Path(path).suffix.lower() not in SUPPORTED_SUFFIXES:
            return None
        try:
            rows = read_rows(path)
        except Exception:  # unreadable or not a spreadsheet
            return None
        table = find_table(rows)
        if table is None:
            return None
        header = " ".join(text(cell) for row in rows[: table[0]] for cell in row)
        return rows, header.casefold()

    def looks_like_statement(self, path: str | Path) -> bool:
        return self._header_text(path) is not None

    def can_parse(self, path: str | Path) -> bool:
        found = self._header_text(path)
        return found is not None and any(marker in found[1] for marker in self.markers)

    def parse(self, path: str | Path) -> Statement:
        rows = read_rows(path)
        table = find_table(rows)
        if table is None:
            raise ValueError("No transaction table found (need date, description and amount columns).")
        header_index, columns = table
        header_rows = rows[:header_index]

        account_raw = _label_value(header_rows, LABELS["account"])
        account = re.search(r"\d[\d\s-]{5,}\d", account_raw)
        if not account:
            raise ValueError("Account number not found in the statement header.")
        account_number = re.sub(r"\D", "", account.group())
        currency = next((c for c in ("MNT", "USD", "EUR", "CNY", "RUB") if c in account_raw.upper()), "MNT")

        holder = re.sub(r"\s*\(.*$", "", _label_value(header_rows, LABELS["holder"])).strip()
        opening = self._optional_amount(_label_value(header_rows, LABELS["opening"]))
        closing = self._optional_amount(_label_value(header_rows, LABELS["closing"]))
        period_dates = [parse_date(m.group()) for m in DATE_RE.finditer(_label_value(header_rows, LABELS["period"]))]

        def cell(row: list[Any], field: str) -> Any:
            index = columns.get(field)
            return row[index] if index is not None and index < len(row) else None

        txns: list[Txn] = []
        refs: dict[str, int] = {}
        hashes: dict = {}
        for row in rows[header_index + 1 :]:
            first = " ".join(text(v) for v in row[:3])
            if TOTAL_ROW.match(first):
                break
            description = text(cell(row, "description"))
            if OPENING_ROW.search(first) or OPENING_ROW.search(description):
                opening = opening if opening is not None else self._optional_amount(cell(row, "balance"))
                continue
            if CLOSING_ROW.search(first) or CLOSING_ROW.search(description):
                closing = closing if closing is not None else self._optional_amount(cell(row, "balance"))
                break
            txn_date = parse_date(cell(row, "date"))
            if txn_date is None:
                continue  # blank, page-break or footer row
            if "amount" in columns and "income" not in columns:
                amount = parse_amount(cell(row, "amount"))
            else:
                amount = abs(parse_amount(cell(row, "income"))) - abs(parse_amount(cell(row, "expense")))
            if amount == 0:
                continue
            balance = self._optional_amount(cell(row, "balance"))
            ref = text(cell(row, "ref"))
            if ref:
                refs[ref] = refs.get(ref, 0) + 1
                if refs[ref] > 1:
                    ref = f"{ref}#{refs[ref]}"
            else:
                ref = _synthetic_ref(txn_date, amount, balance, description, hashes)
            txns.append(Txn(txn_date, description, text(cell(row, "counterparty")), ref, amount, balance))

        if not txns:
            raise ValueError("The statement contains no transactions.")
        if txns[0].txn_date > txns[-1].txn_date:
            txns.reverse()  # newest-first exports
        opening, closing = self._validate(txns, opening, closing)

        return Statement(
            bank_code=self.bank_code,
            account_number=account_number,
            holder=holder,
            currency=currency,
            period_start=period_dates[0] if period_dates and period_dates[0] else txns[0].txn_date,
            period_end=period_dates[-1] if len(period_dates) > 1 and period_dates[-1] else txns[-1].txn_date,
            opening_balance=opening,
            closing_balance=closing,
            txns=txns,
        )

    @staticmethod
    def _optional_amount(value: Any) -> Decimal | None:
        if not text(value):
            return None
        try:
            return parse_amount(value)
        except ValueError:
            return None

    @staticmethod
    def _validate(
        txns: list[Txn], opening: Decimal | None, closing: Decimal | None
    ) -> tuple[Decimal | None, Decimal | None]:
        """Check the money adds up using whatever balances the bank provides."""
        balances = [t.balance for t in txns]
        if all(b is not None for b in balances):
            if opening is None:
                opening = balances[0] - txns[0].amount
            running = opening
            for txn in txns:
                running += txn.amount
                if running != txn.balance:
                    raise ValueError(
                        f"Running balance mismatch on {txn.txn_date}: expected {running}, file says {txn.balance}"
                    )
            closing = closing if closing is not None else running
        total = sum((t.amount for t in txns), Decimal("0.00"))
        if opening is not None and closing is not None and opening + total != closing:
            raise ValueError(f"Balance mismatch: opening {opening} + transactions {total} != closing {closing}")
        return opening, closing
