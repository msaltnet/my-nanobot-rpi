import json
import logging
import re
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
