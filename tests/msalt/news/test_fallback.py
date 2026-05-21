import json
from unittest.mock import MagicMock, patch

from msalt.news.fallback import FallbackCollector


def _sources_file(tmp_path, sources):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"fallback": sources}), encoding="utf-8")
    return str(path)


def _response(body: str):
    resp = MagicMock()
    resp.text = body
    resp.content = body.encode("utf-8")
    resp.raise_for_status = MagicMock()
    return resp


@patch("msalt.news.fallback.httpx.get")
def test_collect_from_html_extracts_matching_article_links(mock_get, tmp_path):
    mock_get.return_value = _response("""
        <a href="/article/1">첫 번째 경제 기사</a>
        <a href="/sports/1">스포츠 기사</a>
        <a href="/article/2"><span>두 번째 경제 기사</span></a>
    """)
    source = {
        "name": "경제 섹션",
        "url": "https://example.com/economy",
        "category": "domestic",
        "link_patterns": ["/article/"],
        "assume_current_if_missing": True,
    }

    articles = FallbackCollector().collect_from_html(source)

    assert [a["title"] for a in articles] == ["첫 번째 경제 기사", "두 번째 경제 기사"]
    assert articles[0]["url"] == "https://example.com/article/1"
    assert articles[0]["published_at"] is not None


@patch("msalt.news.fallback.httpx.get")
def test_collect_from_sitemap_uses_lastmod(mock_get, tmp_path):
    mock_get.return_value = _response("""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url>
            <loc>https://example.com/economy/rate-freeze</loc>
            <lastmod>2026-05-21T00:00:00Z</lastmod>
          </url>
          <url>
            <loc>https://example.com/sports/game</loc>
            <lastmod>2026-05-21T00:00:00Z</lastmod>
          </url>
        </urlset>
    """)
    source = {
        "name": "경제 사이트맵",
        "sitemap_url": "https://example.com/sitemap.xml",
        "category": "domestic",
        "link_patterns": ["/economy/"],
    }

    articles = FallbackCollector().collect_from_sitemap(source)

    assert len(articles) == 1
    assert articles[0]["title"] == "rate freeze"
    assert articles[0]["published_at"] == "2026-05-21 00:00:00"


@patch("msalt.news.fallback.httpx.get")
def test_collect_all_deduplicates_urls(mock_get, tmp_path):
    mock_get.return_value = _response("""
        <a href="/article/1">첫 번째 경제 기사</a>
        <a href="/article/1">첫 번째 경제 기사</a>
    """)
    sources_path = _sources_file(tmp_path, [{
        "name": "경제 섹션",
        "url": "https://example.com/economy",
        "link_patterns": ["/article/"],
    }])

    articles = FallbackCollector(sources_path=sources_path).collect_all()

    assert len(articles) == 1
