import logging

from msalt.news.fallback import FallbackCollector
from msalt.news.official import OfficialFeedCollector
from msalt.news.rss import DEFAULT_SOURCES_PATH, RssCollector
from msalt.news.search import SearchCollector
from msalt.storage import Storage

logger = logging.getLogger(__name__)


class NewsCollector:
    """RSS에서 뉴스를 수집하여 저장소에 저장한다."""

    def __init__(self, storage: Storage, sources_path: str | None = None):
        self.storage = storage
        self.sources_path = sources_path or DEFAULT_SOURCES_PATH
        self.rss = RssCollector(sources_path=self.sources_path)
        self.official = OfficialFeedCollector(sources_path=self.sources_path)
        self.search = SearchCollector(sources_path=self.sources_path)
        self.fallback = FallbackCollector(sources_path=self.sources_path)

    def collect(self) -> int:
        """모든 소스에서 뉴스를 수집하고 저장한다. 수집된 기사 수를 반환."""
        count = 0

        fetched = 0
        for article in self._collect_articles():
            fetched += 1
            inserted = self.storage.insert_article(
                source=article["source"],
                title=article["title"],
                url=article["url"],
                summary=article["summary"],
                category=article["category"],
                published_at=article.get("published_at"),
            )
            if inserted is not False:
                count += 1

        logger.info("Total fetched: %d articles, inserted: %d new articles", fetched, count)
        return count

    def _collect_articles(self) -> list[dict]:
        articles = []
        for name, collector in [
            ("rss", self.rss),
            ("official", self.official),
            ("search", self.search),
            ("fallback", self.fallback),
        ]:
            try:
                collected = collector.collect_all()
                articles.extend(collected)
                logger.info("Collected %d articles via %s", len(collected), name)
            except Exception:
                logger.exception("Error collecting via %s", name)
        return _dedupe_articles(articles)


def _dedupe_articles(articles: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for article in articles:
        url = article.get("url")
        title = article.get("title")
        if not url or not title or url in seen:
            continue
        seen.add(url)
        unique.append(article)
    return unique
