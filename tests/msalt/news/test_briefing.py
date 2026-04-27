from unittest.mock import MagicMock, patch

import pytest

from msalt.news.briefing import BriefingGenerator


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get_articles_since.return_value = [
        {"source": "한경", "title": "경제 성장률 상승", "url": "https://hk.com/1", "summary": "2분기 성장률 전망", "category": "domestic", "collected_at": "2026-04-12 07:00:00", "published_at": "2026-04-12 06:30:00"},
        {"source": "Reuters", "title": "Fed holds rates", "url": "https://reuters.com/1", "summary": "Federal Reserve holds interest rates", "category": "international", "collected_at": "2026-04-12 07:00:00", "published_at": "2026-04-12 05:45:00"},
    ]
    return storage


def test_format_briefing_plain_mode(mock_storage):
    gen = BriefingGenerator(storage=mock_storage, use_llm=False)
    text = gen.format_briefing("morning")
    assert "아침 경제 브리핑" in text
    assert "국내" in text
    assert "해외" in text
    assert "경제 성장률 상승" in text
    assert "Fed holds rates" in text


def test_format_briefing_includes_policy_section():
    storage = MagicMock()
    storage.get_articles_since.return_value = [
        {"source": "Fed Monetary Policy", "title": "FOMC statement", "url": "https://fed.gov/1", "summary": "Rate held at 4.25%", "category": "policy", "collected_at": "2026-04-23 07:00:00", "published_at": "2026-04-23 06:30:00"},
    ]
    gen = BriefingGenerator(storage=storage, use_llm=False)
    text = gen.format_briefing("morning")
    assert "[정책·지표]" in text
    assert "Fed Monetary Policy" in text
    assert "FOMC statement" in text


def test_format_briefing_empty(mock_storage):
    mock_storage.get_articles_since.return_value = []
    gen = BriefingGenerator(storage=mock_storage, use_llm=False)
    text = gen.format_briefing("morning")
    assert "수집된 뉴스가 없습니다" in text


def test_get_articles_for_briefing_deduplicates(mock_storage):
    mock_storage.get_articles_since.return_value = [
        {"source": "한경", "title": "같은 기사", "url": "https://same.com", "summary": "a", "category": "domestic", "collected_at": "2026-04-12", "published_at": "2026-04-12"},
        {"source": "매경", "title": "같은 기사", "url": "https://same.com", "summary": "b", "category": "domestic", "collected_at": "2026-04-12", "published_at": "2026-04-12"},
    ]
    gen = BriefingGenerator(storage=mock_storage, use_llm=False)
    articles = gen.get_articles_for_briefing()
    assert len(articles) == 1


def test_get_articles_for_briefing_requires_published_at_by_default(mock_storage):
    """브리핑은 발행일 미상 항목을 기본 제외해 RSS의 옛 기사 재노출을 방지한다."""
    gen = BriefingGenerator(storage=mock_storage, use_llm=False)
    gen.get_articles_for_briefing()
    # storage에 require_published_at=True로 호출됐는지 확인
    _, kwargs = mock_storage.get_articles_since.call_args
    assert kwargs.get("require_published_at") is True


def test_get_articles_for_briefing_can_include_null_published(mock_storage):
    gen = BriefingGenerator(storage=mock_storage, use_llm=False)
    gen.get_articles_for_briefing(require_published_at=False)
    _, kwargs = mock_storage.get_articles_since.call_args
    assert kwargs.get("require_published_at") is False


# LLM 모드 테스트 — OpenAI 호출을 mock해 네트워크 없이 동작 확인

def _fake_openai_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=text))]
    return resp


@patch("openai.OpenAI")
def test_llm_mode_inserts_summary_and_sources(MockOpenAI, mock_storage):
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response(
        "2분기 성장률 상승 전망이 우세하다. [1]"
    )
    MockOpenAI.return_value = client

    gen = BriefingGenerator(storage=mock_storage, use_llm=True)
    text = gen.format_briefing("morning")

    assert "2분기 성장률 상승 전망이 우세하다. [1]" in text
    assert "주요 출처:" in text
    assert "https://hk.com/1" in text
    # 단순 나열 포맷의 "원문:" 프리픽스는 LLM 모드에선 나오지 않아야 한다
    assert "   원문:" not in text


@patch("openai.OpenAI")
def test_llm_mode_falls_back_on_error(MockOpenAI, mock_storage):
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("API down")
    MockOpenAI.return_value = client

    gen = BriefingGenerator(storage=mock_storage, use_llm=True)
    text = gen.format_briefing("morning")

    # 폴백 — 원문 프리픽스 포함된 단순 나열로 돌아와야 한다
    assert "   원문: https://hk.com/1" in text
    assert "경제 성장률 상승" in text


@patch("openai.OpenAI")
def test_llm_mode_uses_configured_model(MockOpenAI, mock_storage):
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response("요약")
    MockOpenAI.return_value = client

    gen = BriefingGenerator(storage=mock_storage, use_llm=True, model="gpt-4o-mini")
    gen.format_briefing("morning")

    # 한 번 이상 호출됐고 model 인자가 전달됐는지 확인
    assert client.chat.completions.create.called
    call = client.chat.completions.create.call_args
    assert call.kwargs["model"] == "gpt-4o-mini"


@patch("openai.OpenAI")
def test_llm_prompt_includes_published_at(MockOpenAI, mock_storage):
    """LLM이 시점을 인지할 수 있도록 user prompt에 발행일이 들어가야 한다."""
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response("요약")
    MockOpenAI.return_value = client

    gen = BriefingGenerator(storage=mock_storage, use_llm=True)
    gen.format_briefing("morning")

    # _summarize_with_llm은 카테고리별로 호출됨 → 모든 호출의 user prompt를 합쳐 검증
    all_user_content = "\n".join(
        m["content"]
        for call in client.chat.completions.create.call_args_list
        for m in call.kwargs["messages"]
        if m["role"] == "user"
    )
    assert "2026-04-12 06:30:00" in all_user_content  # 한경 (domestic)
    assert "2026-04-12 05:45:00" in all_user_content  # Reuters (international)
