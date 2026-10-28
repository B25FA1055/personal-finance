"""Rule engine: own-account transfers -> rules by priority -> merchant default -> Бусад."""

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text

# Category names the engine looks up itself (seeded by core/seed.py).
INTERNAL_TRANSFER = "Дотоод шилжүүлэг"
SAVINGS = "Хуримтлал"  # savings deposits: a transfer, counted towards goals
BANK_FEES = "Банкны шимтгэл"  # fallback for fee-type rows no rule matched
OTHER = "Бусад"  # default for anything no rule recognises (income and expense)


@dataclass(frozen=True)
class Rule:
    id: int
    field: str
    match: str
    pattern: str
    direction: str
    category_id: int
    priority: int


@dataclass
class Ctx:
    rules: list[Rule]
    own_numbers: set[str]
    merchant_defaults: dict[int, int]
    internal_transfer_id: int | None
    other_income_id: int | None = None
    other_expense_id: int | None = None
    bank_fees_id: int | None = None


def rule_matches(rule: Rule, txn: dict[str, Any]) -> bool:
    """True if the rule's direction and pattern match the transaction."""
    amount = txn["amount"]
    if rule.direction == "in" and amount <= 0:
        return False
    if rule.direction == "out" and amount >= 0:
        return False

    value = (txn.get(rule.field) or "").strip().upper()
    pattern = rule.pattern.strip().upper()
    if not pattern:
        return False

    if rule.match == "exact":
        return value == pattern
    if rule.match == "contains":
        return pattern in value
    if rule.match == "startswith":
        return value.startswith(pattern)
    if rule.match == "regex":
        try:
            return re.search(rule.pattern, value, re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def classify(txn: dict[str, Any], ctx: Ctx) -> tuple[int | None, str | None]:
    """Return (category_id, 'rule' | 'merchant' | None) for one transaction."""
    amount = txn["amount"]
    counterparty = (txn.get("counterparty") or "").strip()
    # Fees can name the statement's own account as counterparty
    # ('...шимтгэл-5006017805'); they must stay fees, not transfers.
    if txn.get("txn_type") != "fee" and ctx.internal_transfer_id is not None and any(
        counterparty.endswith(number) for number in ctx.own_numbers
    ):
        return ctx.internal_transfer_id, "rule"

    for rule in ctx.rules:
        if rule_matches(rule, txn):
            return rule.category_id, "rule"

    merchant_id = txn.get("merchant_id")
    if merchant_id is not None and merchant_id in ctx.merchant_defaults:
        return ctx.merchant_defaults[merchant_id], "merchant"

    # Smart fallback: a fee no rule knows is still a bank fee, not "Other".
    if txn.get("txn_type") == "fee" and amount < 0 and ctx.bank_fees_id is not None:
        return ctx.bank_fees_id, "rule"

    if amount > 0 and ctx.other_income_id is not None:
        return ctx.other_income_id, "merchant"
    if amount < 0 and ctx.other_expense_id is not None:
        return ctx.other_expense_id, "merchant"

    return None, None


def load_ctx(conn: Connection) -> Ctx:
    rules = [
        Rule(**row._mapping)
        for row in conn.execute(
            text(
                "SELECT id, field, match, pattern, direction, category_id, priority "
                "FROM rules ORDER BY priority, id"
            )
        )
    ]
    own_numbers = {
        number
        for (number,) in conn.execute(text("SELECT number FROM own_account_numbers"))
        if number
    }
    merchant_defaults = {
        merchant_id: category_id
        for merchant_id, category_id in conn.execute(
            text(
                "SELECT id, default_category_id FROM merchants "
                "WHERE default_category_id IS NOT NULL"
            )
        )
    }
    def category_id(name: str, kind: str) -> int | None:
        return conn.execute(
            text("SELECT id FROM categories WHERE name = :name AND kind = :kind"),
            {"name": name, "kind": kind},
        ).scalar_one_or_none()

    internal_transfer_id = category_id(INTERNAL_TRANSFER, "transfer")
    other_income_id = category_id(OTHER, "income")
    other_expense_id = category_id(OTHER, "expense")
    return Ctx(
        rules,
        own_numbers,
        merchant_defaults,
        internal_transfer_id,
        other_income_id,
        other_expense_id,
        category_id(BANK_FEES, "expense"),
    )


def apply(conn: Connection, txn_ids: list[int] | None = None) -> int:
    """Re-classify non-manual transactions; return the number of rows changed."""
    if txn_ids is not None and not txn_ids:
        return 0

    ctx = load_ctx(conn)
    sql = (
        "SELECT t.id, t.description, t.counterparty, t.amount, t.txn_type, t.merchant_id, "
        "m.name AS merchant, t.category_id, t.classified_by "
        "FROM transactions t LEFT JOIN merchants m ON m.id = t.merchant_id "
        "WHERE t.classified_by IS DISTINCT FROM 'manual'"
    )
    params: dict[str, Any] = {}
    if txn_ids is not None:
        sql += " AND t.id = ANY(:ids)"
        params["ids"] = list(txn_ids)

    updates = []
    for row in conn.execute(text(sql), params):
        txn = dict(row._mapping)
        category_id, classified_by = classify(txn, ctx)
        if (category_id, classified_by) != (txn["category_id"], txn["classified_by"]):
            updates.append(
                {"id": txn["id"], "category_id": category_id, "classified_by": classified_by}
            )

    if updates:
        conn.execute(
            text(
                "UPDATE transactions SET category_id = :category_id, "
                "classified_by = :classified_by WHERE id = :id"
            ),
            updates,
        )
    return len(updates)
