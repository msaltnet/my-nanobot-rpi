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


def test_insert_article_stores_published_at(db):
    db.insert_article(
        "src", "t", "https://e.com/1", "s", "domestic",
        published_at="2026-04-12 09:00:00",
    )
    articles = db.get_articles_since("2020-01-01")
    assert articles[0]["published_at"] == "2026-04-12 09:00:00"


def test_insert_article_published_at_optional(db):
    db.insert_article("src", "t", "https://e.com/1", "s", "domestic")
    articles = db.get_articles_since("2020-01-01")
    assert articles[0]["published_at"] is None


def test_get_articles_since_uses_published_at_when_present(db):
    """published_at이 있으면 그것을, 없으면 collected_at을 비교 대상으로 쓴다.

    아래는 RSS가 옛 기사를 새로 노출시킨 시나리오 — collected_at은 '지금'(SQLite
    datetime('now') = UTC) 이지만 published_at은 한참 전이라 윈도우에서 자연 컷된다.
    """
    db.insert_article(
        "src", "옛 기사", "https://old.com", "s", "domestic",
        published_at="2020-01-01 00:00:00",
    )
    db.insert_article(
        "src", "최근 기사", "https://new.com", "s", "domestic",
        published_at="2099-01-01 00:00:00",
    )
    # 2025년 이후만
    articles = db.get_articles_since("2025-01-01 00:00:00")
    titles = [a["title"] for a in articles]
    assert "최근 기사" in titles
    assert "옛 기사" not in titles


def test_get_articles_since_require_published_at_excludes_null(db):
    db.insert_article(
        "src", "발행일 있음", "https://a.com", "s", "domestic",
        published_at="2099-01-01 00:00:00",
    )
    db.insert_article("src", "발행일 미상", "https://b.com", "s", "domestic")
    articles = db.get_articles_since("2020-01-01", require_published_at=True)
    titles = [a["title"] for a in articles]
    assert "발행일 있음" in titles
    assert "발행일 미상" not in titles


def test_storage_initialize_migrates_existing_db_without_published_at(tmp_path):
    """이미 배포된 DB(컬럼 없음)에 initialize()가 ALTER로 컬럼을 추가한다."""
    db_path = tmp_path / "legacy.db"
    # 옛 스키마로 직접 생성 (published_at 없음)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE news_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            summary TEXT,
            category TEXT,
            collected_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "INSERT INTO news_articles (source, title, url, summary, category) "
        "VALUES (?, ?, ?, ?, ?)",
        ("src", "기존", "https://e.com/1", "s", "domestic"),
    )
    conn.commit()
    conn.close()

    storage = Storage(str(db_path))
    storage.initialize()  # ALTER 마이그레이션 실행

    cols = {row[1] for row in sqlite3.connect(db_path).execute(
        "PRAGMA table_info(news_articles)"
    )}
    assert "published_at" in cols
    # 기존 행 보존, 새 컬럼은 NULL
    articles = storage.get_articles_since("2020-01-01")
    assert len(articles) == 1
    assert articles[0]["title"] == "기존"
    assert articles[0]["published_at"] is None


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


def test_has_record_since_uses_recorded_at(storage):
    """recorded_at(시스템 기록 시각) 기준 since 이후 record가 있으면 True."""
    storage.insert_tracked_item("수면", "duration", None, "08:00")
    item = storage.get_tracked_item_by_name("수면")

    # 빈 상태
    assert storage.has_record_since(item["id"], "2099-01-01T00:00:00") is False

    # recorded_for가 어제여도 recorded_at이 지금이면 잡혀야 함 (오버나잇 시나리오)
    storage.upsert_record(item["id"], "2026-04-13", value_num=480,
                          raw_input="8h")
    assert storage.has_record_since(item["id"], "2020-01-01T00:00:00") is True

    # 미래 시점 since는 False
    assert storage.has_record_since(item["id"], "2099-01-01T00:00:00") is False
