"""Idempotent seeding of banks, the category tree, own accounts and keyword rules."""

from sqlalchemy import Connection, Engine, text

from core import classifier
from core.classifier import BANK_FEES, INTERNAL_TRANSFER, OTHER, SAVINGS
from core.config import OWN_ACCOUNTS
from core.db import get_engine, init_db

SEED_BANKS: list[tuple[str, str]] = [
    ("khan", "Khan Bank"),
    ("xac", "Xac Bank"),
    ("golomt", "Golomt Bank"),
]

FOOD = "Хоол хүнс"
DINING = "Ресторан & Кафе"
EDUCATION = "Боловсрол"
BEAUTY = "Гоо сайхан & Арчилгаа"
TRANSPORT = "Тээврийн хэрэгсэл"
FIXED = "Тогтмол зардлууд"
SHOPPING = "Худалдан авалт"
TRANSFERS = "Шилжүүлэг & Хуримтлал"

# (main category, kind, subcategories). Transactions may sit on a main or a sub;
# budgets and reports roll subcategories up into their main category.
TAXONOMY: list[tuple[str, str, list[str]]] = [
    (FOOD, "expense", ["Супермаркет", "Хүнсний дэлгүүр"]),
    (DINING, "expense", ["Ресторан", "Кафе & Кофе шоп", "Түргэн хоол", "Паб & Баар"]),
    (EDUCATION, "expense", ["Сургалтын төлбөр", "Курс & Сургалт", "Ном & Хэрэгсэл"]),
    (BEAUTY, "expense", ["Гоо сайхны бүтээгдэхүүн", "Салон & Үйлчилгээ"]),
    (TRANSPORT, "expense", ["Нийтийн тээвэр", "Такси", "Шатахуун", "Зогсоол"]),
    (FIXED, "expense", ["Түрээс", "Интернет & ТВ", "Гар утас", BANK_FEES]),
    (SHOPPING, "expense", ["Хувцас", "Электроник", "Гэр ахуй"]),
    ("Эрүүл мэнд", "expense", []),
    ("Зугаа цэнгэл", "expense", []),
    ("Зээлийн төлбөр", "expense", []),
    (OTHER, "expense", []),
    (TRANSFERS, "transfer", [INTERNAL_TRANSFER, SAVINGS]),
    ("Өөрийн орлого", "income", []),
    ("Бэлэг", "income", []),
    ("Хандив", "income", []),
    (OTHER, "income", []),
]

# Earlier category names -> current (old name, old kind, new name, new kind). Applied in
# place (or merged when both exist) so transactions, rules and budgets keep their category.
CATEGORY_MOVES: list[tuple[str, str, str, str]] = [
    # first English defaults
    ("Self-earned", "income", "Өөрийн орлого", "income"),
    ("Gift", "income", "Бэлэг", "income"),
    ("Donation", "income", "Хандив", "income"),
    ("Other Income", "income", OTHER, "income"),
    ("Groceries", "expense", FOOD, "expense"),
    ("Restaurant", "expense", DINING, "expense"),
    ("Transportation", "expense", TRANSPORT, "expense"),
    ("Utilities", "expense", FIXED, "expense"),
    ("Housing", "expense", "Түрээс", "expense"),
    ("Bank Fees", "expense", BANK_FEES, "expense"),
    ("Personal Care & Grooming", "expense", BEAUTY, "expense"),
    ("Clothing & Apparel", "expense", "Хувцас", "expense"),
    ("Healthcare & Medical", "expense", "Эрүүл мэнд", "expense"),
    ("Entertainment & Recreation", "expense", "Зугаа цэнгэл", "expense"),
    ("Debt Payments", "expense", "Зээлийн төлбөр", "expense"),
    ("Savings & Investments", "expense", SAVINGS, "transfer"),
    ("Miscellaneous", "expense", OTHER, "expense"),
    ("Internal Transfer", "transfer", INTERNAL_TRANSFER, "transfer"),
    # then the flat Mongolian set (before main/subcategories)
    ("Ресторан, кафе", "expense", DINING, "expense"),
    ("Тээвэр / Улаанбаатар смарт карт", "expense", TRANSPORT, "expense"),
    ("Ашиглалт, холбоо", "expense", FIXED, "expense"),
    ("Үйлчилгээ / Шимтгэл", "expense", BANK_FEES, "expense"),
    ("Орон сууц", "expense", "Түрээс", "expense"),
    ("Хувийн арчилгаа", "expense", BEAUTY, "expense"),
    ("Хадгаламж, хөрөнгө оруулалт", "expense", SAVINGS, "transfer"),
]


def _rules(
    patterns: list[str],
    field: str,
    match: str,
    direction: str,
    category: str,
    priority: int,
) -> list[tuple[str, str, str, str, str, int]]:
    return [(p, field, match, direction, category, priority) for p in patterns]


# (pattern, field, match, direction, category name, priority). Lower priority runs first.
# Short words use whole-word regex: 'НОМ' is inside 'НОМИН', 'RENT' inside 'CURRENT'.
SEED_RULES: list[tuple[str, str, str, str, str, int]] = [
    # Bank fees (Тогтмол зардлууд)
    *_rules(["XACINFO", "Банк хоорондын шилжүүлгийн шимтгэл"], "description", "startswith", "out", BANK_FEES, 10),
    *_rules(["TRX:"], "description", "contains", "out", BANK_FEES, 10),
    # Loan, mortgage, credit-card and lease repayments contribute to DTI.
    *_rules(
        [
            "ЗЭЭЛИЙН ТӨЛБӨР",
            "ЗЭЭЛИЙН ЭРГЭН ТӨЛӨЛТ",
            "ЗЭЭЛИЙН ҮНДСЭН ТӨЛБӨР",
            "ЗЭЭЛИЙН ХҮҮ",
            "КРЕДИТИЙН ТӨЛБӨР",
            "ЛИЗИНГИЙН ТӨЛБӨР",
            "LOAN PAYMENT",
            "LOAN REPAYMENT",
            "MORTGAGE",
            "CREDIT PAYMENT",
            "CREDIT CARD PAYMENT",
            "CREDIT REPAYMENT",
            "LEASE PAYMENT",
            "LEASE",
        ],
        "description", "contains", "out", "Зээлийн төлбөр", 15,
    ),
    *_rules(
        [
            "ЗЭЭЛИЙН ТӨЛБӨР",
            "ЗЭЭЛИЙН ЭРГЭН ТӨЛӨЛТ",
            "ЗЭЭЛИЙН ҮНДСЭН ТӨЛБӨР",
            "ЗЭЭЛИЙН ХҮҮ",
            "КРЕДИТИЙН ТӨЛБӨР",
            "ЛИЗИНГИЙН ТӨЛБӨР",
            "LOAN PAYMENT",
            "LOAN REPAYMENT",
            "MORTGAGE",
            "CREDIT PAYMENT",
            "CREDIT CARD PAYMENT",
            "CREDIT REPAYMENT",
            "LEASE PAYMENT",
            "LEASE",
        ],
        "counterparty", "contains", "out", "Зээлийн төлбөр", 15,
    ),
    *_rules(
        [
            "LOAN PAYMENT",
            "LOAN REPAYMENT",
            "MORTGAGE",
            "CREDIT PAYMENT",
            "CREDIT CARD PAYMENT",
            "CREDIT REPAYMENT",
            "LEASE PAYMENT",
            "ЛИЗИНГ",
        ],
        "merchant", "contains", "out", "Зээлийн төлбөр", 15,
    ),
    # Specific names that would otherwise hit a broader rule
    *_rules(["SEZIS BUFFET"], "merchant", "contains", "out", "Ресторан", 20),
    *_rules(["NOMIN ELECTRONICS", "НОМИН ЭЛЕКТРОНИКС"], "merchant", "contains", "out", "Электроник", 20),
    # Savings and transport
    *_rules(["ХАДГАЛАМЖ", "ХУРИМТЛАЛ", "SAVINGS"], "description", "contains", "out", SAVINGS, 40),
    *_rules(["СМАРТ КАРТ"], "counterparty", "contains", "out", "Нийтийн тээвэр", 50),
    *_rules(["СМАРТ КАРТ", "SMART CARD", "U MONEY BUS"], "merchant", "contains", "out", "Нийтийн тээвэр", 50),
    *_rules(["TAXI", "ТАКСИ", "UBCAB"], "description", "contains", "out", "Такси", 50),
    *_rules(["TAXI", "ТАКСИ", "UBCAB"], "merchant", "contains", "out", "Такси", 50),
    *_rules(
        ["PETROVIS", "ПЕТРОВИС", "SHUNKHLAI", "ШУНХЛАЙ", "MAGNAI", "SOD MONGOL", "PETROL", "FUEL", "ШАТАХУУН", "ШТС"],
        "merchant", "contains", "out", "Шатахуун", 50,
    ),
    *_rules(["PARKING", "ЗОГСООЛ"], "merchant", "contains", "out", "Зогсоол", 50),
    *_rules(["ЗОГСООЛ"], "description", "contains", "out", "Зогсоол", 50),
    # Fixed costs
    *_rules(["ТҮРЭЭС"], "description", "contains", "out", "Түрээс", 50),
    *_rules([r"\bRENT\b"], "description", "regex", "out", "Түрээс", 50),
    *_rules(["OMSKYTEL", "UNITEL", "ЮНИТЕЛ", "MOBICOM", "МОБИКОМ", "SKYTEL", "СКАЙТЕЛ", "GMOBILE"],
            "merchant", "contains", "out", "Гар утас", 50),
    *_rules(["UNITEL", "MOBICOM", "SKYTEL", "GMOBILE"], "description", "contains", "out", "Гар утас", 50),
    *_rules(["UNIVISION", "ЮНИВИЖН", "SKYMEDIA", "DDISH", "ДДИШ", "VOO", "INTERNET", "ИНТЕРНЭТ"],
            "merchant", "contains", "out", "Интернет & ТВ", 50),
    # Education (tuition before the broader course words)
    *_rules(["MANDAKH", "МАНДАХ", "МУИС", "СЭЗИС", "ШУТИС", "UNIVERSITY", "ИХ СУРГУУЛЬ", "СУРГАЛТЫН ТӨЛБӨР"],
            "merchant", "contains", "out", "Сургалтын төлбөр", 55),
    *_rules(["МУИС", "СЭЗИС", "MANDAKH", "МАНДАХ", "СУРГАЛТЫН ТӨЛБӨР", "ХИЧЭЭЛИЙН ТӨЛБӨР"],
            "description", "contains", "out", "Сургалтын төлбөр", 55),
    *_rules([r"\b(NUM|UFE|MUST|SHUTIS)\b"], "merchant", "regex", "out", "Сургалтын төлбөр", 55),
    *_rules([r"\b(NUM|UFE|MUST|SHUTIS)\b"], "description", "regex", "out", "Сургалтын төлбөр", 55),
    *_rules(["COURSE", "КУРС", "ACADEMY", "АКАДЕМИ", "TRAINING", "СУРГАЛТ"], "merchant", "contains", "out", "Курс & Сургалт", 60),
    *_rules(["КУРС", "СУРГАЛТ", "COURSE"], "description", "contains", "out", "Курс & Сургалт", 60),
    *_rules(["BOOK", "INTERNOM", "ИНТЕРНОМ", "НОМЫН"], "merchant", "contains", "out", "Ном & Хэрэгсэл", 60),
    *_rules([r"\bНОМ\b"], "merchant", "regex", "out", "Ном & Хэрэгсэл", 60),
    # Beauty and personal care
    *_rules(["GLOWUP", "GLOW UP", "COSMETIC", "КОСМЕТИК", "BEAUTY", "ГОО САЙХАН"],
            "merchant", "contains", "out", "Гоо сайхны бүтээгдэхүүн", 60),
    *_rules(["GLOWUP", "GLOW UP"], "description", "contains", "out", "Гоо сайхны бүтээгдэхүүн", 60),
    *_rules(["SALON", "САЛОН", "NAIL", "BARBER", "ҮСЧИН", "ASSESSMENT", "ҮНЭЛГЭЭ"], "merchant", "contains", "out", "Салон & Үйлчилгээ", 60),
    *_rules([r"\bSPA\b"], "merchant", "regex", "out", "Салон & Үйлчилгээ", 60),
    # Shopping
    *_rules(["ELECTRONIC", "ЭЛЕКТРОНИК", "PC MALL", "SAMSUNG", "APPLE", "IPHONE", "COMPUTER", "КОМПЬЮТЕР"],
            "merchant", "contains", "out", "Электроник", 80),
    *_rules(["IKEA", "ГЭР АХУЙ", "HOUSEHOLD", "ТАВИЛГА", "FURNITURE", "HOME CENTER"], "merchant", "contains", "out", "Гэр ахуй", 80),
    *_rules(["AZOD ONLINE SHOP", "CLOTH", "ХУВЦАС", "FASHION", "SHOES", "ГУТАЛ", "ZARA", "H&M"],
            "merchant", "contains", "out", "Хувцас", 80),
    # Food: supermarkets before small shops ('SANSAR_EMART_KIOSK' is an E-Mart)
    *_rules(
        ["EMART", "CARREFOUR", "NOMINMACRO", "NOMIN BUSNESS CLUB", "SANSAR", "SUPERMARKET", "СУПЕРМАРКЕТ", "BARS ZAH", "БАРС"],
        "merchant", "contains", "out", "Супермаркет", 90,
    ),
    *_rules(["CU-", "GS25", "ALTJIN"], "merchant", "startswith", "out", "Хүнсний дэлгүүр", 100),
    *_rules(
        ["GS25", "MINII DELGUUR", "MINI MARKET", "FOOD CITY", "VILLA MARKET", "KHUNSNII", "ZAKH", "KIOSK", "КИОСК", "ХҮНСНИЙ"],
        "merchant", "contains", "out", "Хүнсний дэлгүүр", 100,
    ),
    *_rules(["NOMIN", "НОМИН"], "merchant", "contains", "out", "Супермаркет", 110),  # broad: last
    # Dining
    *_rules(["TSAINII GAZAR", "ЦАЙНЫ ГАЗАР", "RESTAURANT", "РЕСТОРАН", "BUFFET", "TUTS", "SEZS"],
            "merchant", "contains", "out", "Ресторан", 100),
    *_rules(["CAFE", "CAFFE", "COFFEE", "КОФЕ", "КАФЕ", "TOM N TOMS", "DESSERT", "БРЮ ХАУС", "BAKERY"],
            "merchant", "contains", "out", "Кафе & Кофе шоп", 100),
    *_rules(["KFC", "BURGER", "PIZZA", "MOMS TOUCH", "BUBU CHIKEN", "CHICKEN"], "merchant", "contains", "out", "Түргэн хоол", 100),
    *_rules(["ПАБ", "LOUNGE", "BEER", "ПИВО"], "merchant", "contains", "out", "Паб & Баар", 100),
    *_rules([r"\bPUB\b"], "merchant", "regex", "out", "Паб & Баар", 100),
    # Health and entertainment
    *_rules(["ZOLO DENT", "FARM", "PHARM", "ЭМИЙН САН", "HOSPITAL", "ЭМНЭЛЭГ", "DENT", "CLINIC", "КЛИНИК"],
            "merchant", "contains", "out", "Эрүүл мэнд", 100),
    *_rules(["GARAAR URLAKHUI", "CINEMA", "КИНО", "URGOO", "ӨРГӨӨ", "TICKET"], "merchant", "contains", "out", "Зугаа цэнгэл", 100),
    # Income
    *_rules(["EMEE"], "description", "exact", "in", "Бэлэг", 100),
]


def _seed_banks(connection: Connection) -> None:
    connection.execute(
        text(
            "INSERT INTO banks (code, name) VALUES (:code, :name) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        [{"code": code, "name": name} for code, name in SEED_BANKS],
    )


def _move_categories(connection: Connection) -> None:
    """Rename old categories in place, or merge them into the new one if it exists.

    Only active old categories are touched: an inactive one was merged before.
    """
    for old, old_kind, new, new_kind in CATEGORY_MOVES:
        old_id = connection.execute(
            text("SELECT id FROM categories WHERE name = :name AND kind = :kind AND is_active"),
            {"name": old, "kind": old_kind},
        ).scalar()
        if old_id is None:
            continue
        new_id = connection.execute(
            text("SELECT id FROM categories WHERE name = :name AND kind = :kind"),
            {"name": new, "kind": new_kind},
        ).scalar()
        if new_id is None:
            connection.execute(
                text("UPDATE categories SET name = :name, kind = :kind WHERE id = :id"),
                {"name": new, "kind": new_kind, "id": old_id},
            )
            continue
        params = {"old_id": old_id, "new_id": new_id}
        for table, column in (
            ("transactions", "category_id"),
            ("rules", "category_id"),
            ("merchants", "default_category_id"),
            ("recurring_items", "category_id"),
        ):
            connection.execute(
                text(f"UPDATE {table} SET {column} = :new_id WHERE {column} = :old_id"), params
            )
        # Keep a budget only where the target month has none yet.
        connection.execute(
            text(
                "UPDATE category_budgets b SET category_id = :new_id WHERE b.category_id = :old_id "
                "AND NOT EXISTS (SELECT 1 FROM category_budgets n "
                "WHERE n.category_id = :new_id AND n.budget_month = b.budget_month)"
            ),
            params,
        )
        connection.execute(text("DELETE FROM category_budgets WHERE category_id = :old_id"), params)
        connection.execute(
            text("UPDATE categories SET is_active = FALSE, parent_id = NULL WHERE id = :old_id"), params
        )


def _seed_categories(connection: Connection) -> None:
    """Create/activate every main and subcategory and set its parent."""
    upsert = text(
        "INSERT INTO categories (name, kind, is_default, is_active, parent_id) "
        "VALUES (:name, :kind, TRUE, TRUE, :parent_id) "
        "ON CONFLICT (name, kind) DO UPDATE SET parent_id = EXCLUDED.parent_id, is_active = TRUE "
        "RETURNING id"
    )
    for main, kind, subs in TAXONOMY:
        main_id = connection.execute(upsert, {"name": main, "kind": kind, "parent_id": None}).scalar_one()
        for sub in subs:
            connection.execute(upsert, {"name": sub, "kind": kind, "parent_id": main_id})


def _seed_own_accounts(connection: Connection) -> None:
    if not OWN_ACCOUNTS:
        return
    connection.execute(
        text(
            "INSERT INTO own_account_numbers (number) VALUES (:number) "
            "ON CONFLICT (number) DO NOTHING"
        ),
        [{"number": number} for number in OWN_ACCOUNTS],
    )


def _seed_rules(connection: Connection) -> None:
    """Insert seed rules, or point an existing identical rule at the current category."""
    kinds = {name: kind for main, kind, subs in TAXONOMY for name in (main, *subs)}
    for pattern, field, match, direction, category, priority in SEED_RULES:
        kind = "income" if direction == "in" else kinds.get(category, "expense")
        category_id = connection.execute(
            text("SELECT id FROM categories WHERE name = :name AND kind = :kind"),
            {"name": category, "kind": kind},
        ).scalar_one()
        params = {"field": field, "match": match, "pattern": pattern, "direction": direction,
                  "category_id": category_id, "priority": priority}
        updated = connection.execute(
            text(
                "UPDATE rules SET category_id = :category_id, priority = :priority "
                "WHERE field = :field AND match = :match AND pattern = :pattern AND direction = :direction"
            ),
            params,
        ).rowcount
        if not updated:
            connection.execute(
                text(
                    "INSERT INTO rules (field, match, pattern, direction, category_id, priority) "
                    "VALUES (:field, :match, :pattern, :direction, :category_id, :priority)"
                ),
                params,
            )


def seed(engine: Engine | None = None) -> None:
    """Insert defaults (idempotent), then re-run auto-classification."""
    target_engine = engine or get_engine()
    with target_engine.begin() as connection:
        _seed_banks(connection)
        _move_categories(connection)
        _seed_categories(connection)
        _seed_own_accounts(connection)
        _seed_rules(connection)
        classifier.apply(connection)


def main() -> None:
    engine = get_engine()
    init_db(engine)
    seed(engine)

    with engine.connect() as connection:
        counts = {
            table: connection.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()
            for table in ("banks", "categories", "rules", "own_account_numbers")
        }

    print(" ".join(f"{table}={count}" for table, count in counts.items()))


if __name__ == "__main__":
    main()
