import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import httpx

from msalt.news.rss import DEFAULT_SOURCES_PATH, REQUEST_TIMEOUT, USER_AGENT
from msalt.news.utils import clean_text, current_utc_string, normalize_datetime

logger = logging.getLogger(__name__)


class FallbackCollector:
    """RSS가 비거나 깨질 때 HTML 목록/사이트맵에서 최신 링크를 보강 수집."""

    def __init__(self, sources_path: str | None = None):
        self.sources_path = sources_path or DEFAULT_SOURCES_PATH

    def load_sources(self) -> list[dict]:
        path = Path(self.sources_path)
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("fallback", [])

    def collect_all(self) -> list[dict]:
        articles = []
        for source in self.load_sources():
            try:
                if source.get("sitemap_url"):
                    articles.extend(self.collect_from_sitemap(source))
                if source.get("url"):
                    articles.extend(self.collect_from_html(source))
            except Exception:
                logger.exception("Error collecting fallback source %s", source.get("name"))
        return _dedupe_articles(articles)

    def collect_from_html(self, source: dict) -> list[dict]:
        try:
            resp = httpx.get(
                source["url"],
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Failed fallback HTML %s: %s", source.get("name"), e)
            return []

        limit = int(source.get("limit", 20))
        patterns = source.get("link_patterns", [])
        articles = []
        seen = set()
        for href, label in _extract_links(resp.text):
            url = urljoin(source["url"], href)
            if url in seen or not _matches_url(url, patterns):
                continue
            title = clean_text(label)
            if len(title) < int(source.get("min_title_length", 8)):
                continue
            seen.add(url)
            articles.append(_make_article(source, title, url, ""))
            if len(articles) >= limit:
                break
        return articles

    def collect_from_sitemap(self, source: dict) -> list[dict]:
        limit = int(source.get("limit", 20))
        max_sitemaps = int(source.get("max_sitemaps", 3))
        entries = self._read_sitemap_entries(source["sitemap_url"], max_sitemaps=max_sitemaps)
        patterns = source.get("link_patterns", [])
        articles = []
        for loc, lastmod in entries:
            if not _matches_url(loc, patterns):
                continue
            title = _title_from_url(loc)
            if len(title) < int(source.get("min_title_length", 8)):
                continue
            articles.append(_make_article(source, title, loc, "", lastmod=lastmod))
            if len(articles) >= limit:
                break
        return articles

    def _read_sitemap_entries(
        self,
        sitemap_url: str,
        *,
        max_sitemaps: int,
    ) -> list[tuple[str, str | None]]:
        try:
            resp = httpx.get(
                sitemap_url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Failed fallback sitemap %s: %s", sitemap_url, e)
            return []

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            logger.warning("Failed parsing sitemap: %s", sitemap_url)
            return []

        tag = _strip_ns(root.tag)
        if tag == "sitemapindex":
            entries = []
            child_urls = [
                _child_text(sitemap, "loc")
                for sitemap in root
                if _strip_ns(sitemap.tag) == "sitemap"
            ]
            for child_url in [u for u in child_urls if u][:max_sitemaps]:
                entries.extend(
                    self._read_sitemap_entries(child_url, max_sitemaps=0)
                )
            return entries

        entries = []
        for item in root:
            if _strip_ns(item.tag) != "url":
                continue
            loc = _child_text(item, "loc")
            if not loc:
                continue
            entries.append((loc, _child_text(item, "lastmod")))
        return entries


def _extract_links(html: str) -> list[tuple[str, str]]:
    link_re = re.compile(
        r"<a\b[^>]*?href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    return link_re.findall(html)


def _matches_url(url: str, patterns: list[str]) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    if not patterns:
        return True
    return any(pattern in url for pattern in patterns)


def _make_article(
    source: dict,
    title: str,
    url: str,
    summary: str,
    *,
    lastmod: str | None = None,
) -> dict:
    published_at = normalize_datetime(lastmod)
    if not published_at and source.get("assume_current_if_missing", False):
        published_at = current_utc_string()
    return {
        "source": source["name"],
        "title": title,
        "url": url,
        "summary": clean_text(summary),
        "category": source.get("category", "domestic"),
        "published_at": published_at,
    }


def _title_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1]
    if not slug:
        return url
    slug = re.sub(r"\.[a-zA-Z0-9]+$", "", slug)
    slug = unquote(slug)
    slug = re.sub(r"[-_]+", " ", slug)
    return clean_text(slug)


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, name: str) -> str | None:
    for child in node:
        if _strip_ns(child.tag) == name and child.text:
            return child.text.strip()
    return None


def _dedupe_articles(articles: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for article in articles:
        url = article.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(article)
    return unique
