import time
from unittest.mock import patch, MagicMock

import httpx

from msalt.news.rss import RssCollector, _normalize_published


def _mock_response(body: bytes = b"<rss/>") -> MagicMock:
    resp = MagicMock()
    resp.content = body
    resp.raise_for_status = MagicMock()
    return resp


def _entry_obj(
    title: str,
    link: str,
    *,
    summary: str = "",
    published: str = "",
    published_parsed=None,
    updated_parsed=None,
) -> MagicMock:
    """feedparser entry 흉내. MagicMock 자동 속성으로 인한 truthy published_parsed
    오염을 막기 위해 명시 속성만 노출한다."""
    e = MagicMock(spec=["title", "link", "get", "published_parsed", "updated_parsed"])
    e.title = title
    e.link = link
    e.published_parsed = published_parsed
    e.updated_parsed = updated_parsed
    e.get = lambda key, default="": {"summary": summary, "published": published}.get(key, default)
    return e


MOCK_FEED = MagicMock()
MOCK_FEED.bozo = False
MOCK_FEED.entries = [
    _entry_obj(
        "경제 성장률 전망",
        "https://example.com/article1",
        summary="2분기 경제 성장률이 상승할 것으로 전망된다.",
        published="Sat, 12 Apr 2026 09:00:00 GMT",
        published_parsed=time.struct_time((2026, 4, 12, 9, 0, 0, 5, 102, 0)),
    ),
    _entry_obj(
        "금리 동결 결정",
        "https://example.com/article2",
        summary="한국은행이 기준금리를 동결했다.",
        published="Sat, 12 Apr 2026 10:00:00 GMT",
        published_parsed=time.struct_time((2026, 4, 12, 10, 0, 0, 5, 102, 0)),
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
    # published_parsed가 UTC ISO 문자열로 정규화되어 들어가야 한다
    assert articles[0]["published_at"] == "2026-04-12 09:00:00"
    assert articles[1]["published_at"] == "2026-04-12 10:00:00"


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
    return _entry_obj(title, link)


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


def test_normalize_published_uses_published_parsed():
    e = _entry_obj("t", "u", published_parsed=time.struct_time((2026, 4, 12, 9, 0, 0, 5, 102, 0)))
    assert _normalize_published(e) == "2026-04-12 09:00:00"


def test_normalize_published_falls_back_to_updated_parsed():
    e = _entry_obj("t", "u", updated_parsed=time.struct_time((2026, 4, 12, 9, 0, 0, 5, 102, 0)))
    assert _normalize_published(e) == "2026-04-12 09:00:00"


def test_normalize_published_returns_none_when_missing():
    e = _entry_obj("t", "u")  # 둘 다 None
    assert _normalize_published(e) is None


def test_normalize_published_drops_future_dates():
    """피드 타임존 오류로 미래 시각이 들어오면 신뢰 못 함 → None."""
    far_future = time.struct_time((2099, 1, 1, 0, 0, 0, 0, 1, 0))
    e = _entry_obj("t", "u", published_parsed=far_future)
    assert _normalize_published(e) is None
