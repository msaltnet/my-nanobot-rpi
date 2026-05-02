import sqlite3

from msalt.storage import Storage


def test_initialize_adds_pending_since_column(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tracked_items)")}
    conn.close()
    assert "pending_since" in cols
    assert "last_asked_at" in cols


def test_initialize_is_idempotent_on_existing_db(tmp_path):
    """이미 last_missed_asked_date가 있는 옛 DB에서도 깨지지 않고 새 컬럼만 추가된다."""
    db = tmp_path / "test.db"
    # 옛 schema로 미리 만든다
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE tracked_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            schema TEXT NOT NULL,
            unit TEXT,
            schedule_time TEXT NOT NULL,
            frequency TEXT NOT NULL DEFAULT 'daily',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_missed_asked_date TEXT
        );
    """)
    conn.commit()
    conn.close()

    s = Storage(str(db))
    s.initialize()  # 두 번 호출해도 OK
    s.initialize()

    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tracked_items)")}
    conn.close()
    assert "pending_since" in cols
    assert "last_asked_at" in cols


def test_set_pending_since_persists(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    item_id = s.insert_tracked_item("수면", "duration", None, "22:00")
    s.set_pending_since(item_id, "2026-05-01 13:00:00")
    item = s.get_tracked_item_by_name("수면")
    assert item["pending_since"] == "2026-05-01 13:00:00"


def test_clear_pending_sets_null(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    item_id = s.insert_tracked_item("수면", "duration", None, "22:00")
    s.set_pending_since(item_id, "2026-05-01 13:00:00")
    s.clear_pending(item_id)
    item = s.get_tracked_item_by_name("수면")
    assert item["pending_since"] is None


def test_set_last_asked_at_persists(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    item_id = s.insert_tracked_item("수면", "duration", None, "22:00")
    s.set_last_asked_at(item_id, "2026-05-02 00:00:00")
    item = s.get_tracked_item_by_name("수면")
    assert item["last_asked_at"] == "2026-05-02 00:00:00"
