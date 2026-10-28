"""Import a bank statement file: parse -> dedupe -> insert -> classify."""

import hashlib
from collections import Counter
from datetime import date, timedelta
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, text

from core import classifier
from core.classify_service import NEEDS_REVIEW
from core.merchant import extract_merchant
from core.parsers import detect_parser


@dataclass
class ImportResult:
    import_id: int | None
    rows_read: int
    inserted: int
    skipped: int
    unclassified: int
    duplicate_file: bool
    message: str
    # Continuity with this account's previous import (both None/False when fine):
    gap_from: date | None = None
    gap_to: date | None = None
    opening_mismatch: bool = False


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


BANK_NAMES = {"xac": "Xac Bank", "khan": "Khan Bank", "golomt": "Golomt Bank"}


def import_file(
    path: str | Path,
    file_name: str,
    engine: Engine | None = None,
    bank_code: str | None = None,
) -> ImportResult:
    """Import one statement in a single transaction (rolled back on any error).

    bank_code forces the bank for files that don't name it (see detect_parser).
    """
    if engine is None:
        from core.db import get_engine

        engine = get_engine()

    digest = file_sha256(path)

    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM imports WHERE file_sha256 = :sha"), {"sha": digest}
        ).scalar_one_or_none()
        if existing is not None:
            return ImportResult(
                existing, 0, 0, 0, 0, True, f"'{file_name}' was already imported"
            )

        stmt = detect_parser(path, bank_code).parse(path)

        bank_id = conn.execute(
            text(
                "INSERT INTO banks (code, name) VALUES (:code, :name) "
                "ON CONFLICT (code) DO UPDATE SET code = EXCLUDED.code RETURNING id"
            ),
            {"code": stmt.bank_code, "name": BANK_NAMES.get(stmt.bank_code, stmt.bank_code)},
        ).scalar_one()

        account_id = conn.execute(
            text(
                "INSERT INTO accounts (bank_id, account_number, holder, currency, is_own) "
                "VALUES (:bank_id, :number, :holder, :currency, TRUE) "
                "ON CONFLICT (bank_id, account_number) DO UPDATE "
                "SET holder = EXCLUDED.holder, currency = EXCLUDED.currency "
                "RETURNING id"
            ),
            {
                "bank_id": bank_id,
                "number": stmt.account_number,
                "holder": stmt.holder,
                "currency": stmt.currency,
            },
        ).scalar_one()
        # The imported account is the user's own: transfers to it from their other
        # banks' statements become Internal Transfer instead of expense/income.
        conn.execute(
            text(
                "INSERT INTO own_account_numbers (number, label) VALUES (:number, :label) "
                "ON CONFLICT (number) DO NOTHING"
            ),
            {"number": stmt.account_number, "label": BANK_NAMES.get(stmt.bank_code, stmt.bank_code)},
        )

        import_id = conn.execute(
            text(
                "INSERT INTO imports (account_id, file_name, file_sha256, period_start, "
                "period_end, opening_balance, closing_balance, rows_read) "
                "VALUES (:account_id, :file_name, :sha, :start, :end, :opening, "
                ":closing, :rows_read) RETURNING id"
            ),
            {
                "account_id": account_id,
                "file_name": file_name,
                "sha": digest,
                "start": stmt.period_start,
                "end": stmt.period_end,
                "opening": stmt.opening_balance,
                "closing": stmt.closing_balance,
                "rows_read": len(stmt.txns),
            },
        ).scalar_one()

        gap_from = gap_to = None
        opening_mismatch = False
        previous = conn.execute(
            text(
                "SELECT period_end, closing_balance FROM imports "
                "WHERE account_id = :account_id AND id <> :import_id AND period_end IS NOT NULL "
                "ORDER BY period_end DESC LIMIT 1"
            ),
            {"account_id": account_id, "import_id": import_id},
        ).first()
        if previous and stmt.period_start:
            next_day = previous.period_end + timedelta(days=1)
            if stmt.period_start > next_day:
                gap_from, gap_to = next_day, stmt.period_start - timedelta(days=1)
            elif (
                stmt.period_start == next_day
                and previous.closing_balance is not None
                and stmt.opening_balance is not None
                and previous.closing_balance != stmt.opening_balance
            ):
                opening_mismatch = True

        # Content duplicates: the same (date, amount, description) already stored for this
        # account, e.g. from an overlapping export with different references. Copies are
        # counted, so three identical 50₮ fees on one day stay three rows.
        stored = Counter()
        if stmt.txns:
            for row in conn.execute(
                text(
                    "SELECT txn_date::date AS d, amount, description, COUNT(*) AS n "
                    "FROM transactions WHERE account_id = :account_id "
                    "AND txn_date::date BETWEEN :first AND :last GROUP BY 1, 2, 3"
                ),
                {
                    "account_id": account_id,
                    "first": min(t.txn_date for t in stmt.txns),
                    "last": max(t.txn_date for t in stmt.txns),
                },
            ):
                stored[(row.d, row.amount, row.description)] = row.n
        seen = Counter()

        merchant_ids: dict[str, int] = {}
        new_ids: list[int] = []
        for txn in stmt.txns:
            key = (txn.txn_date, txn.amount, txn.description)
            seen[key] += 1
            if seen[key] <= stored[key]:
                continue  # this copy is already in the database
            txn_type, merchant = extract_merchant(txn.description, txn.counterparty)
            merchant_id = None
            if merchant:
                if merchant not in merchant_ids:
                    merchant_ids[merchant] = conn.execute(
                        text(
                            "INSERT INTO merchants (name, txn_type) VALUES (:name, :type) "
                            "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
                            "RETURNING id"
                        ),
                        {"name": merchant, "type": txn_type},
                    ).scalar_one()
                merchant_id = merchant_ids[merchant]

            new_id = conn.execute(
                text(
                    "INSERT INTO transactions (account_id, import_id, txn_date, "
                    "description, counterparty, bank_ref, amount, balance, txn_type, "
                    "merchant_id) VALUES (:account_id, :import_id, :txn_date, "
                    ":description, :counterparty, :bank_ref, :amount, :balance, "
                    ":txn_type, :merchant_id) "
                    "ON CONFLICT (account_id, bank_ref) DO NOTHING RETURNING id"
                ),
                {
                    "account_id": account_id,
                    "import_id": import_id,
                    "txn_date": txn.txn_date,
                    "description": txn.description,
                    "counterparty": txn.counterparty,
                    "bank_ref": txn.bank_ref,
                    "amount": txn.amount,
                    "balance": txn.balance,
                    "txn_type": txn_type,
                    "merchant_id": merchant_id,
                },
            ).scalar_one_or_none()
            if new_id is not None:
                new_ids.append(new_id)

        conn.execute(
            text("UPDATE imports SET rows_inserted = :n WHERE id = :id"),
            {"n": len(new_ids), "id": import_id},
        )
        classifier.apply(conn, new_ids)

        unclassified = 0
        if new_ids:
            unclassified = conn.execute(
                text(
                    "SELECT COUNT(*) FROM transactions t "
                    f"WHERE t.id = ANY(:ids) AND {NEEDS_REVIEW}"
                ),
                {"ids": new_ids},
            ).scalar_one()

    rows_read = len(stmt.txns)
    inserted = len(new_ids)
    return ImportResult(
        import_id,
        rows_read,
        inserted,
        rows_read - inserted,
        unclassified,
        False,
        f"'{file_name}': {inserted} inserted, {rows_read - inserted} skipped, "
        f"{unclassified} to review",
        gap_from=gap_from,
        gap_to=gap_to,
        opening_mismatch=opening_mismatch,
    )


def main() -> None:
    from core.db import get_engine, init_db
    from core.seed import seed

    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m core.importer <file.xlsx>")
    path = Path(sys.argv[1])
    engine = get_engine()
    init_db(engine)
    seed(engine)
    print(import_file(path, path.name, engine))


if __name__ == "__main__":
    main()
