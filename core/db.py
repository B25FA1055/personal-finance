"""Database engine management and schema initialization."""

from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, text

from core.config import DATABASE_URL

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


@lru_cache(maxsize=None)
def _create_engine(url: str) -> Engine:
    # Fail fast (instead of hanging) when PostgreSQL is not running.
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})


def get_engine(url: str | None = None) -> Engine:
    """Return the cached SQLAlchemy engine for the requested database URL."""
    return _create_engine(url or DATABASE_URL)


def init_db(engine: Engine | None = None) -> None:
    """Create all application tables and indexes if they do not exist."""
    target_engine = engine or get_engine()
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")

    with target_engine.begin() as connection:
        for statement in schema.split(";"):
            if statement.strip():
                connection.execute(text(statement))


def main() -> None:
    engine = get_engine()
    init_db(engine)

    with engine.connect() as connection:
        table_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
        ).scalar_one()

    print(f"DB OK {table_count}")


if __name__ == "__main__":
    main()
