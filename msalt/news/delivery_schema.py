"""Additive schema for the news delivery ledger; no legacy rows are reclassified."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS news_deliveries (
 delivery_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL DEFAULT 1,
 target TEXT NOT NULL, thread TEXT NOT NULL DEFAULT '', kst_date TEXT NOT NULL,
 slot TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
 state TEXT NOT NULL, snapshot_urls TEXT, snapshot_hash TEXT, payload TEXT, payload_hash TEXT, owner TEXT, lease_until REAL,
 error TEXT, generation INTEGER NOT NULL DEFAULT 1, generation_started REAL NOT NULL,
 is_empty INTEGER NOT NULL DEFAULT 0, send_started REAL, manual INTEGER NOT NULL DEFAULT 0,
 UNIQUE(target, thread, kst_date, slot)
);
CREATE TABLE IF NOT EXISTS news_delivery_articles (
 delivery_id TEXT NOT NULL REFERENCES news_deliveries(delivery_id),
 article_url TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(delivery_id, article_url)
);
CREATE UNIQUE INDEX IF NOT EXISTS news_delivery_active_url
 ON news_delivery_articles(article_url) WHERE active = 1;
CREATE TABLE IF NOT EXISTS news_delivery_parts (
 delivery_id TEXT NOT NULL REFERENCES news_deliveries(delivery_id), part_no INTEGER NOT NULL,
 text TEXT NOT NULL, hash TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0, message_id INTEGER, ack_at REAL,
 PRIMARY KEY(delivery_id, part_no)
);
CREATE TABLE IF NOT EXISTS news_delivery_attempts (
 attempt_id TEXT PRIMARY KEY, delivery_id TEXT NOT NULL REFERENCES news_deliveries(delivery_id),
 part_no INTEGER, created_at REAL NOT NULL, updated_at REAL NOT NULL,
 owner TEXT, outcome TEXT NOT NULL, error TEXT, manual INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS news_delivery_budget (
 name TEXT PRIMARY KEY, used INTEGER NOT NULL CHECK(used >= 0)
);
"""


def migrate(conn):
    """Called inside Storage.initialize's transaction; never executescript/commit."""
    validate(conn, partial=True)
    for statement in SCHEMA.split(";"):
        if statement.strip():
            conn.execute(statement)


def validate(conn, *, partial=False):
    """Reject incompatible prior/partial ledger schemas before mutation."""
    import re
    import sqlite3

    def normalized(sql):
        return re.sub(r"\s+", "", (sql or "").lower())

    with sqlite3.connect(":memory:") as reference:
        reference.executescript(SCHEMA)
        for name, kind, table, sql in reference.execute(
            "SELECT name,type,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ):
            actual = conn.execute(
                "SELECT type,tbl_name,sql FROM sqlite_master WHERE name=?", (name,)
            ).fetchone()
            parent_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name=?", (table,)
            ).fetchone()
            if actual is None and partial and parent_exists is None:
                continue
            if actual is None or (actual[0], actual[1], normalized(actual[2])) != (
                kind,
                table,
                normalized(sql),
            ):
                raise ValueError("incompatible delivery schema constraints")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='news_deliveries'").fetchone():
        if conn.execute(
            "SELECT 1 FROM news_deliveries WHERE schema_version != 1 LIMIT 1"
        ).fetchone():
            raise ValueError("unsupported delivery schema version")
