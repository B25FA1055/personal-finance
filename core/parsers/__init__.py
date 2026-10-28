"""Registry of bank statement parsers."""

from pathlib import Path

from core.parsers.base import BaseParser, Statement, Txn
from core.parsers.generic import TableParser, UnknownBankError
from core.parsers.golomt import GolomtParser
from core.parsers.khan import KhanParser
from core.parsers.xac import XacParser

# Order matters: Xac's exact layout first, then banks recognised by header markers.
PARSERS: list[BaseParser] = [XacParser(), KhanParser(), GolomtParser()]
BANK_CODES = [parser.bank_code for parser in PARSERS]


def detect_parser(path: str | Path, bank_code: str | None = None) -> BaseParser:
    """Parser for this file. bank_code forces a bank when the file doesn't name one."""
    if bank_code:
        parser = next((p for p in PARSERS if p.bank_code == bank_code), None)
        if parser is None:
            raise ValueError(f"Unknown bank: {bank_code}")
        if isinstance(parser, TableParser) and parser.looks_like_statement(path):
            return parser
        if parser.can_parse(path):
            return parser
        raise ValueError(f"This file is not in a format the {bank_code} parser understands.")

    for parser in PARSERS:
        if parser.can_parse(path):
            return parser
    if any(isinstance(p, TableParser) and p.looks_like_statement(path) for p in PARSERS):
        raise UnknownBankError("The bank could not be identified from the file; choose it manually.")
    raise ValueError(f"No parser recognises file: {Path(path).name}")


__all__ = [
    "BANK_CODES",
    "PARSERS",
    "BaseParser",
    "GolomtParser",
    "KhanParser",
    "Statement",
    "Txn",
    "UnknownBankError",
    "XacParser",
    "detect_parser",
]
