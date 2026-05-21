import json
import logging
from pathlib import Path

from msalt.news.rss import DEFAULT_SOURCES_PATH, RssCollector

logger = logging.getLogger(__name__)


class OfficialFeedCollector:
    """중앙은행·금융당국 등 공식기관 feed를 별도 단계로 수집."""

    def __init__(self, sources_path: str | None = None):
        self.sources_path = sources_path or DEFAULT_SOURCES_PATH
        self.rss = RssCollector(sources_path=self.sources_path)

    def load_sources(self) -> list[dict]:
        path = Path(self.sources_path)
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("official_rss", [])

    def collect_all(self) -> list[dict]:
        articles = []
        for source in self.load_sources():
            try:
                collected = self.rss.collect_from_source(source)
                articles.extend(collected)
                logger.info(
                    "Collected %d official articles from %s",
                    len(collected),
                    source["name"],
                )
            except Exception:
                logger.exception("Error collecting official source %s", source["name"])
        return articles
