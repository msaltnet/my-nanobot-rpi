import sqlite3


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

            CREATE TABLE IF NOT EXISTS tracked_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                schema TEXT NOT NULL,
                unit TEXT,
                schedule_time TEXT NOT NULL,
                frequency TEXT NOT NULL DEFAULT 'daily',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL REFERENCES tracked_items(id) ON DELETE CASCADE,
                recorded_for TEXT NOT NULL,
                recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                value_text TEXT,
                value_num REAL,
                value_bool INTEGER,
                raw_input TEXT NOT NULL,
                UNIQUE(item_id, recorded_for)
            );

            CREATE INDEX IF NOT EXISTS idx_records_for ON records(recorded_for);
            CREATE INDEX IF NOT EXISTS idx_records_item ON records(item_id, recorded_for DESC);
        """)
        conn.commit()
        conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
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

    def insert_tracked_item(self, name: str, schema: str,
                            unit: str | None, schedule_time: str,
                            frequency: str = "daily") -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO tracked_items (name, schema, unit, schedule_time, frequency) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, schema, unit, schedule_time, frequency),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_tracked_item_by_name(self, name: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM tracked_items WHERE name = ?", (name,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_tracked_items(self) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM tracked_items ORDER BY name ASC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_tracked_item(self, name: str) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM tracked_items WHERE name = ?", (name,))
            conn.commit()
        finally:
            conn.close()

    def upsert_record(self, item_id: int, recorded_for: str,
                      value_text: str | None = None,
                      value_num: float | None = None,
                      value_bool: bool | None = None,
                      raw_input: str = "") -> None:
        conn = self._connect()
        try:
            bool_int = None if value_bool is None else int(bool(value_bool))
            conn.execute(
                "INSERT INTO records (item_id, recorded_for, value_text, value_num, "
                "value_bool, raw_input) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(item_id, recorded_for) DO UPDATE SET "
                "value_text=excluded.value_text, value_num=excluded.value_num, "
                "value_bool=excluded.value_bool, raw_input=excluded.raw_input, "
                "recorded_at=datetime('now')",
                (item_id, recorded_for, value_text, value_num, bool_int, raw_input),
            )
            conn.commit()
        finally:
            conn.close()

    def get_records_for_item(self, item_id: int, days: int,
                             ref_date: str) -> list[dict]:
        """ref_date 기준 최근 days일 기록 (recorded_for 내림차순)."""
        from datetime import date, timedelta
        ref = date.fromisoformat(ref_date)
        since = (ref - timedelta(days=days - 1)).isoformat()
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM records WHERE item_id = ? AND recorded_for >= ? "
                "ORDER BY recorded_for DESC",
                (item_id, since),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def record_exists(self, item_id: int, recorded_for: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM records WHERE item_id = ? AND recorded_for = ?",
                (item_id, recorded_for),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def has_record_since(self, item_id: int, since_iso: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM records WHERE item_id = ? AND recorded_at >= ?",
                (item_id, since_iso),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

