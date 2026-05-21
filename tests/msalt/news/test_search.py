import json
from unittest.mock import MagicMock, patch

from msalt.news.search import SearchCollector


def _sources_file(tmp_path, sources):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"search": sources}), encoding="utf-8")
    return str(path)


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


@patch("msalt.news.search.httpx.post")
def test_tavily_collects_news_results(mock_post, tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    mock_post.return_value = _response({
        "results": [
            {
                "title": "<b>금리 동결</b>",
                "url": "https://example.com/rate",
                "content": "요약",
                "published_date": "2026-05-21T00:00:00Z",
            }
        ]
    })
    sources_path = _sources_file(tmp_path, [{
        "name": "Tavily 국내",
        "provider": "tavily",
        "query": "금리",
        "category": "domestic",
        "days": 1,
    }])

    articles = SearchCollector(sources_path=sources_path).collect_all()

    assert articles == [{
        "source": "Tavily 국내",
        "title": "금리 동결",
        "url": "https://example.com/rate",
        "summary": "요약",
        "category": "domestic",
        "published_at": "2026-05-21 00:00:00",
    }]
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer tvly-test"


@patch("msalt.news.search.httpx.get")
def test_brave_collects_results_and_assumes_current_when_configured(
    mock_get,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("BRAVE_API_KEY", "brave-test")
    mock_get.return_value = _response({
        "web": {
            "results": [
                {
                    "title": "Fed minutes",
                    "url": "https://example.com/fed",
                    "description": "summary",
                }
            ]
        }
    })
    sources_path = _sources_file(tmp_path, [{
        "name": "Brave 글로벌",
        "provider": "brave",
        "query": "fed",
        "category": "international",
        "assume_current_if_missing": True,
    }])

    articles = SearchCollector(sources_path=sources_path).collect_all()

    assert articles[0]["title"] == "Fed minutes"
    assert articles[0]["published_at"] is not None
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["X-Subscription-Token"] == "brave-test"


@patch("msalt.news.search.httpx.get")
@patch("msalt.news.search.httpx.post")
def test_search_skips_missing_keys(mock_post, mock_get, tmp_path, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    sources_path = _sources_file(tmp_path, [
        {"name": "t", "provider": "tavily", "query": "q"},
        {"name": "b", "provider": "brave", "query": "q"},
    ])

    assert SearchCollector(sources_path=sources_path).collect_all() == []
    mock_post.assert_not_called()
    mock_get.assert_not_called()
