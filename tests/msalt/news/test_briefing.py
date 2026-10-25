from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from msalt.news.briefing import BriefingGenerator, _briefing_since_utc


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get_articles_since.return_value = [
        {"source": "한경", "title": "경제 성장률 상승", "url": "https://hk.com/1", "summary": "2분기 성장률 전망", "category": "domestic", "collected_at": "2026-04-12 07:00:00", "published_at": "2026-04-12 06:30:00"},
        {"source": "Reuters", "title": "Fed holds rates", "url": "https://reuters.com/1", "summary": "Federal Reserve holds interest rates", "category": "international", "collected_at": "2026-04-12 07:00:00", "published_at": "2026-04-12 05:45:00"},
    ]
    storage.get_briefed_article_urls.return_value = set()
    return storage


def test_format_briefing_plain_mode(mock_storage):
    gen = BriefingGenerator(storage=mock_storage, use_llm=False)
    text = gen.format_briefing("morning")
    assert "아침 경제 브리핑" in text
    assert "국내" in text
    assert "해외" in text
    assert "경제 성장률 상승" in text
    assert "Fed holds rates" not in text
    assert "Federal Reserve holds interest rates" not in text
    assert "한국어 요약을 생성하지 못했습니다" in text
    assert "https://reuters.com/1" in text


def test_format_briefing_afternoon_uses_lunch_label(mock_storage):
    gen = BriefingGenerator(storage=mock_storage, use_llm=False)

    text = gen.format_briefing("afternoon")

    assert "점심 경제 브리핑" in text


def test_format_briefing_includes_policy_section():
    storage = MagicMock()
    storage.get_articles_since.return_value = [
        {"source": "Fed Monetary Policy", "title": "FOMC statement", "url": "https://fed.gov/1", "summary": "Rate held at 4.25%", "category": "policy", "collected_at": "2026-04-23 07:00:00", "published_at": "2026-04-23 06:30:00"},
    ]
    gen = BriefingGenerator(storage=storage, use_llm=False)
    text = gen.format_briefing("morning")
    assert "[정책·지표]" in text
    assert "Fed Monetary Policy" in text
    assert "FOMC statement" not in text
    assert "Rate held at 4.25%" not in text
    assert "한국어 요약을 생성하지 못했습니다" in text


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


def test_get_articles_for_briefing_excludes_already_briefed_urls(mock_storage):
    mock_storage.get_briefed_article_urls.return_value = {"https://hk.com/1"}
    gen = BriefingGenerator(storage=mock_storage, use_llm=False)

    articles = gen.get_articles_for_briefing()

    assert [a["url"] for a in articles] == ["https://reuters.com/1"]


@pytest.mark.parametrize('legacy_mark', [False, True])
def test_format_briefing_preserves_rendered_urls_without_marking(mock_storage, legacy_mark):
    gen = BriefingGenerator(storage=mock_storage, use_llm=False)
    text = gen.format_briefing('evening', mark_as_briefed=legacy_mark)
    assert 'https://hk.com/1' in text and 'https://reuters.com/1' in text
    mock_storage.mark_articles_briefed.assert_not_called()


def test_format_briefing_can_skip_marking_articles(mock_storage):
    gen = BriefingGenerator(storage=mock_storage, use_llm=False)

    gen.format_briefing("morning", mark_as_briefed=False)

    mock_storage.mark_articles_briefed.assert_not_called()


def test_briefing_since_splits_morning_and_evening_windows():
    now = datetime(2026, 5, 23, 19, 10, tzinfo=ZoneInfo("Asia/Seoul"))

    assert _briefing_since_utc("morning", now) == "2026-05-22 10:00:00"
    assert _briefing_since_utc("afternoon", now) == "2026-05-22 22:00:00"
    assert _briefing_since_utc("evening", now) == "2026-05-23 05:00:00"


def test_briefing_since_rejects_unknown_time_of_day():
    with pytest.raises(ValueError, match="morning, afternoon, evening"):
        _briefing_since_utc("night")


# LLM 모드 테스트 — OpenAI 호출을 mock해 네트워크 없이 동작 확인

def _fake_openai_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=text))]
    return resp


@patch("openai.OpenAI")
def test_llm_mode_inserts_summary_and_sources(mock_openai_cls, mock_storage):
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response(
        "2분기 성장률 상승 전망이 우세하다. [1]"
    )
    mock_openai_cls.return_value = client

    gen = BriefingGenerator(storage=mock_storage, use_llm=True)
    text = gen.format_briefing("morning")

    assert "2분기 성장률 상승 전망이 우세하다. [1]" in text
    assert "주요 출처:" in text
    assert "https://hk.com/1" in text
    # 단순 나열 포맷의 "원문:" 프리픽스는 LLM 모드에선 나오지 않아야 한다
    assert "   원문:" not in text


@patch("openai.OpenAI")
def test_llm_mode_falls_back_on_error(mock_openai_cls, mock_storage):
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("API down")
    mock_openai_cls.return_value = client

    gen = BriefingGenerator(storage=mock_storage, use_llm=True)
    text = gen.format_briefing("morning")

    # 폴백 — 원문 프리픽스 포함된 단순 나열로 돌아와야 한다
    assert "   원문: https://hk.com/1" in text
    assert "경제 성장률 상승" in text


@patch("openai.OpenAI")
def test_llm_mode_uses_configured_model(mock_openai_cls, mock_storage):
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response("요약")
    mock_openai_cls.return_value = client

    gen = BriefingGenerator(storage=mock_storage, use_llm=True, model="gpt-4o-mini")
    gen.format_briefing("morning")

    # 한 번 이상 호출됐고 model 인자가 전달됐는지 확인
    assert client.chat.completions.create.called
    call = client.chat.completions.create.call_args
    assert call.kwargs["model"] == "gpt-4o-mini"


@patch("openai.OpenAI")
def test_llm_prompt_includes_published_at(mock_openai_cls, mock_storage):
    """LLM이 시점을 인지할 수 있도록 user prompt에 발행일이 들어가야 한다."""
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response("요약")
    mock_openai_cls.return_value = client

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


@pytest.mark.parametrize("response", [None, "", "   ", RuntimeError("API down")])
@patch("openai.OpenAI")
def test_english_fallback_hides_untranslated_content(mock_openai_cls, mock_storage, response):
    client = mock_openai_cls.return_value
    if isinstance(response, Exception):
        client.chat.completions.create.side_effect = response
    else:
        client.chat.completions.create.return_value = _fake_openai_response(response)
    reserved = []
    gen = BriefingGenerator(mock_storage, before_summary=lambda: reserved.append(True))
    articles = mock_storage.get_articles_since.return_value
    result = gen.render_articles(articles)
    assert "Fed holds rates" not in result.text
    assert "Federal Reserve holds interest rates" not in result.text
    assert "한국어 요약을 생성하지 못했습니다" in result.text
    assert "경제 성장률 상승" in result.text
    assert "2분기 성장률 전망" in result.text
    assert result.urls == ("https://hk.com/1", "https://reuters.com/1")
    assert "https://reuters.com/1" in result.text
    assert len(reserved) == 2
    assert client.chat.completions.create.call_count == 2
    assert mock_openai_cls.call_args.kwargs["max_retries"] == 0


@pytest.mark.parametrize("title,summary,visible,hidden", [
    ("한국 금리 동결", "Federal Reserve holds interest rates", "한국 금리 동결", "Federal Reserve holds interest rates"),
    ("Fed holds rates", "금리는 4.25%로 유지됐다", "금리는 4.25%로 유지됐다", "Fed holds rates"),
    ("해외 Fed holds rates", "한국 경제 회복", "한국 경제 회복", "해외 Fed holds rates"),
    ("AI 투자 4.25% 증가", "성장률 2% 전망", "AI 투자 4.25% 증가", None),
    ("FED HOLDS RATES", "RATE HELD", None, "FED HOLDS RATES"),
])
def test_plain_mode_handles_each_language_field(mock_storage, title, summary, visible, hidden):
    article = dict(mock_storage.get_articles_since.return_value[1], title=title, summary=summary)
    result = BriefingGenerator(mock_storage, use_llm=False).render_articles([article])
    if visible:
        assert visible in result.text
    if hidden:
        assert hidden not in result.text
        assert "한국어 요약을 생성하지 못했습니다" in result.text
    assert result.urls == ("https://reuters.com/1",)
    assert "원문: https://reuters.com/1" in result.text


@patch("openai.OpenAI")
def test_english_news_requests_korean_translation_in_same_call(mock_openai_cls, mock_storage):
    article = dict(mock_storage.get_articles_since.return_value[1], summary="Rate held at 4.25%")
    client = mock_openai_cls.return_value
    client.chat.completions.create.return_value = _fake_openai_response("미 연준이 금리를 4.25%로 동결했다. [1]")
    result = BriefingGenerator(mock_storage).render_articles([article])
    assert "미 연준이 금리를 4.25%로 동결했다. [1]" in result.text
    assert "주요 출처:" in result.text
    assert "https://reuters.com/1" in result.text
    assert "한국어 요약을 생성하지 못했습니다" not in result.text
    assert result.urls == ("https://reuters.com/1",)
    client.chat.completions.create.assert_called_once()
    messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert "한국어로 번역" in messages[0]["content"]
    assert "수치" in messages[0]["content"]
    assert "Fed holds rates" in messages[1]["content"]
    assert "4.25%" in messages[1]["content"]
