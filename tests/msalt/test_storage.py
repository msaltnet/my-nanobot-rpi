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


def test_initialize_creates_tables(db):
    conn = sqlite3.connect(db.db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    assert "news_articles" in tables
    assert "sleep_log" in tables
    assert "todos" in tables
    assert "life_log" in tables


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
