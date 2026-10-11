"""Additive Watch migration; Storage.initialize owns the transaction."""
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watch_conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            normalized_name TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL,
            keywords_json TEXT NOT NULL,
            excluded_keywords_json TEXT NOT NULL,
            active INTEGER NOT NULL CHECK(active IN (0, 1)),
            revision INTEGER NOT NULL CHECK(revision >= 1),
            start_article_id INTEGER NOT NULL CHECK(start_article_id >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT
        )
    """)
