from unittest.mock import patch, MagicMock

import pytest

from msalt.news.cli import run_collect, run_briefing, run_search


@patch("msalt.news.cli.NewsCollector")
@patch("msalt.news.cli.Storage")
def test_run_collect(MockStorage, MockCollector):
    mock_storage = MockStorage.return_value
    mock_collector = MockCollector.return_value
    mock_collector.collect.return_value = 5

    result = run_collect()
    assert "5" in result
    mock_storage.initialize.assert_called_once()
    mock_collector.collect.assert_called_once()


@patch("msalt.news.cli.BriefingGenerator")
@patch("msalt.news.cli.Storage")
def test_run_briefing(MockStorage, MockGenerator):
    mock_gen = MockGenerator.return_value
    mock_gen.format_briefing.return_value = "아침 경제 브리핑 (2026-04-12)\n..."

    result = run_briefing("morning")
    assert "아침 경제 브리핑" in result


@patch("msalt.news.cli.Storage")
def test_run_search(MockStorage):
    mock_storage = MockStorage.return_value
    mock_storage.get_articles_since.return_value = [
        {"title": "삼성전자 실적", "url": "https://example.com/1", "summary": "s", "source": "한경", "category": "domestic", "collected_at": "2026-04-12"},
        {"title": "LG 실적", "url": "https://example.com/2", "summary": "s", "source": "매경", "category": "domestic", "collected_at": "2026-04-12"},
    ]
    mock_storage.initialize.return_value = None

    result = run_search("삼성전자")
    assert "삼성전자 실적" in result
