import json
import logging
import os
from pathlib import Path

import httpx

from msalt.news.rss import DEFAULT_SOURCES_PATH, REQUEST_TIMEOUT, USER_AGENT
from msalt.news.utils import clean_text, current_utc_string, normalize_datetime

logger = logging.getLogger(__name__)

TAVILY_ENDPOINT = "https://api.tavily.com/search"
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class SearchCollector:
    """검색 API로 RSS가 놓친 최신 경제 뉴스를 보강한다."""

    def __init__(self, sources_path: str | None = None):
        self.sources_path = sources_path or DEFAULT_SOURCES_PATH

    def load_sources(self) -> list[dict]:
        path = Path(self.sources_path)
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("search", [])

    def collect_all(self) -> list[dict]:
        articles = []
        for source in self.load_sources():
            provider = source.get("provider")
            if provider == "tavily":
                articles.extend(self._collect_tavily(source))
            elif provider == "brave":
                articles.extend(self._collect_brave(source))
            else:
                logger.warning("Unknown search provider: %s", provider)
        return articles

    def _collect_tavily(self, source: dict) -> list[dict]:
        api_key = os.environ.get(source.get("api_key_env", "TAVILY_API_KEY"), "").strip()
        if not api_key:
            logger.info("Skip Tavily source %s: API key missing", source.get("name"))
            return []

        payload = {
            "query": source["query"],
            "topic": source.get("topic", "news"),
            "search_depth": source.get("search_depth", "basic"),
            "max_results": source.get("max_results", 10),
            "include_answer": False,
            "include_raw_content": False,
        }
        if source.get("days") is not None:
            payload["days"] = source["days"]

        try:
            resp = httpx.post(
                TAVILY_ENDPOINT,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": USER_AGENT,
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Failed Tavily search %s: %s", source.get("name"), e)
            return []

        return [
            self._article_from_search_result(source, item)
            for item in resp.json().get("results", [])
            if item.get("url") and item.get("title")
        ]

    def _collect_brave(self, source: dict) -> list[dict]:
        api_key = os.environ.get(source.get("api_key_env", "BRAVE_API_KEY"), "").strip()
        if not api_key:
            logger.info("Skip Brave source %s: API key missing", source.get("name"))
            return []

        params = {
            "q": source["query"],
            "count": min(int(source.get("count", 10)), 20),
            "safesearch": source.get("safesearch", "moderate"),
        }
        for key in ("freshness", "country", "search_lang"):
            if source.get(key):
                params[key] = source[key]

        try:
            resp = httpx.get(
                BRAVE_ENDPOINT,
                params=params,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": api_key,
                    "User-Agent": USER_AGENT,
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Failed Brave search %s: %s", source.get("name"), e)
            return []

        results = resp.json().get("web", {}).get("results", [])
        return [
            self._article_from_search_result(source, item)
            for item in results
            if item.get("url") and item.get("title")
        ]

    def _article_from_search_result(self, source: dict, item: dict) -> dict:
        published_at = (
            normalize_datetime(item.get("published_date"))
            or normalize_datetime(item.get("published"))
            or normalize_datetime(item.get("age"))
        )
        if not published_at and source.get("assume_current_if_missing", False):
            published_at = current_utc_string()

        return {
            "source": source["name"],
            "title": clean_text(item.get("title")),
            "url": item["url"],
            "summary": clean_text(item.get("content") or item.get("description") or ""),
            "category": source.get("category", "domestic"),
            "published_at": published_at,
        }
