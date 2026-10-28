# FinTrack SPEC (Single Source of Truth)

## Goal
Local personal-finance tool for a single user on Windows. Periodic upload of Mongolian bank statements (Khan Bank, Xac Bank, etc.) -> PostgreSQL database -> Automatic & Manual POS merchant classification -> Budgeting & Financial Reports.

## Stack
- Python 3.12
- PostgreSQL 16
- SQLAlchemy 2 Core with text() SQL (No ORM classes)
- psycopg[binary] 3, pandas, openpyxl, Streamlit, python-dotenv, pytest

## Code Rules
- Type hints, pure functional helpers where possible. Money stored as Decimal / DB NUMERIC(14,2) (Never float).
- UTF-8 Mongolian Cyrillic support (Do not strip non-ASCII characters).
- DB Connection via core/db.py get_engine().

## Database Schema (core/schema.sql)
- banks: id, code UNIQUE, name
- accounts: id, bank_id, account_number, holder, currency, is_own
- own_account_numbers: number UNIQUE, label
- categories: id, name, kind ('income','expense','transfer'), is_default, is_active
- merchants: id, name UNIQUE, txn_type, default_category_id
- rules: id, field, match, pattern, direction, category_id, priority
- imports: id, account_id, file_name, file_sha256 UNIQUE, period_start, period_end, opening_balance, closing_balance, rows_read, rows_inserted, imported_at
- transactions: id, account_id, import_id, txn_date, description, counterparty, bank_ref, amount (+in, -out), balance, txn_type, merchant_id, category_id, classified_by, note
- category_budgets: category_id, budget_month, monthly_limit (one per expense category and month)
- savings_goals: name, target_amount, current_amount, deadline, is_active
- Budgets warn at 80% usage and show an exceeded alert when actual spending is over the limit.
- Dashboard DTI is current-month-to-date debt-category payments divided by classified positive income; transfers are excluded. The safety cap is 45%, with safe (<35%), moderate (35%-45%), and high-risk (>45%) statuses.
- Application features, including merchant categorization and the financial coach, run locally. No external AI API or API key is required; receipt details are entered manually.

## Classification Pipeline
1. Manual override (never overwritten automatically).
2. Internal transfer rule (Matching own_account_numbers).
3. Rule Engine matching priority.
4. Merchant default category.
5. Pending manual review on the 'Classify' page.