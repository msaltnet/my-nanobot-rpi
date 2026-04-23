import logging
from datetime import datetime, timedelta, timezone

from msalt.storage import Storage

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5-mini"
MAX_ARTICLES_PER_CATEGORY = 10

CATEGORY_LABELS = {
    "domestic": "국내",
    "international": "해외",
    "policy": "정책·지표",
    "reddit": "커뮤니티",
}

CATEGORY_ORDER = ["domestic", "international", "policy", "reddit"]

SYSTEM_PROMPT = (
    "당신은 한국어 경제 뉴스 편집자다. 주어진 기사 목록을 읽고 "
    "카테고리의 핵심 흐름을 요약한다.\n"
    "규칙:\n"
    "- 총 5문장 이내. 더 쓰지 말 것.\n"
    "- 사실만, 추측 금지.\n"
    "- 중복되는 헤드라인은 하나로 합친다.\n"
    "- 한 문장에 하나의 주제만. 여러 주제를 접속사로 이어 붙이지 말 것.\n"
    "- 숫자·고유명사는 원문 그대로.\n"
    "- 서론·맺음말 없이 본론만.\n"
    "- 각 문장 끝에 근거 기사 번호를 [1], [1,3] 형태로 표기."
)


class BriefingGenerator:
    """수집된 뉴스를 카테고리별 LLM 요약 + 원문 링크로 정리한 브리핑 텍스트를 생성한다."""

    def __init__(
        self,
        storage: Storage,
        *,
        use_llm: bool = True,
        model: str = DEFAULT_MODEL,
    ):
        self.storage = storage
        self.use_llm = use_llm
        self.model = model

    def get_articles_for_briefing(self, hours: int = 12) -> list[dict]:
        # collected_at은 SQLite datetime('now') = UTC로 저장되므로 비교도 UTC로 맞춘다.
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        articles = self.storage.get_articles_since(since)
        seen_urls = set()
        unique = []
        for article in articles:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                unique.append(article)
        return unique

    def format_briefing(self, time_of_day: str = "morning") -> str:
        articles = self.get_articles_for_briefing()
        label = "아침" if time_of_day == "morning" else "저녁"

        if not articles:
            return f"{label} 경제 브리핑 - 수집된 뉴스가 없습니다."

        today = datetime.now().strftime("%Y-%m-%d")
        lines = [f"{label} 경제 브리핑 ({today})", ""]

        for category in CATEGORY_ORDER:
            bucket = [a for a in articles if a["category"] == category][:MAX_ARTICLES_PER_CATEGORY]
            if not bucket:
                continue
            lines.append(f"[{CATEGORY_LABELS[category]}]")
            lines.append(self._render_category(bucket))
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _render_category(self, articles: list[dict]) -> str:
        if self.use_llm:
            summary = self._summarize_with_llm(articles)
            if summary:
                return summary + "\n\n" + _format_sources(articles)
            # LLM 실패 시 단순 나열로 폴백
        return _format_plain(articles)

    def _summarize_with_llm(self, articles: list[dict]) -> str | None:
        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("openai package not available; falling back to plain listing")
            return None

        user_content = _build_user_prompt(articles)
        try:
            client = OpenAI()
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("LLM summarization failed, falling back: %s", e)
            return None


def _build_user_prompt(articles: list[dict]) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        title = a.get("title", "").strip()
        summary = (a.get("summary", "") or "").strip()[:300]
        source = a.get("source", "").strip()
        snippet = f"{i}. [{source}] {title}"
        if summary:
            snippet += f" — {summary}"
        lines.append(snippet)
    return "\n".join(lines)


def _format_sources(articles: list[dict]) -> str:
    lines = ["주요 출처:"]
    for i, a in enumerate(articles, 1):
        lines.append(f"  [{i}] {a['url']}")
    return "\n".join(lines)


def _format_plain(articles: list[dict]) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. [{a.get('source', '')}] {a['title']}")
        if a.get("summary"):
            lines.append(f"   {a['summary'][:200]}")
        lines.append(f"   원문: {a['url']}")
    return "\n".join(lines)
