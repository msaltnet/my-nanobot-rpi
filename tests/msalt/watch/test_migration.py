import sqlite3

import pytest

from msalt.storage import Storage
from msalt.watch.store import WatchStore


def test_repeated_upgrade_preserves_all_existing_rows(tmp_path):
    storage = Storage(str(tmp_path / "old.db"))
    storage.initialize()
    storage.insert_article("fixture", "news", "https://fixture/news", "summary", "fixture")
    item_id = storage.insert_tracked_item("fixture", "quantity", "units", "09:00")
    with storage._connect() as conn:
        conn.execute("DROP TABLE watch_conditions")
        conn.execute("INSERT INTO news_briefed_articles VALUES ('https://fixture/news', 'morning', '2026-10-10')")
        conn.execute("INSERT INTO records(item_id, recorded_for, value_num, raw_input) VALUES (?, '2026-10-09', 3, 'fixture')", (item_id,))
        conn.execute("INSERT INTO tracking_deliveries(item_id, recorded_for, kind, slot_utc, state, claimed_at) VALUES (?, '2026-10-10', 'scheduled', '2026-10-10T00:00:00Z', 'unknown', '2026-10-10T00:00:00Z')", (item_id,))
        conn.execute("CREATE TABLE local_settings(name TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO local_settings VALUES ('disabled', 'true')")
        for identifier, state in [('ack', 'sent'), ('uncertain', 'unknown')]:
            conn.execute("INSERT INTO news_deliveries(delivery_id, target, kst_date, slot, created_at, updated_at, state, generation_started) VALUES (?, 'fixture', '2026-10-10', ?, 1, 1, ?, 1)", (identifier, identifier, state))
            conn.execute("INSERT INTO news_delivery_parts(delivery_id, part_no, text, hash, state, attempts, message_id, ack_at) VALUES (?, 0, 'fixture', 'hash', ?, 1, ?, ?)", (identifier, state, 123 if state == 'sent' else None, 1 if state == 'sent' else None))
            conn.execute("INSERT INTO news_delivery_articles VALUES (?, ?, 1)", (identifier, 'https://fixture/' + identifier))
            conn.execute("INSERT INTO news_delivery_attempts(attempt_id, delivery_id, created_at, updated_at, outcome) VALUES (?, ?, 1, 1, ?)", (identifier, identifier, state))
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before = {table: list(conn.execute('SELECT * FROM ' + table)) for table in tables}
    storage.initialize()
    store = WatchStore(storage)
    condition = store.add("fixture", description="description", keywords=[], excluded_keywords=[])
    store.delete(condition.id, expected_revision=1)
    storage.initialize()
    storage.initialize()
    with storage._connect() as conn:
        after = {table: list(conn.execute('SELECT * FROM ' + table)) for table in tables}
        assert before == after
        assert conn.execute("SELECT COUNT(*) FROM watch_conditions WHERE deleted_at IS NOT NULL").fetchone()[0] == 1


def test_failed_migration_rolls_back_watch_and_other_new_tables(tmp_path, monkeypatch):
    storage = Storage(str(tmp_path / "empty.db"))
    from msalt.watch import schema
    migrate = schema.migrate
    def fail(conn):
        migrate(conn)
        raise RuntimeError("synthetic migration failure")
    monkeypatch.setattr(schema, "migrate", fail)
    with pytest.raises(RuntimeError):
        storage.initialize()
    with sqlite3.connect(storage.db_path) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


def test_soft_delete_retains_foreign_key_history(tmp_path):
    storage = Storage(str(tmp_path / "history.db"))
    storage.initialize()
    store = WatchStore(storage)
    item = store.add("history", description="fixture", keywords=[], excluded_keywords=[])
    with storage._connect() as conn:
        conn.execute("CREATE TABLE fixture_history(watch_id INTEGER REFERENCES watch_conditions(id), result TEXT)")
        conn.execute("INSERT INTO fixture_history VALUES (?, 'retained')", (item.id,))
    store.delete(item.id, expected_revision=1)
    storage.initialize()
    with storage._connect() as conn:
        assert tuple(conn.execute("SELECT * FROM fixture_history").fetchone()) == (item.id, 'retained')
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
