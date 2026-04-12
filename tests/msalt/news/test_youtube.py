from unittest.mock import patch, MagicMock

import pytest

from msalt.news.youtube import YoutubeCollector


MOCK_SEARCH_RESPONSE = {
    "items": [
        {
            "id": {"videoId": "abc123"},
            "snippet": {
                "title": "경제 전망 분석",
                "channelTitle": "삼프로TV",
                "publishedAt": "2026-04-12T09:00:00Z",
                "description": "이번 분기 경제 전망을 분석합니다.",
            },
        }
    ]
}


@patch("msalt.news.youtube.httpx.get")
def test_get_recent_videos(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_SEARCH_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    collector = YoutubeCollector(api_key="test-key")
    videos = collector.get_recent_videos("UC_channel_id")
    assert len(videos) == 1
    assert videos[0]["title"] == "경제 전망 분석"
    assert videos[0]["video_id"] == "abc123"
    assert videos[0]["channel"] == "삼프로TV"


def test_format_video_as_article():
    collector = YoutubeCollector(api_key="test-key")
    video = {
        "video_id": "abc123",
        "title": "경제 전망 분석",
        "channel": "삼프로TV",
        "description": "이번 분기 경제 전망을 분석합니다.",
        "published_at": "2026-04-12T09:00:00Z",
    }
    article = collector.format_as_article(video, transcript="경제가 좋아지고 있습니다.")
    assert article["source"] == "삼프로TV"
    assert article["url"] == "https://www.youtube.com/watch?v=abc123"
    assert article["category"] == "youtube"
    assert "경제가 좋아지고 있습니다." in article["summary"]
