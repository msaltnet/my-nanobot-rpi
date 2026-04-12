from unittest.mock import MagicMock

import pytest

from msalt.news.briefing import BriefingGenerator


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get_articles_since.return_value = [
        {"source": "한경", "title": "경제 성장률 상승", "url": "https://hk.com/1", "summary": "2분기 성장률 전망", "category": "domestic", "collected_at": "2026-04-12 07:00:00"},
        {"source": "Reuters", "title": "Fed holds rates", "url": "https://reuters.com/1", "summary": "Federal Reserve holds interest rates", "category": "international", "collected_at": "2026-04-12 07:00:00"},
        {"source": "삼프로TV", "title": "시장 분석", "url": "https://youtube.com/watch?v=abc", "summary": "이번 주 시장 분석", "category": "youtube", "collected_at": "2026-04-12 07:00:00"},
    ]
    return storage


def test_format_briefing(mock_storage):
    gen = BriefingGenerator(storage=mock_storage)
    text = gen.format_briefing("morning")
    assert "아침 경제 브리핑" in text
    assert "국내" in text
    assert "해외" in text
    assert "유튜브" in text
    assert "경제 성장률 상승" in text
    assert "Fed holds rates" in text
    assert "시장 분석" in text


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
