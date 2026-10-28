"""Golomt Bank statement exports (.xlsx / .xls / .csv), parsed by column names."""

from core.parsers.generic import TableParser


class GolomtParser(TableParser):
    bank_code = "golomt"
    markers = ("голомт", "golomt")
