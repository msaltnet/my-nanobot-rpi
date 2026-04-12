import sqlite3
from datetime import datetime, timezone


class Storage:
    """msalt-nanobot SQLite 저장소."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def initialize(self):
        """모든 테이블을 생성한다."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                summary TEXT,
                category TEXT,
                collected_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sleep_log (
                date TEXT PRIMARY KEY,
                bedtime TEXT,
                wakeup TEXT,
                duration_min INTEGER,
                quality TEXT
            );

            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                due_at TEXT,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS life_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                raw_text TEXT NOT NULL,
                category TEXT,
                parsed_data TEXT
            );
        """)
        conn.commit()
        conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def insert_article(self, source: str, title: str, url: str, summary: str, category: str):
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO news_articles (source, title, url, summary, category) "
                "VALUES (?, ?, ?, ?, ?)",
                (source, title, url, summary, category),
            )
            conn.commit()
        finally:
            conn.close()

    def get_articles_since(self, since_date: str) -> list[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM news_articles WHERE collected_at >= ? ORDER BY collected_at DESC",
                (since_date,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
