from unittest.mock import patch, MagicMock

import httpx

from msalt.news.rss import RssCollector


def _mock_response(body: bytes = b"<rss/>") -> MagicMock:
    resp = MagicMock()
    resp.content = body
    resp.raise_for_status = MagicMock()
    return resp


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


@patch("msalt.news.rss.httpx.get", return_value=_mock_response())
@patch("msalt.news.rss.feedparser.parse", return_value=MOCK_FEED)
def test_collect_from_source(mock_parse, mock_get):
    collector = RssCollector()
    source = {"name": "테스트", "url": "https://example.com/feed", "category": "domestic"}
    articles = collector.collect_from_source(source)
    assert len(articles) == 2
    assert articles[0]["title"] == "경제 성장률 전망"
    assert articles[0]["url"] == "https://example.com/article1"
    assert articles[0]["source"] == "테스트"
    assert articles[0]["category"] == "domestic"


@patch("msalt.news.rss.httpx.get", return_value=_mock_response())
@patch("msalt.news.rss.feedparser.parse")
def test_collect_from_source_handles_bozo(mock_parse, mock_get):
    bad_feed = MagicMock()
    bad_feed.bozo = True
    bad_feed.entries = []
    mock_parse.return_value = bad_feed
    collector = RssCollector()
    source = {"name": "Bad", "url": "https://bad.com/feed", "category": "domestic"}
    articles = collector.collect_from_source(source)
    assert articles == []


@patch("msalt.news.rss.httpx.get")
def test_collect_from_source_handles_http_error(mock_get):
    mock_get.side_effect = httpx.ConnectError("boom")
    collector = RssCollector()
    source = {"name": "Dead", "url": "https://dead.com/feed", "category": "domestic"}
    articles = collector.collect_from_source(source)
    assert articles == []


def _entry(title: str, link: str) -> MagicMock:
    e = MagicMock(
        title=title,
        link=link,
        get=lambda key, default="": {"summary": "", "published": ""}.get(key, default),
    )
    return e


@patch("msalt.news.rss.httpx.get", return_value=_mock_response())
@patch("msalt.news.rss.feedparser.parse")
def test_collect_from_source_applies_limit(mock_parse, mock_get):
    feed = MagicMock()
    feed.bozo = False
    feed.entries = [_entry(f"post {i}", f"https://r/{i}") for i in range(5)]
    mock_parse.return_value = feed
    collector = RssCollector()
    source = {"name": "r/test", "url": "https://r/feed", "category": "reddit", "limit": 2}
    articles = collector.collect_from_source(source)
    assert len(articles) == 2
    assert articles[0]["title"] == "post 0"
    assert articles[1]["title"] == "post 1"


@patch("msalt.news.rss.httpx.get", return_value=_mock_response())
@patch("msalt.news.rss.feedparser.parse")
def test_collect_from_source_skips_sticky_titles(mock_parse, mock_get):
    feed = MagicMock()
    feed.bozo = False
    feed.entries = [
        _entry("Daily Discussion Thread", "https://r/1"),
        _entry("Fed cuts rates", "https://r/2"),
        _entry("Weekly earnings megathread", "https://r/3"),
        _entry("Tesla earnings beat", "https://r/4"),
    ]
    mock_parse.return_value = feed
    collector = RssCollector()
    source = {
        "name": "r/test",
        "url": "https://r/feed",
        "category": "reddit",
        "skip_title_patterns": ["Daily", "Weekly", "Megathread"],
    }
    articles = collector.collect_from_source(source)
    titles = [a["title"] for a in articles]
    assert titles == ["Fed cuts rates", "Tesla earnings beat"]


def test_load_sources(tmp_path):
    import json

    sources_file = tmp_path / "sources.json"
    sources_file.write_text(json.dumps({
        "rss": [{"name": "Test", "url": "https://test.com/rss", "category": "domestic"}],
    }))
    collector = RssCollector(sources_path=str(sources_file))
    sources = collector.load_sources()
    assert len(sources) == 1
    assert sources[0]["name"] == "Test"
