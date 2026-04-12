import json
import logging
from pathlib import Path

import feedparser

logger = logging.getLogger(__name__)


class RssCollector:
    """RSS 피드에서 뉴스 기사를 수집한다."""

    def __init__(self, sources_path: str = "msalt/news/sources.json"):
        self.sources_path = sources_path

    def load_sources(self) -> list[dict]:
        path = Path(self.sources_path)
        if not path.exists():
            logger.warning("sources.json not found: %s", self.sources_path)
            return []
        with open(path) as f:
            data = json.load(f)
        return data.get("rss", [])

    def collect_from_source(self, source: dict) -> list[dict]:
        feed = feedparser.parse(source["url"])
        if feed.bozo:
            logger.warning("Failed to parse feed: %s", source["name"])
            return []

        articles = []
        for entry in feed.entries:
            articles.append({
                "source": source["name"],
                "title": entry.title,
                "url": entry.link,
                "summary": entry.get("summary", ""),
                "category": source["category"],
                "published": entry.get("published", ""),
            })
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
