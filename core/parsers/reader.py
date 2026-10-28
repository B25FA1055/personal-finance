"""Read the first sheet of a statement file (.xlsx, .xls or .csv) into rows of raw values."""

import csv
import io
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = (".xlsx", ".xls", ".csv")


def read_rows(path: str | Path) -> list[list[Any]]:
    """Rows of cell values; dates come back as datetime where the file marks them as dates."""
    suffix = Path(path).suffix.lower()
    if suffix == ".xlsx":
        return _read_xlsx(path)
    if suffix == ".xls":
        return _read_xls(path)
    if suffix == ".csv":
        return _read_csv(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def _read_xlsx(path: str | Path) -> list[list[Any]]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        sheet.reset_dimensions()  # some bank exports declare a bogus sheet size
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _read_xls(path: str | Path) -> list[list[Any]]:
    import xlrd

    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)
    rows = []
    for r in range(sheet.nrows):
        row = []
        for cell in sheet.row(r):
            if cell.ctype == xlrd.XL_CELL_DATE:
                row.append(xlrd.xldate_as_datetime(cell.value, book.datemode))
            elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                row.append(None)
            else:
                row.append(cell.value)
        rows.append(row)
    return rows


def _read_csv(path: str | Path) -> list[list[Any]]:
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "cp1251"):  # Excel on Mongolian Windows often saves CP1251
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Could not decode the CSV file (expected UTF-8 or Windows-1251).")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [list(row) for row in csv.reader(io.StringIO(text), dialect)]
