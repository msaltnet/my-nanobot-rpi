import calendar
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import httpx

logger = logging.getLogger(__name__)

# Reddit 등 UA 없이는 403을 반환하는 엔드포인트가 있어 명시한다.
# feedparser.parse(url)은 Accept 헤더 조합이 차단되므로 httpx로 직접 받아서 넘긴다.
USER_AGENT = "Mozilla/5.0 (compatible; msalt-nanobot/1.0)"
REQUEST_TIMEOUT = 10.0


class RssCollector:
    """RSS/Atom 피드에서 뉴스 기사를 수집한다."""

    def __init__(self, sources_path: str = "msalt/news/sources.json"):
        self.sources_path = sources_path

    def load_sources(self) -> list[dict]:
        path = Path(self.sources_path)
        if not path.exists():
            logger.warning("sources.json not found: %s", self.sources_path)
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("rss", [])

    def collect_from_source(self, source: dict) -> list[dict]:
        try:
            resp = httpx.get(
                source["url"],
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Failed to fetch feed %s: %s", source["name"], e)
            return []

        feed = feedparser.parse(resp.content)
        if feed.bozo:
            logger.warning("Failed to parse feed: %s", source["name"])
            return []

        skip_patterns = source.get("skip_title_patterns", [])
        limit = source.get("limit")

        articles = []
        for entry in feed.entries:
            title = getattr(entry, "title", "")
            if _matches_any(title, skip_patterns):
                continue
            articles.append({
                "source": source["name"],
                "title": title,
                "url": entry.link,
                "summary": entry.get("summary", ""),
                "category": source["category"],
                "published": entry.get("published", ""),
                "published_at": _normalize_published(entry),
            })
            if limit and len(articles) >= limit:
                break
        return articles

    def collect_all(self) -> list[dict]:
        sources = self.load_sources()
        all_articles = []
        for source in sources:
            try:
                articles = self.collect_from_source(source)
                all_articles.extend(articles)
                logger.info("Collected %d articles from %s", len(articles), source["name"])
            except Exception:
                logger.exception("Error collecting from %s", source["name"])
        return all_articles


def _matches_any(title: str, patterns: list[str]) -> bool:
    return any(re.search(p, title, re.IGNORECASE) for p in patterns)


def _normalize_published(entry) -> str | None:
    """RSS entry의 발행일을 'YYYY-MM-DD HH:MM:SS' UTC 문자열로 정규화.

    feedparser는 RFC 822/8601 등 다양한 포맷을 ``published_parsed`` (struct_time, UTC)
    로 파싱해 두기 때문에 그걸 1순위로 쓴다. 없으면 ``updated_parsed``로 폴백.
    parser가 실패해 둘 다 ``None``이거나 미래 시각이면 ``None``을 반환 — 브리핑에서
    NULL 처리되어 신뢰 못 할 항목으로 분류된다.
    """
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None
    try:
        ts = calendar.timegm(parsed)  # struct_time (UTC) → epoch
    except (TypeError, ValueError, OverflowError):
        return None
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    # 미래 시각(피드 타임존 오류로 종종 나옴) — 신뢰 못 하므로 NULL
    if dt > datetime.now(timezone.utc):
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")
