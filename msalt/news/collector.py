import logging

from msalt.news.rss import RssCollector
from msalt.storage import Storage

logger = logging.getLogger(__name__)


class NewsCollector:
    """RSS + YouTube에서 뉴스를 수집하여 저장소에 저장한다."""

    def __init__(self, storage: Storage, sources_path: str = "msalt/news/sources.json",
                 youtube_api_key: str | None = None):
        self.storage = storage
        self.sources_path = sources_path
        self.rss = RssCollector(sources_path=sources_path)
        self.youtube_api_key = youtube_api_key

    def collect(self) -> int:
        """모든 소스에서 뉴스를 수집하고 저장한다. 수집된 기사 수를 반환."""
        count = 0

        # RSS 수집
        rss_articles = self.rss.collect_all()
        for article in rss_articles:
            self.storage.insert_article(
                source=article["source"],
                title=article["title"],
                url=article["url"],
                summary=article["summary"],
                category=article["category"],
            )
            count += 1

        # YouTube 수집
        if self.youtube_api_key:
            try:
                from msalt.news.youtube import YoutubeCollector
                yt = YoutubeCollector(api_key=self.youtube_api_key, sources_path=self.sources_path)
                yt_articles = yt.collect_all()
                for article in yt_articles:
                    self.storage.insert_article(
                        source=article["source"],
                        title=article["title"],
                        url=article["url"],
                        summary=article["summary"],
                        category=article["category"],
                    )
                    count += 1
            except Exception:
                logger.exception("YouTube collection failed")

        logger.info("Total collected: %d articles", count)
        return count
