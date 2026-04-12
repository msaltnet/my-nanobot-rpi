import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YoutubeCollector:
    """YouTube Data API로 채널별 최신 영상을 수집한다."""

    def __init__(self, api_key: str, sources_path: str = "msalt/news/sources.json"):
        self.api_key = api_key
        self.sources_path = sources_path

    def load_sources(self) -> list[dict]:
        path = Path(self.sources_path)
        if not path.exists():
            return []
        with open(path) as f:
            data = json.load(f)
        return data.get("youtube", [])

    def get_recent_videos(self, channel_id: str, max_results: int = 5) -> list[dict]:
        resp = httpx.get(
            f"{YOUTUBE_API_BASE}/search",
            params={
                "key": self.api_key,
                "channelId": channel_id,
                "part": "snippet",
                "order": "date",
                "type": "video",
                "maxResults": max_results,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        videos = []
        for item in data.get("items", []):
            snippet = item["snippet"]
            videos.append({
                "video_id": item["id"]["videoId"],
                "title": snippet["title"],
                "channel": snippet["channelTitle"],
                "description": snippet.get("description", ""),
                "published_at": snippet["publishedAt"],
            })
        return videos

    def get_transcript(self, video_id: str) -> str | None:
        """YouTube 자막을 가져온다. 자막이 없으면 None 반환."""
        try:
            resp = httpx.get(
                f"{YOUTUBE_API_BASE}/captions",
                params={
                    "key": self.api_key,
                    "videoId": video_id,
                    "part": "snippet",
                },
            )
            resp.raise_for_status()
            captions = resp.json().get("items", [])
            if not captions:
                return None
            return None
        except Exception:
            logger.debug("No transcript for %s", video_id)
            return None

    def format_as_article(self, video: dict, transcript: str | None = None) -> dict:
        summary = transcript if transcript else video["description"]
        return {
            "source": video["channel"],
            "title": video["title"],
            "url": f"https://www.youtube.com/watch?v={video['video_id']}",
            "summary": summary,
            "category": "youtube",
            "published": video["published_at"],
        }

    def collect_all(self) -> list[dict]:
        sources = self.load_sources()
        all_articles = []
        for source in sources:
            try:
                videos = self.get_recent_videos(source["channel_id"])
                for video in videos:
                    transcript = self.get_transcript(video["video_id"])
                    article = self.format_as_article(video, transcript)
                    all_articles.append(article)
                logger.info("Collected %d videos from %s", len(videos), source["name"])
            except Exception:
                logger.exception("Error collecting from YouTube channel %s", source.get("name"))
        return all_articles
