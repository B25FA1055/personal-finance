"""Khan Bank statement exports (.xlsx / .xls / .csv), parsed by column names."""

from core.parsers.generic import TableParser


class KhanParser(TableParser):
    bank_code = "khan"
    # Not plain "хаан": it is also part of personal names (Хаанчулуун...).
    markers = ("хаан банк", "khan bank", "khanbank")
