"""Additive tracking delivery schema; caller owns the migration transaction."""
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tracking_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES tracked_items(id) ON DELETE CASCADE,
            recorded_for TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('scheduled', 'retry')),
            slot_utc TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('claimed', 'sent', 'rejected', 'unknown')),
            claimed_at TEXT NOT NULL,
            completed_at TEXT,
            resolved_at TEXT,
            UNIQUE(item_id, recorded_for, kind, slot_utc)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracking_delivery_unresolved
        ON tracking_deliveries(item_id, recorded_for, state, resolved_at)
    """)
