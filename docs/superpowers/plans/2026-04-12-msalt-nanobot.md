# msalt-nanobot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** nanobot 포크 위에 경제 뉴스 비서 + 생활 습관 관리 기능을 구축하여, 라즈베리파이 3B+에서 텔레그램으로 서비스한다.

**Architecture:** nanobot의 기존 인프라(텔레그램 채널, 에이전트 루프, 크론, 메모리)를 그대로 활용하고, `msalt/` 디렉토리에 뉴스 수집기와 생활 습관 트래커를 격리된 Python 모듈로 구현한다. nanobot 스킬(SKILL.md)을 통해 에이전트가 msalt 모듈을 호출하고, 크론으로 정기 브리핑을 스케줄링한다.

**Tech Stack:** Python 3.11+, nanobot (포크), OpenAI GPT (gpt-4o-mini), python-telegram-bot, feedparser (RSS), SQLite, croniter

**Spec:** [docs/superpowers/specs/2026-04-12-msalt-nanobot-design.md](../specs/2026-04-12-msalt-nanobot-design.md)

---

## Phase 1: 인프라 (텔레그램 + 라즈베리파이)

### Task 1: msalt/ 디렉토리 구조 초기화

**Files:**
- Create: `msalt/__init__.py`
- Create: `msalt/config.py`
- Create: `msalt/news/__init__.py`
- Create: `msalt/lifestyle/__init__.py`
- Create: `tests/msalt/__init__.py`
- Create: `tests/msalt/test_config.py`

- [ ] **Step 1: Write the failing test for msalt config**

```python
# tests/msalt/__init__.py
# (empty)
```

```python
# tests/msalt/test_config.py
from msalt.config import MsaltConfig


def test_default_config():
    config = MsaltConfig()
    assert config.timezone == "Asia/Seoul"
    assert config.news_sources_path == "msalt/news/sources.json"
    assert config.db_path == "msalt/data/msalt.db"
    assert config.briefing_morning == "07:00"
    assert config.briefing_evening == "19:00"


def test_custom_config():
    config = MsaltConfig(timezone="UTC", briefing_morning="08:00")
    assert config.timezone == "UTC"
    assert config.briefing_morning == "08:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/msalt/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'msalt'`

- [ ] **Step 3: Write minimal implementation**

```python
# msalt/__init__.py
# (empty)
```

```python
# msalt/news/__init__.py
# (empty)
```

```python
# msalt/lifestyle/__init__.py
# (empty)
```

```python
# msalt/config.py
from dataclasses import dataclass, field


@dataclass
class MsaltConfig:
    """msalt-nanobot 전용 설정."""
    timezone: str = "Asia/Seoul"
    news_sources_path: str = "msalt/news/sources.json"
    db_path: str = "msalt/data/msalt.db"
    briefing_morning: str = "07:00"
    briefing_evening: str = "19:00"
    collect_before_min: int = 30  # 브리핑 전 수집 시작 (분)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/msalt/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add msalt/ tests/msalt/
git commit -m "feat(msalt): initialize msalt directory structure and config"
```

---

### Task 2: nanobot config 설정 파일 생성

**Files:**
- Create: `msalt/nanobot-config.example.json`
- Create: `docs/msalt-setup.md`

- [ ] **Step 1: Create example nanobot config for msalt**

nanobot config는 `~/.nanobot/config.json`에 위치한다. 라즈베리파이용 경량 설정 예시를 만든다.

```json
{
  "agents": {
    "defaults": {
      "model": "gpt-4o-mini",
      "workspace": "~/.nanobot/workspace",
      "maxTokens": 4096,
      "contextWindowTokens": 16000,
      "maxToolIterations": 50,
      "timezone": "Asia/Seoul",
      "dream": {
        "intervalH": 12,
        "maxBatchSize": 10,
        "maxIterations": 5
      }
    }
  },
  "providers": {
    "openai": {
      "apiKey": "${OPENAI_API_KEY}"
    }
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "${TELEGRAM_BOT_TOKEN}",
      "allowFrom": ["YOUR_TELEGRAM_USER_ID"]
    },
    "sendProgress": false,
    "sendToolHints": false,
    "sendMaxRetries": 2
  },
  "tools": {
    "web": {
      "enable": true,
      "search": {
        "provider": "duckduckgo"
      }
    },
    "exec": {
      "enable": true,
      "timeout": 30
    }
  }
}
```

- [ ] **Step 2: Create setup guide**

```markdown
# msalt-nanobot 설정 가이드

## 사전 준비

1. Telegram Bot Token: @BotFather에서 봇 생성 후 토큰 획득
2. OpenAI API Key: https://platform.openai.com 에서 발급
3. Telegram User ID: @userinfobot 에서 확인

## 환경 변수 설정

```bash
export OPENAI_API_KEY="sk-..."
export TELEGRAM_BOT_TOKEN="123456:ABC-..."
```

## nanobot config 설정

```bash
# config 예시 복사
cp msalt/nanobot-config.example.json ~/.nanobot/config.json

# allowFrom에 본인 Telegram User ID 입력
# 편집: nano ~/.nanobot/config.json
```

## 실행

```bash
# 개발 환경
pip install -e .
nanobot gateway

# 라즈베리파이 (systemd)
# docs/msalt-rpi-deploy.md 참고
```
```

- [ ] **Step 3: Commit**

```bash
git add msalt/nanobot-config.example.json docs/msalt-setup.md
git commit -m "docs(msalt): add nanobot config example and setup guide"
```

---

### Task 3: 라즈베리파이 배포 가이드 및 systemd 서비스

**Files:**
- Create: `deploy/msalt-nanobot.service`
- Create: `deploy/setup-rpi.sh`
- Create: `docs/msalt-rpi-deploy.md`

- [ ] **Step 1: Create systemd service file**

```ini
# deploy/msalt-nanobot.service
[Unit]
Description=msalt-nanobot AI Assistant
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/msalt-nanobot
EnvironmentFile=/home/pi/msalt-nanobot/.env
ExecStart=/home/pi/msalt-nanobot/.venv/bin/nanobot gateway
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create RPi setup script**

```bash
#!/usr/bin/env bash
# deploy/setup-rpi.sh
# Raspberry Pi 3B+ 환경 설정 스크립트
set -euo pipefail

echo "=== msalt-nanobot RPi Setup ==="

# 1. swap 설정 (1GB)
echo "Setting up 1GB swap..."
sudo dphys-swapfile swapoff || true
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# 2. Python 3.11+ 설치
echo "Installing Python 3.11..."
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev

# 3. 프로젝트 설정
echo "Setting up project..."
cd /home/pi/msalt-nanobot
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .

# 4. .env 파일 생성 (사용자가 직접 편집)
if [ ! -f .env ]; then
    cat > .env << 'ENVEOF'
OPENAI_API_KEY=sk-your-key-here
TELEGRAM_BOT_TOKEN=your-bot-token-here
ENVEOF
    echo "Created .env file — edit with your API keys!"
fi

# 5. systemd 서비스 등록
echo "Installing systemd service..."
sudo cp deploy/msalt-nanobot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable msalt-nanobot

echo "=== Setup complete! ==="
echo "1. Edit .env with your API keys"
echo "2. Edit ~/.nanobot/config.json (see msalt/nanobot-config.example.json)"
echo "3. Start: sudo systemctl start msalt-nanobot"
echo "4. Logs: journalctl -u msalt-nanobot -f"
```

- [ ] **Step 3: Create deployment guide**

배포 가이드 문서를 `docs/msalt-rpi-deploy.md`에 작성한다. 내용:
- 라즈베리파이 3B+ 요구사항 (Raspberry Pi OS Lite, Python 3.11+)
- Git clone 및 setup-rpi.sh 실행 절차
- .env 및 config.json 설정 방법
- systemd 서비스 관리 명령어 (start, stop, status, logs)
- 메모리 모니터링 팁 (`free -h`, `htop`)
- 트러블슈팅 (swap 부족, API 키 오류, 텔레그램 연결 실패)

- [ ] **Step 4: Commit**

```bash
git add deploy/ docs/msalt-rpi-deploy.md
git commit -m "feat(deploy): add RPi systemd service and setup script"
```

---

## Phase 2: 경제 뉴스 비서

### Task 4: SQLite 저장소 기반 모듈

**Files:**
- Create: `msalt/storage.py`
- Create: `tests/msalt/test_storage.py`

- [ ] **Step 1: Write the failing tests for storage**

```python
# tests/msalt/test_storage.py
import sqlite3
from pathlib import Path

import pytest

from msalt.storage import Storage


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    storage = Storage(str(db_path))
    storage.initialize()
    return storage


def test_initialize_creates_tables(db):
    conn = sqlite3.connect(db.db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    assert "news_articles" in tables
    assert "sleep_log" in tables
    assert "todos" in tables
    assert "life_log" in tables


def test_insert_and_get_article(db):
    db.insert_article(
        source="hankyung",
        title="테스트 기사",
        url="https://example.com/1",
        summary="요약 내용",
        category="domestic",
    )
    articles = db.get_articles_since("2020-01-01")
    assert len(articles) == 1
    assert articles[0]["title"] == "테스트 기사"
    assert articles[0]["source"] == "hankyung"


def test_duplicate_url_ignored(db):
    db.insert_article("src", "제목1", "https://example.com/1", "요약1", "domestic")
    db.insert_article("src", "제목2", "https://example.com/1", "요약2", "domestic")
    articles = db.get_articles_since("2020-01-01")
    assert len(articles) == 1


def test_get_articles_since_filters_by_date(db):
    db.insert_article("src", "오래된", "https://old.com", "old", "domestic")
    articles = db.get_articles_since("2099-01-01")
    assert len(articles) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/msalt/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'msalt.storage'`

- [ ] **Step 3: Write minimal implementation**

```python
# msalt/storage.py
import sqlite3
from datetime import datetime, timezone


class Storage:
    """msalt-nanobot SQLite 저장소."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def initialize(self):
        """모든 테이블을 생성한다."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                summary TEXT,
                category TEXT,
                collected_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sleep_log (
                date TEXT PRIMARY KEY,
                bedtime TEXT,
                wakeup TEXT,
                duration_min INTEGER,
                quality TEXT
            );

            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                due_at TEXT,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS life_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                raw_text TEXT NOT NULL,
                category TEXT,
                parsed_data TEXT
            );
        """)
        conn.commit()
        conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def insert_article(self, source: str, title: str, url: str, summary: str, category: str):
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO news_articles (source, title, url, summary, category) "
                "VALUES (?, ?, ?, ?, ?)",
                (source, title, url, summary, category),
            )
            conn.commit()
        finally:
            conn.close()

    def get_articles_since(self, since_date: str) -> list[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM news_articles WHERE collected_at >= ? ORDER BY collected_at DESC",
                (since_date,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/msalt/test_storage.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add msalt/storage.py tests/msalt/test_storage.py
git commit -m "feat(msalt): add SQLite storage module with news_articles table"
```

---

### Task 5: RSS 뉴스 수집기

**Files:**
- Create: `msalt/news/sources.json`
- Create: `msalt/news/rss.py`
- Create: `tests/msalt/news/__init__.py`
- Create: `tests/msalt/news/test_rss.py`

- [ ] **Step 1: Create sources.json**

```json
{
  "rss": [
    {
      "name": "한국경제",
      "url": "https://www.hankyung.com/feed/economy",
      "category": "domestic"
    },
    {
      "name": "매일경제",
      "url": "https://www.mk.co.kr/rss/30100041/",
      "category": "domestic"
    },
    {
      "name": "조선비즈",
      "url": "https://biz.chosun.com/svc/rss/www/rss.xml",
      "category": "domestic"
    },
    {
      "name": "Reuters Business",
      "url": "https://www.reutersagency.com/feed/?best-topics=business-finance",
      "category": "international"
    },
    {
      "name": "CNBC Top News",
      "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
      "category": "international"
    }
  ],
  "youtube": []
}
```

- [ ] **Step 2: Write the failing tests for RSS collector**

```python
# tests/msalt/news/__init__.py
# (empty)
```

```python
# tests/msalt/news/test_rss.py
from unittest.mock import patch, MagicMock

import pytest

from msalt.news.rss import RssCollector


MOCK_FEED = MagicMock()
MOCK_FEED.bozo = False
MOCK_FEED.entries = [
    MagicMock(
        title="경제 성장률 전망",
        link="https://example.com/article1",
        get=lambda key, default="": {
            "summary": "2분기 경제 성장률이 상승할 것으로 전망된다.",
            "published": "Sat, 12 Apr 2026 09:00:00 GMT",
        }.get(key, default),
    ),
    MagicMock(
        title="금리 동결 결정",
        link="https://example.com/article2",
        get=lambda key, default="": {
            "summary": "한국은행이 기준금리를 동결했다.",
            "published": "Sat, 12 Apr 2026 10:00:00 GMT",
        }.get(key, default),
    ),
]


@patch("msalt.news.rss.feedparser.parse", return_value=MOCK_FEED)
def test_collect_from_source(mock_parse):
    collector = RssCollector()
    source = {"name": "테스트", "url": "https://example.com/feed", "category": "domestic"}
    articles = collector.collect_from_source(source)
    assert len(articles) == 2
    assert articles[0]["title"] == "경제 성장률 전망"
    assert articles[0]["url"] == "https://example.com/article1"
    assert articles[0]["source"] == "테스트"
    assert articles[0]["category"] == "domestic"


@patch("msalt.news.rss.feedparser.parse")
def test_collect_from_source_handles_bozo(mock_parse):
    bad_feed = MagicMock()
    bad_feed.bozo = True
    bad_feed.entries = []
    mock_parse.return_value = bad_feed
    collector = RssCollector()
    source = {"name": "Bad", "url": "https://bad.com/feed", "category": "domestic"}
    articles = collector.collect_from_source(source)
    assert articles == []


def test_load_sources(tmp_path):
    import json

    sources_file = tmp_path / "sources.json"
    sources_file.write_text(json.dumps({
        "rss": [{"name": "Test", "url": "https://test.com/rss", "category": "domestic"}],
        "youtube": [],
    }))
    collector = RssCollector(sources_path=str(sources_file))
    sources = collector.load_sources()
    assert len(sources) == 1
    assert sources[0]["name"] == "Test"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/msalt/news/test_rss.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'msalt.news.rss'`

- [ ] **Step 4: Add feedparser dependency**

`pyproject.toml`의 `[project.dependencies]`에 `feedparser>=6.0.0,<7.0.0` 추가 후:

Run: `pip install -e .`

- [ ] **Step 5: Write minimal implementation**

```python
# msalt/news/rss.py
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
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/msalt/news/test_rss.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add msalt/news/rss.py msalt/news/sources.json tests/msalt/news/ pyproject.toml
git commit -m "feat(news): add RSS news collector with source configuration"
```

---

### Task 6: YouTube 수집기

**Files:**
- Create: `msalt/news/youtube.py`
- Create: `tests/msalt/news/test_youtube.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/msalt/news/test_youtube.py
from unittest.mock import patch, MagicMock, AsyncMock

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

MOCK_CAPTIONS_RESPONSE = {
    "items": [
        {"snippet": {"language": "ko"}, "id": "cap1"}
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/msalt/news/test_youtube.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# msalt/news/youtube.py
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
            # 자막 다운로드는 OAuth가 필요하므로, 설명만 사용하거나
            # youtube-transcript-api 패키지로 대체 가능
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/msalt/news/test_youtube.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add msalt/news/youtube.py tests/msalt/news/test_youtube.py
git commit -m "feat(news): add YouTube video collector"
```

---

### Task 7: 뉴스 수집 오케스트레이터

**Files:**
- Create: `msalt/news/collector.py`
- Create: `tests/msalt/news/test_collector.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/msalt/news/test_collector.py
from unittest.mock import MagicMock, patch

import pytest

from msalt.news.collector import NewsCollector


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get_articles_since.return_value = []
    return storage


@patch("msalt.news.collector.RssCollector")
def test_collect_all_stores_articles(MockRss, mock_storage):
    mock_rss = MockRss.return_value
    mock_rss.collect_all.return_value = [
        {
            "source": "한경",
            "title": "테스트 기사",
            "url": "https://example.com/1",
            "summary": "요약",
            "category": "domestic",
            "published": "2026-04-12",
        }
    ]

    collector = NewsCollector(storage=mock_storage, sources_path="dummy.json")
    count = collector.collect()
    assert count == 1
    mock_storage.insert_article.assert_called_once_with(
        source="한경",
        title="테스트 기사",
        url="https://example.com/1",
        summary="요약",
        category="domestic",
    )


@patch("msalt.news.collector.RssCollector")
def test_collect_returns_count(MockRss, mock_storage):
    mock_rss = MockRss.return_value
    mock_rss.collect_all.return_value = [
        {"source": "a", "title": "t1", "url": "https://1.com", "summary": "s", "category": "domestic", "published": ""},
        {"source": "b", "title": "t2", "url": "https://2.com", "summary": "s", "category": "international", "published": ""},
    ]

    collector = NewsCollector(storage=mock_storage, sources_path="dummy.json")
    count = collector.collect()
    assert count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/msalt/news/test_collector.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# msalt/news/collector.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/msalt/news/test_collector.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add msalt/news/collector.py tests/msalt/news/test_collector.py
git commit -m "feat(news): add news collector orchestrator"
```

---

### Task 8: 브리핑 생성기

**Files:**
- Create: `msalt/news/briefing.py`
- Create: `tests/msalt/news/test_briefing.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/msalt/news/test_briefing.py
from unittest.mock import MagicMock

import pytest

from msalt.news.briefing import BriefingGenerator


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get_articles_since.return_value = [
        {"source": "한경", "title": "경제 성장률 상승", "url": "https://hk.com/1", "summary": "2분기 성장률 전망", "category": "domestic", "collected_at": "2026-04-12 07:00:00"},
        {"source": "Reuters", "title": "Fed holds rates", "url": "https://reuters.com/1", "summary": "Federal Reserve holds interest rates", "category": "international", "collected_at": "2026-04-12 07:00:00"},
        {"source": "삼프로TV", "title": "시장 분석", "url": "https://youtube.com/watch?v=abc", "summary": "이번 주 시장 분석", "category": "youtube", "collected_at": "2026-04-12 07:00:00"},
    ]
    return storage


def test_format_briefing(mock_storage):
    gen = BriefingGenerator(storage=mock_storage)
    text = gen.format_briefing("morning")
    assert "아침 경제 브리핑" in text
    assert "국내" in text
    assert "해외" in text
    assert "유튜브" in text
    assert "경제 성장률 상승" in text
    assert "Fed holds rates" in text
    assert "시장 분석" in text


def test_format_briefing_empty(mock_storage):
    mock_storage.get_articles_since.return_value = []
    gen = BriefingGenerator(storage=mock_storage)
    text = gen.format_briefing("morning")
    assert "수집된 뉴스가 없습니다" in text


def test_get_articles_for_briefing_deduplicates(mock_storage):
    mock_storage.get_articles_since.return_value = [
        {"source": "한경", "title": "같은 기사", "url": "https://same.com", "summary": "a", "category": "domestic", "collected_at": "2026-04-12"},
        {"source": "매경", "title": "같은 기사", "url": "https://same.com", "summary": "b", "category": "domestic", "collected_at": "2026-04-12"},
    ]
    gen = BriefingGenerator(storage=mock_storage)
    articles = gen.get_articles_for_briefing()
    assert len(articles) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/msalt/news/test_briefing.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# msalt/news/briefing.py
from datetime import datetime, timedelta

from msalt.storage import Storage


class BriefingGenerator:
    """수집된 뉴스를 브리핑 텍스트로 포맷한다."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def get_articles_for_briefing(self, hours: int = 12) -> list[dict]:
        since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        articles = self.storage.get_articles_since(since)
        # URL 기반 중복 제거
        seen_urls = set()
        unique = []
        for article in articles:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                unique.append(article)
        return unique

    def format_briefing(self, time_of_day: str = "morning") -> str:
        articles = self.get_articles_for_briefing()

        if not articles:
            label = "아침" if time_of_day == "morning" else "저녁"
            return f"{label} 경제 브리핑 — 수집된 뉴스가 없습니다."

        today = datetime.now().strftime("%Y-%m-%d")
        label = "아침" if time_of_day == "morning" else "저녁"

        domestic = [a for a in articles if a["category"] == "domestic"]
        international = [a for a in articles if a["category"] == "international"]
        youtube = [a for a in articles if a["category"] == "youtube"]

        lines = [f"{label} 경제 브리핑 ({today})", ""]

        if domestic:
            lines.append("[국내]")
            for i, a in enumerate(domestic, 1):
                lines.append(f"{i}. {a['title']}")
                if a.get("summary"):
                    lines.append(f"   {a['summary'][:200]}")
                lines.append(f"   원문: {a['url']}")
                lines.append("")

        if international:
            lines.append("[해외]")
            for i, a in enumerate(international, 1):
                lines.append(f"{i}. {a['title']}")
                if a.get("summary"):
                    lines.append(f"   {a['summary'][:200]}")
                lines.append(f"   원문: {a['url']}")
                lines.append("")

        if youtube:
            lines.append("[유튜브]")
            for i, a in enumerate(youtube, 1):
                lines.append(f"{i}. [{a['source']}] {a['title']}")
                if a.get("summary"):
                    lines.append(f"   {a['summary'][:200]}")
                lines.append(f"   링크: {a['url']}")
                lines.append("")

        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/msalt/news/test_briefing.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add msalt/news/briefing.py tests/msalt/news/test_briefing.py
git commit -m "feat(news): add briefing generator with dedup and formatting"
```

---

### Task 9: 뉴스 nanobot 스킬 (SKILL.md)

**Files:**
- Create: `msalt/skills/news/SKILL.md`
- Create: `msalt/skills/news-briefing/SKILL.md`

- [ ] **Step 1: Create news skill for on-demand queries**

이 스킬은 사용자가 텔레그램에서 "오늘 뉴스", "삼성전자 뉴스" 같은 요청을 할 때 에이전트가 사용한다.

```markdown
---
name: news
description: 경제 뉴스를 검색하고 요약합니다. 사용자가 뉴스, 경제, 시장 관련 질문을 할 때 사용하세요.
---

# 뉴스 검색 스킬

사용자가 뉴스나 경제 관련 질문을 하면 shell 도구로 msalt 뉴스 모듈을 실행하세요.

## 최신 뉴스 브리핑 요청 시

```bash
python -m msalt.news.cli briefing
```

## 키워드로 뉴스 검색 시

```bash
python -m msalt.news.cli search "키워드"
```

## 뉴스 수집 실행 (수동)

```bash
python -m msalt.news.cli collect
```

## 응답 가이드

- 결과를 한국어로 자연스럽게 요약해서 전달하세요
- 원문 링크를 반드시 포함하세요
- 중복 기사는 하나로 합쳐서 전달하세요
```

- [ ] **Step 2: Create news-briefing skill for scheduled briefings**

이 스킬은 크론에 의해 자동 실행되는 브리핑용이다.

```markdown
---
name: news-briefing
description: 정기 경제 뉴스 브리핑을 생성합니다. 크론 스케줄러가 사용합니다.
metadata: {"always": false}
---

# 정기 뉴스 브리핑

크론 스케줄러에 의해 실행됩니다. 다음 단계를 수행하세요:

1. 뉴스 수집 실행:
```bash
python -m msalt.news.cli collect
```

2. 브리핑 생성:
```bash
python -m msalt.news.cli briefing
```

3. 결과를 사용자에게 전달하세요.
```

- [ ] **Step 3: Commit**

```bash
git add msalt/skills/
git commit -m "feat(skills): add news and news-briefing nanobot skills"
```

---

### Task 10: 뉴스 CLI 엔트리포인트

**Files:**
- Create: `msalt/news/cli.py`
- Create: `tests/msalt/news/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/msalt/news/test_cli.py
from unittest.mock import patch, MagicMock
from io import StringIO

import pytest

from msalt.news.cli import run_collect, run_briefing, run_search


@patch("msalt.news.cli.NewsCollector")
@patch("msalt.news.cli.Storage")
def test_run_collect(MockStorage, MockCollector):
    mock_storage = MockStorage.return_value
    mock_collector = MockCollector.return_value
    mock_collector.collect.return_value = 5

    result = run_collect()
    assert "5" in result
    mock_storage.initialize.assert_called_once()
    mock_collector.collect.assert_called_once()


@patch("msalt.news.cli.BriefingGenerator")
@patch("msalt.news.cli.Storage")
def test_run_briefing(MockStorage, MockGenerator):
    mock_gen = MockGenerator.return_value
    mock_gen.format_briefing.return_value = "아침 경제 브리핑 (2026-04-12)\n..."

    result = run_briefing("morning")
    assert "아침 경제 브리핑" in result


@patch("msalt.news.cli.Storage")
def test_run_search(MockStorage):
    mock_storage = MockStorage.return_value
    mock_storage.get_articles_since.return_value = [
        {"title": "삼성전자 실적", "url": "https://example.com/1", "summary": "s", "source": "한경", "category": "domestic", "collected_at": "2026-04-12"},
        {"title": "LG 실적", "url": "https://example.com/2", "summary": "s", "source": "매경", "category": "domestic", "collected_at": "2026-04-12"},
    ]
    mock_storage.initialize.return_value = None

    result = run_search("삼성전자")
    assert "삼성전자 실적" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/msalt/news/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# msalt/news/cli.py
"""msalt 뉴스 CLI — 스킬과 크론에서 호출하는 엔트리포인트."""
import sys

from msalt.config import MsaltConfig
from msalt.storage import Storage
from msalt.news.collector import NewsCollector
from msalt.news.briefing import BriefingGenerator


def _get_storage() -> Storage:
    config = MsaltConfig()
    storage = Storage(config.db_path)
    storage.initialize()
    return storage


def run_collect() -> str:
    storage = _get_storage()
    collector = NewsCollector(storage=storage)
    count = collector.collect()
    return f"뉴스 수집 완료: {count}건"


def run_briefing(time_of_day: str = "morning") -> str:
    storage = _get_storage()
    gen = BriefingGenerator(storage=storage)
    return gen.format_briefing(time_of_day)


def run_search(keyword: str) -> str:
    storage = _get_storage()
    articles = storage.get_articles_since("2020-01-01")
    matched = [a for a in articles if keyword.lower() in a["title"].lower()
               or keyword.lower() in a.get("summary", "").lower()]
    if not matched:
        return f"'{keyword}' 관련 뉴스를 찾을 수 없습니다."

    lines = [f"'{keyword}' 관련 뉴스 ({len(matched)}건)", ""]
    for i, a in enumerate(matched, 1):
        lines.append(f"{i}. [{a['source']}] {a['title']}")
        lines.append(f"   원문: {a['url']}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m msalt.news.cli [collect|briefing|search <keyword>]")
        sys.exit(1)

    command = sys.argv[1]
    if command == "collect":
        print(run_collect())
    elif command == "briefing":
        time = sys.argv[2] if len(sys.argv) > 2 else "morning"
        print(run_briefing(time))
    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: python -m msalt.news.cli search <keyword>")
            sys.exit(1)
        print(run_search(sys.argv[2]))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/msalt/news/test_cli.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add msalt/news/cli.py tests/msalt/news/test_cli.py
git commit -m "feat(news): add CLI entry point for collect, briefing, search"
```

---

## Phase 3: 생활 습관 관리

### Task 11: 수면 기록 저장/조회

**Files:**
- Create: `msalt/lifestyle/sleep.py`
- Create: `tests/msalt/lifestyle/__init__.py`
- Create: `tests/msalt/lifestyle/test_sleep.py`
- Modify: `msalt/storage.py` (add sleep-specific methods)

- [ ] **Step 1: Write the failing tests for storage sleep methods**

```python
# tests/msalt/lifestyle/__init__.py
# (empty)
```

```python
# tests/msalt/lifestyle/test_sleep.py
import pytest

from msalt.storage import Storage
from msalt.lifestyle.sleep import SleepTracker


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    s = Storage(str(db_path))
    s.initialize()
    return s


def test_record_sleep(storage):
    tracker = SleepTracker(storage)
    tracker.record("2026-04-11", bedtime="23:00", wakeup="06:30", duration_min=450)
    log = storage.get_sleep_log("2026-04-11")
    assert log is not None
    assert log["bedtime"] == "23:00"
    assert log["wakeup"] == "06:30"
    assert log["duration_min"] == 450


def test_record_sleep_overwrites_same_date(storage):
    tracker = SleepTracker(storage)
    tracker.record("2026-04-11", bedtime="23:00", wakeup="06:30", duration_min=450)
    tracker.record("2026-04-11", bedtime="00:00", wakeup="07:00", duration_min=420)
    log = storage.get_sleep_log("2026-04-11")
    assert log["bedtime"] == "00:00"


def test_get_weekly_stats(storage):
    tracker = SleepTracker(storage)
    tracker.record("2026-04-07", bedtime="23:00", wakeup="06:00", duration_min=420)
    tracker.record("2026-04-08", bedtime="23:30", wakeup="06:30", duration_min=420)
    tracker.record("2026-04-09", bedtime="22:00", wakeup="06:00", duration_min=480)

    stats = tracker.get_stats(days=7)
    assert stats["count"] == 3
    assert stats["avg_duration_min"] == 440
    assert stats["min_duration_min"] == 420
    assert stats["max_duration_min"] == 480
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/msalt/lifestyle/test_sleep.py -v`
Expected: FAIL

- [ ] **Step 3: Add sleep methods to Storage**

`msalt/storage.py`에 다음 메서드를 추가:

```python
def upsert_sleep(self, date: str, bedtime: str, wakeup: str,
                 duration_min: int, quality: str | None = None):
    conn = self._connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO sleep_log (date, bedtime, wakeup, duration_min, quality) "
            "VALUES (?, ?, ?, ?, ?)",
            (date, bedtime, wakeup, duration_min, quality),
        )
        conn.commit()
    finally:
        conn.close()

def get_sleep_log(self, date: str) -> dict | None:
    conn = self._connect()
    try:
        cursor = conn.execute("SELECT * FROM sleep_log WHERE date = ?", (date,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_sleep_logs_since(self, since_date: str) -> list[dict]:
    conn = self._connect()
    try:
        cursor = conn.execute(
            "SELECT * FROM sleep_log WHERE date >= ? ORDER BY date DESC",
            (since_date,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
```

- [ ] **Step 4: Write SleepTracker implementation**

```python
# msalt/lifestyle/sleep.py
from datetime import datetime, timedelta

from msalt.storage import Storage


class SleepTracker:
    """수면 기록을 관리한다."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def record(self, date: str, bedtime: str, wakeup: str,
               duration_min: int, quality: str | None = None):
        self.storage.upsert_sleep(date, bedtime, wakeup, duration_min, quality)

    def get_stats(self, days: int = 7) -> dict:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        logs = self.storage.get_sleep_logs_since(since)
        if not logs:
            return {"count": 0, "avg_duration_min": 0, "min_duration_min": 0, "max_duration_min": 0}

        durations = [log["duration_min"] for log in logs]
        return {
            "count": len(logs),
            "avg_duration_min": round(sum(durations) / len(durations)),
            "min_duration_min": min(durations),
            "max_duration_min": max(durations),
        }

    def format_stats(self, days: int = 7) -> str:
        stats = self.get_stats(days)
        if stats["count"] == 0:
            return f"최근 {days}일간 수면 기록이 없습니다."

        return (
            f"최근 {days}일 수면 통계 ({stats['count']}건)\n"
            f"  평균: {stats['avg_duration_min']}분 ({stats['avg_duration_min'] // 60}시간 {stats['avg_duration_min'] % 60}분)\n"
            f"  최소: {stats['min_duration_min']}분\n"
            f"  최대: {stats['max_duration_min']}분"
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/msalt/lifestyle/test_sleep.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add msalt/storage.py msalt/lifestyle/sleep.py tests/msalt/lifestyle/
git commit -m "feat(lifestyle): add sleep tracker with stats"
```

---

### Task 12: 할일 관리

**Files:**
- Create: `msalt/lifestyle/todo.py`
- Create: `tests/msalt/lifestyle/test_todo.py`
- Modify: `msalt/storage.py` (add todo methods)

- [ ] **Step 1: Write the failing tests**

```python
# tests/msalt/lifestyle/test_todo.py
import pytest

from msalt.storage import Storage
from msalt.lifestyle.todo import TodoManager


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    s = Storage(str(db_path))
    s.initialize()
    return s


def test_add_todo(storage):
    manager = TodoManager(storage)
    todo_id = manager.add("장보기")
    assert todo_id is not None
    todos = manager.list_pending()
    assert len(todos) == 1
    assert todos[0]["content"] == "장보기"
    assert todos[0]["status"] == "pending"


def test_add_todo_with_due(storage):
    manager = TodoManager(storage)
    manager.add("치과 예약", due_at="2026-04-13 15:00")
    todos = manager.list_pending()
    assert todos[0]["due_at"] == "2026-04-13 15:00"


def test_complete_todo(storage):
    manager = TodoManager(storage)
    todo_id = manager.add("장보기")
    manager.complete(todo_id)
    pending = manager.list_pending()
    assert len(pending) == 0


def test_list_pending_excludes_done(storage):
    manager = TodoManager(storage)
    id1 = manager.add("할일 1")
    id2 = manager.add("할일 2")
    manager.complete(id1)
    pending = manager.list_pending()
    assert len(pending) == 1
    assert pending[0]["content"] == "할일 2"


def test_get_due_soon(storage):
    manager = TodoManager(storage)
    manager.add("곧 할일", due_at="2026-04-12 15:00")
    manager.add("나중 할일", due_at="2099-12-31 23:59")
    due = manager.get_due_soon(before="2026-04-12 16:00")
    assert len(due) == 1
    assert due[0]["content"] == "곧 할일"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/msalt/lifestyle/test_todo.py -v`
Expected: FAIL

- [ ] **Step 3: Add todo methods to Storage**

`msalt/storage.py`에 다음 메서드를 추가:

```python
def insert_todo(self, content: str, due_at: str | None = None) -> int:
    conn = self._connect()
    try:
        cursor = conn.execute(
            "INSERT INTO todos (content, due_at, status) VALUES (?, ?, 'pending')",
            (content, due_at),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def complete_todo(self, todo_id: int):
    conn = self._connect()
    try:
        conn.execute(
            "UPDATE todos SET status='done', completed_at=datetime('now') WHERE id=?",
            (todo_id,),
        )
        conn.commit()
    finally:
        conn.close()

def get_pending_todos(self) -> list[dict]:
    conn = self._connect()
    try:
        cursor = conn.execute(
            "SELECT * FROM todos WHERE status='pending' ORDER BY due_at ASC NULLS LAST"
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_todos_due_before(self, before: str) -> list[dict]:
    conn = self._connect()
    try:
        cursor = conn.execute(
            "SELECT * FROM todos WHERE status='pending' AND due_at IS NOT NULL AND due_at <= ? "
            "ORDER BY due_at ASC",
            (before,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
```

- [ ] **Step 4: Write TodoManager implementation**

```python
# msalt/lifestyle/todo.py
from msalt.storage import Storage


class TodoManager:
    """할일을 관리한다."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def add(self, content: str, due_at: str | None = None) -> int:
        return self.storage.insert_todo(content, due_at)

    def complete(self, todo_id: int):
        self.storage.complete_todo(todo_id)

    def list_pending(self) -> list[dict]:
        return self.storage.get_pending_todos()

    def get_due_soon(self, before: str) -> list[dict]:
        return self.storage.get_todos_due_before(before)

    def format_list(self) -> str:
        todos = self.list_pending()
        if not todos:
            return "미완료 할일이 없습니다."

        lines = [f"할일 목록 ({len(todos)}건)", ""]
        for t in todos:
            due = f" (기한: {t['due_at']})" if t["due_at"] else ""
            lines.append(f"  [{t['id']}] {t['content']}{due}")
        return "\n".join(lines)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/msalt/lifestyle/test_todo.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add msalt/storage.py msalt/lifestyle/todo.py tests/msalt/lifestyle/test_todo.py
git commit -m "feat(lifestyle): add todo manager"
```

---

### Task 13: 자유 텍스트 기록 + 자동 분류

**Files:**
- Create: `msalt/lifestyle/classifier.py`
- Create: `msalt/lifestyle/tracker.py`
- Create: `tests/msalt/lifestyle/test_classifier.py`
- Create: `tests/msalt/lifestyle/test_tracker.py`
- Modify: `msalt/storage.py` (add life_log methods)

- [ ] **Step 1: Write the failing tests for classifier**

```python
# tests/msalt/lifestyle/test_classifier.py
import pytest

from msalt.lifestyle.classifier import classify_text


def test_classify_exercise():
    result = classify_text("오늘 5km 달림")
    assert result["category"] == "exercise"
    assert "5km" in result["parsed_data"]["detail"]


def test_classify_food():
    result = classify_text("커피 3잔 마심")
    assert result["category"] == "food"


def test_classify_health():
    result = classify_text("두통약 먹음")
    assert result["category"] == "health"


def test_classify_mood():
    result = classify_text("기분 좋음")
    assert result["category"] == "mood"


def test_classify_unknown():
    result = classify_text("아무 의미 없는 텍스트 qlwkejr")
    assert result["category"] == "other"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/msalt/lifestyle/test_classifier.py -v`
Expected: FAIL

- [ ] **Step 3: Write classifier implementation**

이 분류기는 간단한 키워드 기반으로 구현한다. 실제 서비스에서는 GPT를 통한 분류도 가능하지만, 오프라인에서도 동작하는 로컬 분류기를 기본으로 제공한다.

```python
# msalt/lifestyle/classifier.py
"""자유 텍스트를 카테고리로 분류한다.

키워드 기반 로컬 분류기. GPT를 통한 분류는 스킬 레이어에서 처리한다.
"""
import json
import re

CATEGORY_KEYWORDS = {
    "exercise": ["달리", "달림", "운동", "헬스", "수영", "자전거", "걸음", "산책", "스쿼트",
                  "푸시업", "플랭크", "요가", "등산", "km", "러닝"],
    "food": ["먹", "마심", "마셨", "식사", "아침", "점심", "저녁", "간식", "커피", "음식",
             "밥", "라면", "치킨", "피자", "샐러드"],
    "health": ["약", "병원", "두통", "감기", "열", "통증", "진료", "체중", "혈압",
               "컨디션", "피곤", "아프"],
    "mood": ["기분", "행복", "우울", "화남", "짜증", "좋음", "슬픔", "스트레스",
             "불안", "편안", "즐거"],
    "sleep": ["잠", "수면", "잤", "일어", "기상", "취침", "낮잠"],
}


def classify_text(text: str) -> dict:
    """텍스트를 카테고리로 분류하고, 파싱된 데이터를 반환한다."""
    text_lower = text.lower()

    best_category = "other"
    best_score = 0

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_category = category

    return {
        "category": best_category,
        "parsed_data": {"detail": text, "confidence": "keyword"},
    }
```

- [ ] **Step 4: Run classifier tests**

Run: `python -m pytest tests/msalt/lifestyle/test_classifier.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the failing tests for tracker**

```python
# tests/msalt/lifestyle/test_tracker.py
import pytest

from msalt.storage import Storage
from msalt.lifestyle.tracker import LifeTracker


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    s = Storage(str(db_path))
    s.initialize()
    return s


def test_log_entry(storage):
    tracker = LifeTracker(storage)
    entry_id = tracker.log("오늘 5km 달림")
    assert entry_id is not None
    entries = storage.get_life_logs_since("2020-01-01")
    assert len(entries) == 1
    assert entries[0]["raw_text"] == "오늘 5km 달림"
    assert entries[0]["category"] == "exercise"


def test_log_multiple_categories(storage):
    tracker = LifeTracker(storage)
    tracker.log("5km 달림")
    tracker.log("커피 3잔")
    tracker.log("기분 좋음")

    entries = storage.get_life_logs_since("2020-01-01")
    categories = {e["category"] for e in entries}
    assert "exercise" in categories
    assert "food" in categories
    assert "mood" in categories


def test_get_summary_by_category(storage):
    tracker = LifeTracker(storage)
    tracker.log("5km 달림")
    tracker.log("3km 달림")
    tracker.log("커피 마심")

    summary = tracker.get_summary_by_category(days=7)
    assert summary["exercise"] == 2
    assert summary["food"] == 1
```

- [ ] **Step 6: Add life_log methods to Storage**

`msalt/storage.py`에 다음 메서드를 추가:

```python
def insert_life_log(self, raw_text: str, category: str, parsed_data: str) -> int:
    conn = self._connect()
    try:
        cursor = conn.execute(
            "INSERT INTO life_log (raw_text, category, parsed_data) VALUES (?, ?, ?)",
            (raw_text, category, parsed_data),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def get_life_logs_since(self, since_date: str) -> list[dict]:
    conn = self._connect()
    try:
        cursor = conn.execute(
            "SELECT * FROM life_log WHERE timestamp >= ? ORDER BY timestamp DESC",
            (since_date,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_life_log_category_counts(self, since_date: str) -> dict[str, int]:
    conn = self._connect()
    try:
        cursor = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM life_log "
            "WHERE timestamp >= ? GROUP BY category",
            (since_date,),
        )
        return {row["category"]: row["cnt"] for row in cursor.fetchall()}
    finally:
        conn.close()
```

- [ ] **Step 7: Write LifeTracker implementation**

```python
# msalt/lifestyle/tracker.py
import json
from datetime import datetime, timedelta

from msalt.lifestyle.classifier import classify_text
from msalt.storage import Storage


class LifeTracker:
    """자유 텍스트 생활 기록을 관리한다."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def log(self, text: str) -> int:
        result = classify_text(text)
        return self.storage.insert_life_log(
            raw_text=text,
            category=result["category"],
            parsed_data=json.dumps(result["parsed_data"], ensure_ascii=False),
        )

    def get_summary_by_category(self, days: int = 7) -> dict[str, int]:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return self.storage.get_life_log_category_counts(since)

    def format_summary(self, days: int = 7) -> str:
        summary = self.get_summary_by_category(days)
        if not summary:
            return f"최근 {days}일간 생활 기록이 없습니다."

        category_labels = {
            "exercise": "운동",
            "food": "식단",
            "health": "건강",
            "mood": "감정",
            "sleep": "수면",
            "other": "기타",
        }

        lines = [f"최근 {days}일 생활 기록 요약", ""]
        for cat, count in sorted(summary.items()):
            label = category_labels.get(cat, cat)
            lines.append(f"  {label}: {count}건")
        return "\n".join(lines)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/msalt/lifestyle/test_classifier.py tests/msalt/lifestyle/test_tracker.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 9: Commit**

```bash
git add msalt/lifestyle/classifier.py msalt/lifestyle/tracker.py msalt/storage.py tests/msalt/lifestyle/
git commit -m "feat(lifestyle): add life tracker with keyword-based classifier"
```

---

### Task 14: 생활 습관 CLI + 스킬

**Files:**
- Create: `msalt/lifestyle/cli.py`
- Create: `msalt/skills/lifestyle/SKILL.md`
- Create: `tests/msalt/lifestyle/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/msalt/lifestyle/test_cli.py
from unittest.mock import patch, MagicMock

import pytest

from msalt.lifestyle.cli import run_sleep_record, run_sleep_stats, run_todo_add, run_todo_list, run_log


@patch("msalt.lifestyle.cli.Storage")
def test_run_sleep_record(MockStorage):
    mock_storage = MockStorage.return_value
    result = run_sleep_record("2026-04-11", "23:00", "06:30", 450)
    assert "수면 기록 완료" in result


@patch("msalt.lifestyle.cli.Storage")
def test_run_todo_add(MockStorage):
    mock_storage = MockStorage.return_value
    mock_storage.insert_todo.return_value = 1
    result = run_todo_add("장보기")
    assert "추가" in result


@patch("msalt.lifestyle.cli.Storage")
def test_run_log(MockStorage):
    mock_storage = MockStorage.return_value
    mock_storage.insert_life_log.return_value = 1
    result = run_log("오늘 5km 달림")
    assert "기록 완료" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/msalt/lifestyle/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Write CLI implementation**

```python
# msalt/lifestyle/cli.py
"""msalt 생활 습관 CLI — 스킬에서 호출하는 엔트리포인트."""
import sys

from msalt.config import MsaltConfig
from msalt.storage import Storage
from msalt.lifestyle.sleep import SleepTracker
from msalt.lifestyle.todo import TodoManager
from msalt.lifestyle.tracker import LifeTracker


def _get_storage() -> Storage:
    config = MsaltConfig()
    storage = Storage(config.db_path)
    storage.initialize()
    return storage


def run_sleep_record(date: str, bedtime: str, wakeup: str, duration_min: int) -> str:
    storage = _get_storage()
    tracker = SleepTracker(storage)
    tracker.record(date, bedtime, wakeup, duration_min)
    return f"수면 기록 완료: {date} ({duration_min}분)"


def run_sleep_stats(days: int = 7) -> str:
    storage = _get_storage()
    tracker = SleepTracker(storage)
    return tracker.format_stats(days)


def run_todo_add(content: str, due_at: str | None = None) -> str:
    storage = _get_storage()
    manager = TodoManager(storage)
    todo_id = manager.add(content, due_at)
    return f"할일 추가 (#{todo_id}): {content}"


def run_todo_list() -> str:
    storage = _get_storage()
    manager = TodoManager(storage)
    return manager.format_list()


def run_todo_complete(todo_id: int) -> str:
    storage = _get_storage()
    manager = TodoManager(storage)
    manager.complete(todo_id)
    return f"할일 #{todo_id} 완료"


def run_log(text: str) -> str:
    storage = _get_storage()
    tracker = LifeTracker(storage)
    entry_id = tracker.log(text)
    return f"기록 완료 (#{entry_id}): {text}"


def run_life_summary(days: int = 7) -> str:
    storage = _get_storage()
    tracker = LifeTracker(storage)
    return tracker.format_summary(days)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m msalt.lifestyle.cli [sleep-record|sleep-stats|todo-add|todo-list|todo-done|log|summary]")
        sys.exit(1)

    command = sys.argv[1]
    if command == "sleep-record":
        print(run_sleep_record(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])))
    elif command == "sleep-stats":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        print(run_sleep_stats(days))
    elif command == "todo-add":
        due = sys.argv[3] if len(sys.argv) > 3 else None
        print(run_todo_add(sys.argv[2], due))
    elif command == "todo-list":
        print(run_todo_list())
    elif command == "todo-done":
        print(run_todo_complete(int(sys.argv[2])))
    elif command == "log":
        print(run_log(" ".join(sys.argv[2:])))
    elif command == "summary":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        print(run_life_summary(days))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
```

- [ ] **Step 4: Create lifestyle skill**

```markdown
---
name: lifestyle
description: 생활 습관을 기록하고 통계를 제공합니다. 수면, 할일, 운동, 식단 등의 기록과 분석에 사용하세요.
---

# 생활 습관 관리 스킬

사용자가 생활 기록, 수면, 할일 관련 요청을 하면 shell 도구로 msalt 생활 습관 모듈을 실행하세요.

## 수면 기록

사용자가 수면에 대해 말하면 (예: "어젯밤 11시에 자서 6시에 일어남"), 날짜/취침/기상/수면시간을 파싱해서:

```bash
python -m msalt.lifestyle.cli sleep-record "2026-04-11" "23:00" "06:30" 450
```

## 수면 통계

```bash
python -m msalt.lifestyle.cli sleep-stats 7
```

## 할일 추가

```bash
python -m msalt.lifestyle.cli todo-add "장보기"
python -m msalt.lifestyle.cli todo-add "치과 예약" "2026-04-13 15:00"
```

## 할일 목록

```bash
python -m msalt.lifestyle.cli todo-list
```

## 할일 완료

```bash
python -m msalt.lifestyle.cli todo-done 1
```

## 자유 기록

사용자가 생활 관련 텍스트를 보내면 (운동, 식단, 건강, 감정 등):

```bash
python -m msalt.lifestyle.cli log "오늘 5km 달림"
```

## 생활 요약

```bash
python -m msalt.lifestyle.cli summary 7
```

## 응답 가이드

- 수면 기록 시: 사용자의 자연어를 파싱하여 날짜, 취침시간, 기상시간, 수면시간(분)을 추출하세요
- 할일 기록 시: 기한이 있으면 "YYYY-MM-DD HH:MM" 형식으로 변환하세요
- 자유 기록 시: 원문 그대로 전달하세요. 분류는 자동으로 됩니다
- 통계 요청 시: 결과를 자연스러운 한국어로 전달하세요
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/msalt/lifestyle/test_cli.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add msalt/lifestyle/cli.py msalt/skills/lifestyle/ tests/msalt/lifestyle/test_cli.py
git commit -m "feat(lifestyle): add CLI entry point and nanobot skill"
```

---

### Task 15: 전체 테스트 실행 및 최종 정리

**Files:**
- Modify: `msalt/news/sources.json` (YouTube 소스 추가)
- Create: `msalt/news/__main__.py`
- Create: `msalt/lifestyle/__main__.py`

- [ ] **Step 1: Add YouTube sources to sources.json**

`msalt/news/sources.json`의 `youtube` 배열에 초기 채널 추가:

```json
{
  "rss": [...],
  "youtube": [
    {
      "name": "삼프로TV",
      "channel_id": "UCz5AYMnEJIQqkhEZkRj3K4w"
    },
    {
      "name": "슈카월드",
      "channel_id": "UCsJ6RuBiTVWRX156FVbeaGg"
    }
  ]
}
```

- [ ] **Step 2: Create __main__.py files for CLI modules**

```python
# msalt/news/__main__.py
from msalt.news.cli import *
import sys

if __name__ == "__main__":
    # Delegates to cli.py __main__ block
    exec(open("msalt/news/cli.py").read())
```

실제로는 `msalt/news/cli.py`의 `if __name__` 블록이 이미 있으므로, `__main__.py`는 간단히:

```python
# msalt/news/__main__.py
from msalt.news.cli import main
main()
```

`cli.py`의 `if __name__` 블록을 `main()` 함수로 리팩터링:

```python
# msalt/news/cli.py 하단에 추가
def main():
    if len(sys.argv) < 2:
        print("Usage: python -m msalt.news.cli [collect|briefing|search <keyword>]")
        sys.exit(1)
    command = sys.argv[1]
    if command == "collect":
        print(run_collect())
    elif command == "briefing":
        time = sys.argv[2] if len(sys.argv) > 2 else "morning"
        print(run_briefing(time))
    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: python -m msalt.news.cli search <keyword>")
            sys.exit(1)
        print(run_search(sys.argv[2]))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

동일하게 `msalt/lifestyle/cli.py`와 `msalt/lifestyle/__main__.py`도 구성.

- [ ] **Step 3: Run all tests**

Run: `python -m pytest tests/msalt/ -v`
Expected: ALL PASS (전체 msalt 테스트)

- [ ] **Step 4: Run linter**

Run: `ruff check msalt/ tests/msalt/`
Expected: No errors (또는 수정 후 통과)

- [ ] **Step 5: Commit**

```bash
git add msalt/ tests/msalt/
git commit -m "feat(msalt): finalize project structure with CLI entry points"
```

---

## Summary

| Task | Phase | 설명 | 예상 테스트 수 |
|------|-------|------|------------|
| 1 | 1 | msalt 디렉토리 + config | 2 |
| 2 | 1 | nanobot config 예시 + 설정 가이드 | 0 (문서) |
| 3 | 1 | RPi 배포 (systemd + setup script) | 0 (인프라) |
| 4 | 2 | SQLite 저장소 | 4 |
| 5 | 2 | RSS 수집기 | 3 |
| 6 | 2 | YouTube 수집기 | 2 |
| 7 | 2 | 뉴스 오케스트레이터 | 2 |
| 8 | 2 | 브리핑 생성기 | 3 |
| 9 | 2 | 뉴스 스킬 (SKILL.md) | 0 (스킬) |
| 10 | 2 | 뉴스 CLI | 3 |
| 11 | 3 | 수면 기록 | 3 |
| 12 | 3 | 할일 관리 | 5 |
| 13 | 3 | 자유 텍스트 분류기 + 트래커 | 8 |
| 14 | 3 | 생활 습관 CLI + 스킬 | 3 |
| 15 | 3 | 최종 정리 + 전체 테스트 | 0 (검증) |
| **Total** | | | **38 tests** |
