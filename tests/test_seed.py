from decimal import Decimal

from sqlalchemy import create_engine, text

from core.classifier import classify, load_ctx
from core.seed import seed


def test_seeded_rules_and_other_defaults_classify_transactions() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE banks (id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "kind TEXT NOT NULL, is_default BOOLEAN, is_active BOOLEAN, "
                "parent_id INTEGER, UNIQUE (name, kind))"
            )
        )
        connection.execute(
            text("CREATE TABLE own_account_numbers (number TEXT PRIMARY KEY, label TEXT)")
        )
        connection.execute(
            text(
                "CREATE TABLE rules (id INTEGER PRIMARY KEY, field TEXT, match TEXT, "
                "pattern TEXT, direction TEXT, category_id INTEGER, priority INTEGER)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE merchants (id INTEGER PRIMARY KEY, name TEXT UNIQUE, "
                "txn_type TEXT, default_category_id INTEGER)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE transactions (id INTEGER PRIMARY KEY, description TEXT, "
                "counterparty TEXT, amount NUMERIC, txn_type TEXT, merchant_id INTEGER, "
                "category_id INTEGER, classified_by TEXT)"
            )
        )

    seed(engine)
    with engine.connect() as connection:
        ctx = load_ctx(connection)
        categories = {
            (row.name, row.kind): row.id
            for row in connection.execute(
                text("SELECT id, name, kind FROM categories")
            )
        }
    assert ctx.internal_transfer_id == categories[("Дотоод шилжүүлэг", "transfer")]

    cases = [
        (
            {
                "description": "XACINFO ҮЙЛЧИЛГЭЭНИЙ ШИМТГЭЛ",
                "counterparty": "",
                "amount": Decimal("-50"),
                "txn_type": "fee",
                "merchant_id": None,
            },
            ("Банкны шимтгэл", "expense"),
        ),
        (
            {
                "description": "POS PURCHASE",
                "counterparty": "",
                "merchant": "CU-334 LENIN CLUB",
                "amount": Decimal("-500"),
                "txn_type": "pos",
                "merchant_id": None,
            },
            ("Хүнсний дэлгүүр", "expense"),
        ),
        (
            {
                "description": "qpay 123",
                "counterparty": "УЛААНБААТАР СМАРТ КАРТ",
                "merchant": "УЛААНБААТАР СМАРТ КАРТ",
                "amount": Decimal("-1000"),
                "txn_type": "qpay",
                "merchant_id": None,
            },
            ("Нийтийн тээвэр", "expense"),
        ),
        (
            {
                "description": "UNRECOGNIZED EXPENSE",
                "counterparty": "",
                "amount": Decimal("-100"),
                "txn_type": "other",
                "merchant_id": None,
            },
            ("Бусад", "expense"),
        ),
        (
            {
                "description": "UNRECOGNIZED INCOME",
                "counterparty": "",
                "amount": Decimal("100"),
                "txn_type": "transfer",
                "merchant_id": None,
            },
            ("Бусад", "income"),
        ),
    ]

    for transaction, (category_name, kind) in cases:
        category_id, _ = classify(transaction, ctx)
        assert category_id == categories[(category_name, kind)]
