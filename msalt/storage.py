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

    def upsert_sleep(self, date: str, bedtime: str, wakeup: str,
                     duration_min: int, quality: str | None = None):
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO sleep_log (date, bedtime, wakeup, duration_min, quality) "
                "VALUES (?, ?, ?, ?, ?)",
                (date, bedtime, wakeup, duration_min, quality),
            )
            conn.commit()
        finally:
            conn.close()

    def get_sleep_log(self, date: str) -> dict | None:
        conn = self._connect()
        try:
            cursor = conn.execute("SELECT * FROM sleep_log WHERE date = ?", (date,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_sleep_logs_since(self, since_date: str) -> list[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM sleep_log WHERE date >= ? ORDER BY date DESC",
                (since_date,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def insert_todo(self, content: str, due_at: str | None = None) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO todos (content, due_at, status) VALUES (?, ?, 'pending')",
                (content, due_at),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def complete_todo(self, todo_id: int):
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE todos SET status='done', completed_at=datetime('now') WHERE id=?",
                (todo_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def get_pending_todos(self) -> list[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM todos WHERE status='pending' ORDER BY due_at ASC NULLS LAST"
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_todos_due_before(self, before: str) -> list[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM todos WHERE status='pending' AND due_at IS NOT NULL AND due_at <= ? "
                "ORDER BY due_at ASC",
                (before,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def insert_life_log(self, raw_text: str, category: str, parsed_data: str) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO life_log (raw_text, category, parsed_data) VALUES (?, ?, ?)",
                (raw_text, category, parsed_data),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_life_logs_since(self, since_date: str) -> list[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM life_log WHERE timestamp >= ? ORDER BY timestamp DESC",
                (since_date,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_life_log_category_counts(self, since_date: str) -> dict[str, int]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM life_log "
                "WHERE timestamp >= ? GROUP BY category",
                (since_date,),
            )
            return {row["category"]: row["cnt"] for row in cursor.fetchall()}
        finally:
            conn.close()
