from unittest.mock import MagicMock

import pytest

from msalt.news.briefing import BriefingGenerator


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get_articles_since.return_value = [
        {"source": "한경", "title": "경제 성장률 상승", "url": "https://hk.com/1", "summary": "2분기 성장률 전망", "category": "domestic", "collected_at": "2026-04-12 07:00:00"},
        {"source": "Reuters", "title": "Fed holds rates", "url": "https://reuters.com/1", "summary": "Federal Reserve holds interest rates", "category": "international", "collected_at": "2026-04-12 07:00:00"},
    ]
    return storage


def test_format_briefing(mock_storage):
    gen = BriefingGenerator(storage=mock_storage)
    text = gen.format_briefing("morning")
    assert "아침 경제 브리핑" in text
    assert "국내" in text
    assert "해외" in text
    assert "경제 성장률 상승" in text
    assert "Fed holds rates" in text


def test_format_briefing_includes_reddit_section():
    from unittest.mock import MagicMock
    storage = MagicMock()
    storage.get_articles_since.return_value = [
        {"source": "한경", "title": "국내 이슈", "url": "https://hk.com/1", "summary": "요약", "category": "domestic", "collected_at": "2026-04-21 07:00:00"},
        {"source": "r/economics", "title": "Fed pivot", "url": "https://reddit.com/r/economics/1", "summary": "", "category": "reddit", "collected_at": "2026-04-21 07:00:00"},
    ]
    gen = BriefingGenerator(storage=storage)
    text = gen.format_briefing("morning")
    assert "[커뮤니티]" in text
    assert "r/economics" in text
    assert "Fed pivot" in text


def test_format_briefing_includes_policy_section():
    from unittest.mock import MagicMock
    storage = MagicMock()
    storage.get_articles_since.return_value = [
        {"source": "Fed Monetary Policy", "title": "FOMC statement", "url": "https://fed.gov/1", "summary": "Rate held at 4.25%", "category": "policy", "collected_at": "2026-04-23 07:00:00"},
    ]
    gen = BriefingGenerator(storage=storage)
    text = gen.format_briefing("morning")
    assert "[정책·지표]" in text
    assert "Fed Monetary Policy" in text
    assert "FOMC statement" in text


def test_format_briefing_empty(mock_storage):
    mock_storage.get_articles_since.return_value = []
    gen = BriefingGenerator(storage=mock_storage)
    text = gen.format_briefing("morning")
    assert "수집된 뉴스가 없습니다" in text


def test_get_articles_for_briefing_deduplicates(mock_storage):
    mock_storage.get_articles_since.return_value = [
        {"source": "한경", "title": "같은 기사", "url": "https://same.com", "summary": "a", "category": "domestic", "collected_at": "2026-04-12"},
        {"source": "매경", "title": "같은 기사", "url": "https://same.com", "summary": "b", "category": "domestic", "collected_at": "2026-04-12"},
    ]
    gen = BriefingGenerator(storage=mock_storage)
    articles = gen.get_articles_for_briefing()
    assert len(articles) == 1
