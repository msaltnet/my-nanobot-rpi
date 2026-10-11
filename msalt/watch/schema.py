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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS watch_scan_cursors (
            watch_id INTEGER NOT NULL REFERENCES watch_conditions(id),
            revision INTEGER NOT NULL,
            last_article_id INTEGER NOT NULL,
            PRIMARY KEY (watch_id,revision)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watch_evaluation_runs (
            run_id TEXT PRIMARY KEY,
            max_articles INTEGER NOT NULL CHECK(max_articles BETWEEN 1 AND 100),
            max_calls INTEGER NOT NULL CHECK(max_calls BETWEEN 0 AND 10),
            retry_errors INTEGER NOT NULL CHECK(retry_errors IN (0,1)),
            articles_processed INTEGER NOT NULL DEFAULT 0,
            calls_reserved INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            CHECK(articles_processed BETWEEN 0 AND max_articles),
            CHECK(calls_reserved BETWEEN 0 AND max_calls)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watch_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_id INTEGER NOT NULL REFERENCES watch_conditions(id),
            revision INTEGER NOT NULL,
            article_id INTEGER NOT NULL REFERENCES news_articles(id),
            status TEXT NOT NULL CHECK(status IN ('pending','evaluating','relevant','irrelevant','error')),
            relevant INTEGER CHECK(relevant IN (0,1)),
            importance TEXT CHECK(importance IN ('low','medium','high')),
            reason TEXT,
            evidence TEXT,
            filter_rule TEXT,
            input_snapshot TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
            owner_token TEXT,
            lease_until REAL,
            error_code TEXT,
            last_run_id TEXT REFERENCES watch_evaluation_runs(run_id),
            stale_at_completion INTEGER NOT NULL DEFAULT 0 CHECK(stale_at_completion IN (0,1)),
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            completed_at REAL,
            UNIQUE(watch_id,revision,article_id)
        )
    """)
    conn.execute('CREATE INDEX IF NOT EXISTS idx_watch_evaluation_status ON watch_evaluations(status,article_id)')
