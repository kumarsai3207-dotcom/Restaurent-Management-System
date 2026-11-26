"""SQLite database connection management and relational schema definitions."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from backend.config import DEFAULT_DB_PATH

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('customer', 'kitchen', 'admin')),
    pin_code TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tables_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_number TEXT NOT NULL,
    session_code TEXT NOT NULL UNIQUE,
    order_mode TEXT NOT NULL CHECK(order_mode IN ('dine_in', 'takeaway')),
    pickup_slot TEXT,
    host_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'checked_out', 'closed')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES tables_sessions(id) ON DELETE CASCADE,
    participant_name TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    UNIQUE(session_id, participant_name)
);

CREATE TABLE IF NOT EXISTS menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    price_paise INTEGER NOT NULL CHECK(price_paise >= 0),
    is_veg INTEGER NOT NULL DEFAULT 1 CHECK(is_veg IN (0, 1)),
    is_jain INTEGER NOT NULL DEFAULT 0 CHECK(is_jain IN (0, 1)),
    is_vegan INTEGER NOT NULL DEFAULT 0 CHECK(is_vegan IN (0, 1)),
    spice_level TEXT NOT NULL DEFAULT 'Medium' CHECK(spice_level IN ('None', 'Mild', 'Medium', 'Hot', 'Extra Hot')),
    prep_time_mins INTEGER NOT NULL DEFAULT 15 CHECK(prep_time_mins > 0),
    in_stock INTEGER NOT NULL DEFAULT 1 CHECK(in_stock IN (0, 1)),
    stock_count INTEGER NOT NULL DEFAULT 40 CHECK(stock_count >= 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    image_emoji TEXT NOT NULL DEFAULT '🍽️',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS addons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL CHECK(category IN ('customisation', 'smart_addon')),
    price_paise INTEGER NOT NULL CHECK(price_paise >= 0),
    is_veg INTEGER NOT NULL DEFAULT 1 CHECK(is_veg IN (0, 1)),
    is_jain INTEGER NOT NULL DEFAULT 1 CHECK(is_jain IN (0, 1)),
    is_vegan INTEGER NOT NULL DEFAULT 0 CHECK(is_vegan IN (0, 1)),
    in_stock INTEGER NOT NULL DEFAULT 1 CHECK(in_stock IN (0, 1))
);

CREATE TABLE IF NOT EXISTS menu_item_addons (
    menu_item_id INTEGER NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    addon_id INTEGER NOT NULL REFERENCES addons(id) ON DELETE CASCADE,
    is_recommended INTEGER NOT NULL DEFAULT 0 CHECK(is_recommended IN (0, 1)),
    PRIMARY KEY (menu_item_id, addon_id)
);

CREATE TABLE IF NOT EXISTS cart_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES tables_sessions(id) ON DELETE CASCADE,
    menu_item_id INTEGER NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    added_by TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    spice_preference TEXT NOT NULL DEFAULT 'Regular',
    selected_addons_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT NOT NULL UNIQUE,
    session_id INTEGER REFERENCES tables_sessions(id) ON DELETE SET NULL,
    order_mode TEXT NOT NULL CHECK(order_mode IN ('dine_in', 'takeaway')),
    table_number TEXT,
    pickup_slot TEXT,
    customer_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Queued' CHECK(status IN ('Queued', 'Preparing', 'Ready', 'Served', 'Cancelled')),
    subtotal_paise INTEGER NOT NULL CHECK(subtotal_paise >= 0),
    cgst_paise INTEGER NOT NULL CHECK(cgst_paise >= 0),
    sgst_paise INTEGER NOT NULL CHECK(sgst_paise >= 0),
    packaging_fee_paise INTEGER NOT NULL DEFAULT 0 CHECK(packaging_fee_paise >= 0),
    total_paise INTEGER NOT NULL CHECK(total_paise >= 0),
    split_mode TEXT NOT NULL DEFAULT 'none' CHECK(split_mode IN ('none', 'equal', 'item_wise')),
    special_instructions TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    menu_item_id INTEGER REFERENCES menu_items(id) ON DELETE SET NULL,
    item_name TEXT NOT NULL,
    added_by TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price_paise INTEGER NOT NULL CHECK(unit_price_paise >= 0),
    addons_total_paise INTEGER NOT NULL DEFAULT 0 CHECK(addons_total_paise >= 0),
    selected_addons_json TEXT NOT NULL DEFAULT '[]',
    spice_preference TEXT NOT NULL DEFAULT 'Regular',
    notes TEXT NOT NULL DEFAULT '',
    line_total_paise INTEGER NOT NULL CHECK(line_total_paise >= 0)
);

CREATE TABLE IF NOT EXISTS split_shares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    participant_name TEXT NOT NULL,
    amount_paise INTEGER NOT NULL CHECK(amount_paise >= 0),
    assigned_items_json TEXT NOT NULL DEFAULT '[]',
    is_paid INTEGER NOT NULL DEFAULT 0 CHECK(is_paid IN (0, 1)),
    paid_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_menu_items_category ON menu_items(category);
CREATE INDEX IF NOT EXISTS idx_cart_items_session ON cart_items(session_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id);
CREATE INDEX IF NOT EXISTS idx_split_shares_order ON split_shares(order_id);
"""


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a configured SQLite connection with row factory and foreign keys enabled."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


@contextmanager
def db_session(db_path: Path | str = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    """Context manager that commits on success and rolls back on exception."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Create all tables and indexes if they do not already exist."""
    with db_session(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
