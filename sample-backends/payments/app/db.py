import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS principals (id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, owner_id INTEGER,
  per_payment_limit INTEGER, secret TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, principal_id INTEGER NOT NULL, balance INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, from_account INTEGER NOT NULL, to_account INTEGER NOT NULL,
  amount INTEGER NOT NULL, idem_key TEXT NOT NULL, refunded INTEGER NOT NULL DEFAULT 0, UNIQUE (from_account, idem_key));
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ.get("APP_DB", "/tmp/payments.db"), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


db = connect()
