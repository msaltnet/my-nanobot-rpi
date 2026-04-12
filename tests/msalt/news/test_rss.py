from unittest.mock import patch, MagicMock

import pytest

from msalt.news.rss import RssCollector


MOCK_FEED = MagicMock()
MOCK_FEED.bozo = False
MOCK_FEED.entries = [
    MagicMock(
        title="경제 성장률 전망",
        link="https://example.com/article1",
        get=lambda key, default="": {
            "summary": "2분기 경제 성장률이 상승할 것으로 전망된다.",
            "published": "Sat, 12 Apr 2026 09:00:00 GMT",
        }.get(key, default),
    ),
    MagicMock(
        title="금리 동결 결정",
        link="https://example.com/article2",
        get=lambda key, default="": {
            "summary": "한국은행이 기준금리를 동결했다.",
            "published": "Sat, 12 Apr 2026 10:00:00 GMT",
        }.get(key, default),
    ),
]


@patch("msalt.news.rss.feedparser.parse", return_value=MOCK_FEED)
def test_collect_from_source(mock_parse):
    collector = RssCollector()
    source = {"name": "테스트", "url": "https://example.com/feed", "category": "domestic"}
    articles = collector.collect_from_source(source)
    assert len(articles) == 2
    assert articles[0]["title"] == "경제 성장률 전망"
    assert articles[0]["url"] == "https://example.com/article1"
    assert articles[0]["source"] == "테스트"
    assert articles[0]["category"] == "domestic"


@patch("msalt.news.rss.feedparser.parse")
def test_collect_from_source_handles_bozo(mock_parse):
    bad_feed = MagicMock()
    bad_feed.bozo = True
    bad_feed.entries = []
    mock_parse.return_value = bad_feed
    collector = RssCollector()
    source = {"name": "Bad", "url": "https://bad.com/feed", "category": "domestic"}
    articles = collector.collect_from_source(source)
    assert articles == []


def test_load_sources(tmp_path):
    import json

    sources_file = tmp_path / "sources.json"
    sources_file.write_text(json.dumps({
        "rss": [{"name": "Test", "url": "https://test.com/rss", "category": "domestic"}],
        "youtube": [],
    }))
    collector = RssCollector(sources_path=str(sources_file))
    sources = collector.load_sources()
    assert len(sources) == 1
    assert sources[0]["name"] == "Test"
