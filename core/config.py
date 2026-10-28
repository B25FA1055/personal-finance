"""Application configuration loaded from the project-root .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Resolved from this file's location, so it works from any working directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
_ENV_EXAMPLE_PATH = _PROJECT_ROOT / ".env.example"

# utf-8-sig: Notepad/PowerShell may save .env with a BOM, which would
# otherwise corrupt the first key ('﻿DATABASE_URL').
load_dotenv(dotenv_path=_ENV_PATH, encoding="utf-8-sig")


def _env(name: str) -> str | None:
    value = os.getenv(name, "").strip().strip('"').strip("'")
    return value or None


_database_url = _env("DATABASE_URL")
if not _database_url:
    if not _ENV_PATH.is_file():
        reason = (
            f".env file not found at {_ENV_PATH}.\n"
            f"Create it with:  Copy-Item \"{_ENV_EXAMPLE_PATH}\" \"{_ENV_PATH}\"\n"
            "then replace CHANGE_ME with your PostgreSQL password."
        )
    else:
        reason = (
            f"DATABASE_URL is missing or empty in {_ENV_PATH}.\n"
            "Add a line like:\n"
            "DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/fintrack"
        )
    raise RuntimeError(f"DATABASE_URL is not set. {reason}")

DATABASE_URL: str = _database_url
TEST_DATABASE_URL: str | None = _env("TEST_DATABASE_URL")

OWN_ACCOUNTS: list[str] = [
    account.strip()
    for account in (_env("OWN_ACCOUNTS") or "").split(",")
    if account.strip()
]
