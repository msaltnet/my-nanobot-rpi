import sqlite3
from pathlib import Path

import pytest

from msalt.storage import Storage


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    storage = Storage(str(db_path))
    storage.initialize()
    return storage


def test_initialize_creates_news_articles_table(db):
    conn = sqlite3.connect(db.db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    assert "news_articles" in tables


def test_insert_and_get_article(db):
    db.insert_article(
        source="hankyung",
        title="테스트 기사",
        url="https://example.com/1",
        summary="요약 내용",
        category="domestic",
    )
    articles = db.get_articles_since("2020-01-01")
    assert len(articles) == 1
    assert articles[0]["title"] == "테스트 기사"
    assert articles[0]["source"] == "hankyung"


def test_duplicate_url_ignored(db):
    db.insert_article("src", "제목1", "https://example.com/1", "요약1", "domestic")
    db.insert_article("src", "제목2", "https://example.com/1", "요약2", "domestic")
    articles = db.get_articles_since("2020-01-01")
    assert len(articles) == 1


def test_get_articles_since_filters_by_date(db):
    db.insert_article("src", "오래된", "https://old.com", "old", "domestic")
    articles = db.get_articles_since("2099-01-01")
    assert len(articles) == 0


def test_storage_does_not_expose_lifestyle_methods():
    from msalt.storage import Storage
    legacy = ["upsert_sleep", "get_sleep_log", "get_sleep_logs_since",
              "insert_todo", "complete_todo", "get_pending_todos",
              "get_todos_due_before", "insert_life_log",
              "get_life_logs_since", "get_life_log_category_counts"]
    for name in legacy:
        assert not hasattr(Storage, name), f"{name} should be removed"


@pytest.fixture
def storage(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    return s


def test_initialize_creates_tracking_tables(storage):
    conn = sqlite3.connect(storage.db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    conn.close()
    names = {r[0] for r in rows}
    assert "tracked_items" in names
    assert "records" in names


def test_insert_and_get_tracked_item(storage):
    storage.insert_tracked_item("수면", "duration", None, "08:00")
    item = storage.get_tracked_item_by_name("수면")
    assert item["name"] == "수면"
    assert item["schema"] == "duration"
    assert item["unit"] is None
    assert item["schedule_time"] == "08:00"
    assert item["frequency"] == "daily"


def test_insert_tracked_item_unique_name(storage):
    storage.insert_tracked_item("수면", "duration", None, "08:00")
    with pytest.raises(sqlite3.IntegrityError):
        storage.insert_tracked_item("수면", "duration", None, "09:00")


def test_list_tracked_items(storage):
    storage.insert_tracked_item("a", "boolean", None, "10:00")
    storage.insert_tracked_item("b", "quantity", "잔", "22:00")
    items = storage.list_tracked_items()
    assert [i["name"] for i in items] == ["a", "b"]


def test_delete_tracked_item_cascades_records(storage):
    storage.insert_tracked_item("음주", "quantity", "잔", "22:00")
    item = storage.get_tracked_item_by_name("음주")
    storage.upsert_record(item["id"], "2026-04-13", value_num=2.0,
                          raw_input="2잔")
    storage.delete_tracked_item("음주")
    assert storage.get_tracked_item_by_name("음주") is None
    conn = sqlite3.connect(storage.db_path)
    cnt = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    conn.close()
    assert cnt == 0


def test_upsert_record_replaces_same_date(storage):
    storage.insert_tracked_item("수면", "duration", None, "08:00")
    item = storage.get_tracked_item_by_name("수면")
    storage.upsert_record(item["id"], "2026-04-13", value_num=420,
                          raw_input="7시간")
    storage.upsert_record(item["id"], "2026-04-13", value_num=480,
                          raw_input="8시간")
    recs = storage.get_records_for_item(item["id"], days=7,
                                        ref_date="2026-04-14")
    assert len(recs) == 1
    assert recs[0]["value_num"] == 480
    assert recs[0]["raw_input"] == "8시간"


def test_get_records_for_item_filters_by_days(storage):
    storage.insert_tracked_item("수면", "duration", None, "08:00")
    item = storage.get_tracked_item_by_name("수면")
    storage.upsert_record(item["id"], "2026-04-01", value_num=400,
                          raw_input="x")
    storage.upsert_record(item["id"], "2026-04-13", value_num=480,
                          raw_input="y")
    recs = storage.get_records_for_item(item["id"], days=7,
                                        ref_date="2026-04-14")
    assert [r["recorded_for"] for r in recs] == ["2026-04-13"]


def test_record_exists_for_date(storage):
    storage.insert_tracked_item("수면", "duration", None, "08:00")
    item = storage.get_tracked_item_by_name("수면")
    assert storage.record_exists(item["id"], "2026-04-13") is False
    storage.upsert_record(item["id"], "2026-04-13", value_num=480,
                          raw_input="8h")
    assert storage.record_exists(item["id"], "2026-04-13") is True
