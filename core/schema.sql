CREATE TABLE IF NOT EXISTS banks (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id BIGSERIAL PRIMARY KEY,
    bank_id BIGINT NOT NULL REFERENCES banks (id) ON DELETE RESTRICT,
    account_number TEXT NOT NULL,
    holder TEXT,
    currency TEXT NOT NULL DEFAULT 'MNT',
    is_own BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (bank_id, account_number)
);

CREATE TABLE IF NOT EXISTS own_account_numbers (
    number TEXT PRIMARY KEY,
    label TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense', 'transfer')),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (name, kind)
);

CREATE TABLE IF NOT EXISTS merchants (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    txn_type TEXT,
    default_category_id BIGINT REFERENCES categories (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS rules (
    id BIGSERIAL PRIMARY KEY,
    field TEXT NOT NULL CHECK (field IN ('merchant', 'description', 'counterparty')),
    match TEXT NOT NULL CHECK (match IN ('exact', 'contains', 'startswith', 'regex')),
    pattern TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('in', 'out', 'any')),
    category_id BIGINT NOT NULL REFERENCES categories (id) ON DELETE RESTRICT,
    priority INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS imports (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts (id) ON DELETE RESTRICT,
    file_name TEXT NOT NULL,
    file_sha256 TEXT NOT NULL UNIQUE,
    period_start DATE,
    period_end DATE,
    opening_balance NUMERIC(14, 2),
    closing_balance NUMERIC(14, 2),
    rows_read INTEGER NOT NULL DEFAULT 0,
    rows_inserted INTEGER NOT NULL DEFAULT 0,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts (id) ON DELETE RESTRICT,
    import_id BIGINT REFERENCES imports (id) ON DELETE SET NULL,
    txn_date TIMESTAMPTZ NOT NULL,
    description TEXT NOT NULL,
    counterparty TEXT,
    bank_ref TEXT,
    amount NUMERIC(14, 2) NOT NULL,
    balance NUMERIC(14, 2),
    txn_type TEXT,
    merchant_id BIGINT REFERENCES merchants (id) ON DELETE SET NULL,
    category_id BIGINT REFERENCES categories (id) ON DELETE SET NULL,
    classified_by TEXT CHECK (classified_by IN ('rule', 'merchant', 'manual')),
    note TEXT,
    UNIQUE (account_id, bank_ref)
);

CREATE INDEX IF NOT EXISTS idx_transactions_txn_date
    ON transactions (txn_date);

CREATE INDEX IF NOT EXISTS idx_transactions_category_id
    ON transactions (category_id);

CREATE INDEX IF NOT EXISTS idx_transactions_merchant_id
    ON transactions (merchant_id);

CREATE TABLE IF NOT EXISTS category_budgets (
    id BIGSERIAL PRIMARY KEY,
    category_id BIGINT NOT NULL REFERENCES categories (id) ON DELETE CASCADE,
    budget_month DATE NOT NULL,
    monthly_limit NUMERIC(14, 2) NOT NULL CHECK (monthly_limit > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (category_id, budget_month)
);

CREATE INDEX IF NOT EXISTS idx_category_budgets_month
    ON category_budgets (budget_month);

CREATE TABLE IF NOT EXISTS savings_goals (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    target_amount NUMERIC(14, 2) NOT NULL CHECK (target_amount > 0),
    current_amount NUMERIC(14, 2) NOT NULL DEFAULT 0 CHECK (current_amount >= 0),
    deadline DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Subscriptions and fixed bills. start_date anchors the schedule (Jan 31 -> Feb 28 -> Mar 31).
CREATE TABLE IF NOT EXISTS recurring_items (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    direction TEXT NOT NULL DEFAULT 'out' CHECK (direction IN ('in', 'out')),
    frequency TEXT NOT NULL CHECK (frequency IN ('weekly', 'monthly', 'yearly')),
    start_date DATE NOT NULL,
    next_due DATE NOT NULL,
    category_id BIGINT REFERENCES categories (id) ON DELETE SET NULL,
    match_pattern TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One row per due date: how it was settled. UNIQUE stops double logging.
CREATE TABLE IF NOT EXISTS recurring_occurrences (
    id BIGSERIAL PRIMARY KEY,
    item_id BIGINT NOT NULL REFERENCES recurring_items (id) ON DELETE CASCADE,
    due_date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('matched', 'confirmed', 'logged', 'skipped')),
    transaction_id BIGINT REFERENCES transactions (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (item_id, due_date)
);

-- Category hierarchy: a subcategory points to its main category (NULL = main).
ALTER TABLE categories ADD COLUMN IF NOT EXISTS parent_id BIGINT REFERENCES categories (id) ON DELETE SET NULL;

-- Goal kind (emergency, education, purchase, travel, other) for icons and grouping.
ALTER TABLE savings_goals ADD COLUMN IF NOT EXISTS goal_type TEXT NOT NULL DEFAULT 'other';

-- Savings transactions assigned to a goal. One transaction funds at most one goal.
CREATE TABLE IF NOT EXISTS goal_contributions (
    id BIGSERIAL PRIMARY KEY,
    goal_id BIGINT NOT NULL REFERENCES savings_goals (id) ON DELETE CASCADE,
    transaction_id BIGINT NOT NULL UNIQUE REFERENCES transactions (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
