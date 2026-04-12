from unittest.mock import MagicMock, patch

import pytest

from msalt.news.collector import NewsCollector


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get_articles_since.return_value = []
    return storage


@patch("msalt.news.collector.RssCollector")
def test_collect_all_stores_articles(MockRss, mock_storage):
    mock_rss = MockRss.return_value
    mock_rss.collect_all.return_value = [
        {
            "source": "한경",
            "title": "테스트 기사",
            "url": "https://example.com/1",
            "summary": "요약",
            "category": "domestic",
            "published": "2026-04-12",
        }
    ]

    collector = NewsCollector(storage=mock_storage, sources_path="dummy.json")
    count = collector.collect()
    assert count == 1
    mock_storage.insert_article.assert_called_once_with(
        source="한경",
        title="테스트 기사",
        url="https://example.com/1",
        summary="요약",
        category="domestic",
    )


@patch("msalt.news.collector.RssCollector")
def test_collect_returns_count(MockRss, mock_storage):
    mock_rss = MockRss.return_value
    mock_rss.collect_all.return_value = [
        {"source": "a", "title": "t1", "url": "https://1.com", "summary": "s", "category": "domestic", "published": ""},
        {"source": "b", "title": "t2", "url": "https://2.com", "summary": "s", "category": "international", "published": ""},
    ]

    collector = NewsCollector(storage=mock_storage, sources_path="dummy.json")
    count = collector.collect()
    assert count == 2
