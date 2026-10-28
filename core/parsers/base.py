"""Bank-independent statement data structures and parser interface."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path


@dataclass
class Txn:
    txn_date: date
    description: str
    counterparty: str
    bank_ref: str
    amount: Decimal  # signed: + money in, - money out
    balance: Decimal | None  # running balance, if the bank exports one


@dataclass
class Statement:
    bank_code: str
    account_number: str
    holder: str
    currency: str
    period_start: date | None
    period_end: date | None
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    txns: list[Txn] = field(default_factory=list)


class BaseParser:
    bank_code: str = ""

    def can_parse(self, path: str | Path) -> bool:
        raise NotImplementedError

    def parse(self, path: str | Path) -> Statement:
        raise NotImplementedError
