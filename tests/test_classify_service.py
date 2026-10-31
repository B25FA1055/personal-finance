import pytest
from sqlalchemy import create_engine, text

from core.classify_service import create_category, main_categories, set_transaction_categories


@pytest.fixture
def category_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "kind TEXT NOT NULL, is_default BOOLEAN, is_active BOOLEAN, "
                "parent_id INTEGER, UNIQUE (name, kind))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO categories (id, name, kind, is_default, is_active, parent_id) VALUES "
                "(1, 'Боловсрол', 'expense', TRUE, TRUE, NULL), "
                "(2, 'Сургалтын төлбөр', 'expense', TRUE, TRUE, 1), "
                "(3, 'Цалин', 'income', TRUE, TRUE, NULL), "
                "(4, 'Хуучин', 'expense', FALSE, FALSE, NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE transactions (id INTEGER PRIMARY KEY, category_id INTEGER, "
                "classified_by TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO transactions (id, category_id, classified_by) VALUES "
                "(1, 1, 'rule'), (2, 1, 'merchant')"
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()


def test_create_main_and_subcategory(category_db) -> None:
    with category_db.begin() as conn:
        main_id = create_category(conn, "  Гэрийн  тэжээвэр ", "expense")
        sub_id = create_category(conn, "Онлайн курс", "income", parent_id=1)  # kind follows the parent
        rows = {
            row.id: row
            for row in conn.execute(text("SELECT id, name, kind, is_default, parent_id FROM categories"))
        }
    assert rows[main_id].name == "Гэрийн тэжээвэр"
    assert (rows[main_id].kind, rows[main_id].parent_id, rows[main_id].is_default) == ("expense", None, 0)
    assert (rows[sub_id].kind, rows[sub_id].parent_id) == ("expense", 1)


def test_create_category_rejects_bad_input(category_db) -> None:
    with category_db.begin() as conn:
        for name, kind, parent_id, error in [
            ("   ", "expense", None, "cat_err_name"),
            ("x" * 61, "expense", None, "cat_err_name"),
            ("Боловсрол", "expense", None, "cat_err_exists"),
            ("Шинэ", "expense", 2, "cat_err_parent"),  # a subcategory cannot be a parent
            ("Шинэ", "loan", None, "cat_err_kind"),
        ]:
            with pytest.raises(ValueError, match=error):
                create_category(conn, name, kind, parent_id)


def test_archived_category_is_reactivated(category_db) -> None:
    with category_db.begin() as conn:
        assert create_category(conn, "Хуучин", "expense") == 4
        assert (4, "expense", "Хуучин") in main_categories(conn)


def test_manual_categories_persist_even_when_category_is_unchanged(category_db) -> None:
    with category_db.begin() as conn:
        assert set_transaction_categories(conn, {1: 2, 2: 1}) == 2
        rows = {
            row.id: (row.category_id, row.classified_by)
            for row in conn.execute(
                text("SELECT id, category_id, classified_by FROM transactions")
            )
        }

    assert rows == {1: (2, "manual"), 2: (1, "manual")}
