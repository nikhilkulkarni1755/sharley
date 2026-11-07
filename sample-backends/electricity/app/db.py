import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS houses (id TEXT PRIMARY KEY, owner TEXT NOT NULL, tariff_code TEXT NOT NULL, api_key TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS readings (id INTEGER PRIMARY KEY, house_id TEXT NOT NULL, month TEXT NOT NULL, kwh_total REAL NOT NULL,
  UNIQUE (house_id, month));
"""
# 12 houses. Three of them were typed in by hand with slightly different tariff codes ("res-b", "RES-B ", "RES_B").
HOUSES = [("H001", "RES-A"), ("H002", "RES-B"), ("H003", "res-b"), ("H004", "RES-A"), ("H005", "COM-A"), ("H006", "RES-B "),
          ("H007", "RES-A"), ("H008", "RES-B"), ("H009", "RES_B"), ("H010", "COM-A"), ("H011", "RES-A"), ("H012", "RES-B")]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ.get("APP_DB", "/tmp/electricity.db"), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM houses").fetchone()[0] == 0:
        for i, (hid, code) in enumerate(HOUSES, 1):
            conn.execute("INSERT INTO houses VALUES (?, ?, ?, ?)", (hid, f"owner-{hid}", code, f"key-{hid}"))
            conn.execute("INSERT INTO readings (house_id, month, kwh_total) VALUES (?, '2026-01', ?)", (hid, 1000.0 + 10 * i))
            conn.execute("INSERT INTO readings (house_id, month, kwh_total) VALUES (?, '2026-02', ?)", (hid, 1000.0 + 10 * i + 200 + 25 * i))
        conn.commit()
    return conn


db = connect()
