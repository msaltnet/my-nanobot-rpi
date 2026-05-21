import json
from unittest.mock import patch

from msalt.news.official import OfficialFeedCollector


@patch("msalt.news.official.RssCollector")
def test_official_collector_reads_official_sources(mock_rss_cls, tmp_path):
    sources_file = tmp_path / "sources.json"
    sources_file.write_text(json.dumps({
        "official_rss": [
            {
                "name": "한국은행",
                "url": "https://example.com/bok.rss",
                "category": "policy",
            }
        ]
    }), encoding="utf-8")
    mock_rss_cls.return_value.collect_from_source.return_value = [{
        "source": "한국은행",
        "title": "통화정책",
        "url": "https://example.com/1",
        "summary": "",
        "category": "policy",
        "published_at": "2026-05-21 00:00:00",
    }]

    articles = OfficialFeedCollector(sources_path=str(sources_file)).collect_all()

    assert len(articles) == 1
    mock_rss_cls.return_value.collect_from_source.assert_called_once()
