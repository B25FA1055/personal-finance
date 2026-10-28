"""Save scanned receipts as transactions in a separate 'cash' account.

Card-paid receipts also show up in the next bank statement, so saving checks for a
matching statement transaction (same amount, +/-3 days) and asks before double-counting.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Connection, text

from core import classifier
from core.merchant import normalize

CASH_BANK = "cash"
CASH_ACCOUNT = "CASH"
TXN_TYPE = "cash"


def cash_account_id(conn: Connection) -> int:
    bank_id = conn.execute(
        text(
            "INSERT INTO banks (code, name) VALUES (:code, 'Бэлэн мөнгө') "
            "ON CONFLICT (code) DO UPDATE SET code = EXCLUDED.code RETURNING id"
        ),
        {"code": CASH_BANK},
    ).scalar_one()
    return conn.execute(
        text(
            "INSERT INTO accounts (bank_id, account_number, currency, is_own) "
            "VALUES (:bank_id, :number, 'MNT', TRUE) "
            "ON CONFLICT (bank_id, account_number) DO UPDATE SET is_own = TRUE RETURNING id"
        ),
        {"bank_id": bank_id, "number": CASH_ACCOUNT},
    ).scalar_one()


def receipt_saved(conn: Connection, ref: str) -> bool:
    return conn.execute(
        text("SELECT 1 FROM transactions WHERE bank_ref = :ref"), {"ref": ref}
    ).first() is not None


def possible_duplicates(conn: Connection, txn_date: date, total: Decimal) -> list[dict]:
    """Bank-statement expenses with the same amount within 3 days of the receipt."""
    rows = conn.execute(
        text(
            "SELECT t.txn_date::date AS date, t.description, t.amount "
            "FROM transactions t JOIN accounts a ON a.id = t.account_id "
            "JOIN banks b ON b.id = a.bank_id "
            "WHERE b.code <> :cash AND t.amount = :amount "
            "AND t.txn_date::date BETWEEN :start AND :end ORDER BY t.txn_date"
        ),
        {
            "cash": CASH_BANK,
            "amount": -total,
            "start": txn_date - timedelta(days=3),
            "end": txn_date + timedelta(days=3),
        },
    )
    return [dict(row._mapping) for row in rows]


def suggest_category(conn: Connection, merchant: str, total: Decimal) -> int | None:
    """Category the existing rules would give this merchant (None = no rule matched)."""
    name = normalize(merchant)
    category_id, how = classifier.classify(
        {
            "description": name,
            "counterparty": name,
            "merchant": name,
            "merchant_id": None,
            "amount": -total,
            "txn_type": TXN_TYPE,
        },
        classifier.load_ctx(conn),
    )
    return category_id if how == "rule" else None


def save_receipt(
    conn: Connection,
    *,
    ref: str,
    txn_date: date,
    merchant: str,
    total: Decimal,
    category_id: int | None,
    note: str = "",
) -> int:
    """Insert the receipt as an expense in the cash account; returns the transaction id."""
    name = normalize(merchant)
    merchant_id = conn.execute(
        text(
            "INSERT INTO merchants (name, txn_type) VALUES (:name, :type) "
            "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id"
        ),
        {"name": name, "type": TXN_TYPE},
    ).scalar_one()
    txn_id = conn.execute(
        text(
            "INSERT INTO transactions (account_id, txn_date, description, counterparty, "
            "bank_ref, amount, txn_type, merchant_id, category_id, classified_by, note) "
            "VALUES (:account_id, :txn_date, :description, :counterparty, :ref, :amount, "
            ":txn_type, :merchant_id, :category_id, :classified_by, :note) RETURNING id"
        ),
        {
            "account_id": cash_account_id(conn),
            "txn_date": txn_date,
            "description": f"Баримт: {merchant.strip()}",
            "counterparty": merchant.strip(),
            "ref": ref,
            "amount": -total,
            "txn_type": TXN_TYPE,
            "merchant_id": merchant_id,
            "category_id": category_id,
            "classified_by": "manual" if category_id else None,
            "note": note or None,
        },
    ).scalar_one()
    if category_id is None:
        classifier.apply(conn, [txn_id])  # rules, else the Бусад default
    return txn_id
