# msalt-nanobot TRD

> **문서 성격**: 사후 정리 TRD. 시스템의 아키텍처와 컴포넌트별 책임을 기록한다. 코드 시그니처나 확장 가이드는 다루지 않으며, 그 정보는 코드와 [PYTHON_SDK.md](PYTHON_SDK.md)를 참조한다.
>
> **최종 업데이트**: 2026-04-14

---

## 1. 시스템 개요

msalt-nanobot은 **단일 라즈베리파이 노드**에서 nanobot 프레임워크를 호스트하고, 그 위에 msalt 전용 도메인 모듈(`msalt/`)을 얹은 구조다. 외부와는 텔레그램 봇 API와 OpenAI / RSS / YouTube API로 연결된다.

### 컨텍스트 다이어그램

```
                 ┌──────────────────────────┐
                 │      msalt (사용자)      │
                 │   Telegram 모바일 클라이언트 │
                 └────────────┬─────────────┘
                              │ HTTPS (Bot API)
                              ▼
   ┌────────────────────────────────────────────────────┐
   │           Telegram Bot API (api.telegram.org)      │
   └────────────────────────┬───────────────────────────┘
                            │ long polling
                            ▼
   ┌────────────────────────────────────────────────────┐
   │   Raspberry Pi 3B+ — systemd: msalt-nanobot.service│
   │   ┌────────────────────────────────────────────┐   │
   │   │              nanobot core                  │   │
   │   │  (channels, agent loop, cron, dream, ...)  │   │
   │   └────────────────┬───────────────────────────┘   │
   │                    │ skill invocation               │
   │   ┌────────────────▼───────────────────────────┐   │
   │   │              msalt 모듈                    │   │
   │   │  news / lifestyle / storage / config       │   │
   │   └─┬──────────┬──────────┬──────────────┬─────┘   │
   │     │          │          │              │         │
   │     ▼          ▼          ▼              ▼         │
   │  SQLite    workspace   logs          ~/.nanobot/    │
   │  (msalt.db) memory     (journald)    config.json    │
   └─────┬──────────┬──────────────────────────────────┘
         │          │
         ▼          ▼
   ┌─────────┐ ┌─────────┐ ┌─────────────┐
   │ OpenAI  │ │  RSS    │ │ YouTube Data│
   │  API    │ │ Feeds   │ │     API     │
   └─────────┘ └─────────┘ └─────────────┘
```

## 2. 아키텍처

### 레이어 구성

```
┌─────────────────────────────────────────────────────┐
│  L4. 사용자 접점 (Telegram channel — nanobot 제공)  │
├─────────────────────────────────────────────────────┤
│  L3. 스킬 (msalt/skills/*/SKILL.md)                 │
│       대화형 진입점 + 크론 진입점. 얇은 라우팅 레이어│
├─────────────────────────────────────────────────────┤
│  L2. 도메인 모듈 (msalt/news, msalt/lifestyle)     │
│       비즈니스 로직: 수집·요약·분류·집계           │
├─────────────────────────────────────────────────────┤
│  L1. 인프라 (msalt/storage.py, msalt/config.py)    │
│       SQLite I/O, 환경 설정 로드                   │
├─────────────────────────────────────────────────────┤
│  L0. 외부 의존성                                   │
│       nanobot core, OpenAI SDK, feedparser, httpx, │
│       python-telegram-bot, sqlite3                 │
└─────────────────────────────────────────────────────┘
```

### 호출 방향 원칙

- **상위 → 하위 단방향**. L3는 L2를, L2는 L1을 호출. 역방향 금지.
- L2 모듈은 서로 직접 호출하지 않음. 공통 데이터는 L1 (`storage.py`) 경유.
- nanobot core는 msalt를 모름. msalt가 nanobot의 SKILL 규약과 cron 규약을 따른다.

### 디렉토리 구조

```
msalt/
├── config.py              # MsaltConfig 데이터클래스
├── storage.py             # SQLite Storage 클래스
├── news/
│   ├── rss.py             # RssCollector
│   ├── youtube.py         # YoutubeCollector
│   ├── collector.py       # NewsCollector (오케스트레이터)
│   ├── briefing.py        # BriefingGenerator
│   ├── cli.py             # python -m msalt.news 엔트리포인트
│   ├── sources.json       # RSS/YouTube 소스 목록
│   └── __main__.py
├── lifestyle/
│   ├── sleep.py           # SleepTracker
│   ├── todo.py            # TodoManager
│   ├── classifier.py      # classify_text() 키워드 기반
│   ├── tracker.py         # LifeTracker
│   ├── cli.py             # python -m msalt.lifestyle 엔트리포인트
│   └── __main__.py
├── skills/
│   ├── news/SKILL.md
│   ├── news-briefing/SKILL.md
│   └── lifestyle/SKILL.md
├── workspace/
│   ├── SOUL.md            # 봇 페르소나 템플릿
│   └── USER.md            # 사용자 정보 템플릿
└── nanobot-config.example.json
```

## 3. 컴포넌트 책임

각 모듈이 무엇을 책임지는지 한 문단씩. 시그니처는 코드 직접 참조.

### 3.1 인프라 레이어 (L1)

**`msalt/config.py` — MsaltConfig**
모든 msalt 모듈이 공유하는 설정값을 단일 데이터클래스로 보관한다. 타임존(`Asia/Seoul`), SQLite 경로(`~/.nanobot/workspace/msalt.db`), 브리핑 시각(07:00, 19:00) 등을 노출한다. 환경별 분기는 없다 — 1인용·단일 환경 가정.

**`msalt/storage.py` — Storage**
SQLite 4개 테이블에 대한 CRUD를 담당한다. 모든 도메인 모듈은 이 클래스만을 통해 DB에 접근한다. 트랜잭션·커넥션 관리·`initialize()`(테이블 생성) 책임. 비즈니스 로직(분류·요약·집계)은 일절 포함하지 않는 순수 I/O 레이어.

### 3.2 뉴스 도메인 (L2: `msalt/news/`)

**`rss.py` — RssCollector**
`sources.json`의 RSS 피드 목록을 읽고 `feedparser`로 파싱한다. 피드별로 최근 N개 기사 제목·URL·요약·게시일을 추출해 표준 dict 리스트로 반환한다. 네트워크 에러는 소스 단위로 격리(한 피드가 죽어도 다른 피드는 계속).

**`youtube.py` — YoutubeCollector**
YouTube Data API로 채널의 최신 영상을 조회한다. 영상 제목·URL·게시일을 RSS 기사와 동일한 스키마로 변환(`format_as_article`)해 후속 파이프라인이 통합 처리할 수 있게 한다. 자막(`get_transcript`)은 현재 placeholder — 추후 확장.

**`collector.py` — NewsCollector**
RSS와 YouTube 수집 결과를 합치고 `Storage.insert_article`로 저장한다. URL UNIQUE 제약으로 중복 자동 차단. 수집 자체만 책임지고 요약은 하지 않는다.

**`briefing.py` — BriefingGenerator**
DB에 누적된 최근 기사를 읽어 OpenAI GPT로 요약 브리핑 텍스트를 생성한다. 카테고리(국내/해외/유튜브)별로 묶고, 카테고리당 3~5개 항목을 뽑아 한국어 헤드라인 + 한 줄 요약 형태로 출력한다. URL 기반 dedup은 이 시점에도 한 번 더 적용.

**`cli.py` — main**
`python -m msalt.news <command>` 엔트리포인트. 서브커맨드: `collect`(수집만), `briefing`(수집 후 요약 생성), `search <keyword>`(DB 검색). 크론 트리거와 사용자 명령 양쪽에서 공유.

**`sources.json`**
RSS 피드 5개(한경·매경·조선비즈·Reuters·CNBC)와 YouTube 채널 2개(삼프로TV·슈카월드)의 ID/URL 정의. 코드 변경 없이 소스 추가·제거 가능.

### 3.3 라이프스타일 도메인 (L2: `msalt/lifestyle/`)

**`sleep.py` — SleepTracker**
"어제 23시에 자서 7시에 일어났어" 같은 자연어를 정규식·시간 표현 휴리스틱으로 파싱해 `(date, bedtime, wakeup, duration_min)` 튜플로 변환한다. `Storage.upsert_sleep`으로 저장(같은 날짜는 덮어씀). 통계는 주간/월간 평균 수면시간·취침시각 분산을 계산해 사람이 읽을 문자열로 포맷.

**`todo.py` — TodoManager**
할일 추가, 완료 처리, 미완료 목록 조회, 기한 임박 항목 조회. 자연어 기한 파싱(예: "내일", "다음주 월요일")은 기본 케이스만 지원 — 모호하면 사용자에게 다시 묻는 정책.

**`classifier.py` — classify_text**
순수 함수. 입력 텍스트에 대해 키워드 사전 매칭으로 카테고리(`exercise`/`food`/`health`/`mood`/`sleep`/`other`)를 반환한다. LLM 호출 없음 — 즉답성·비용 절감 목적. 키워드 사전은 모듈 내 상수로 정의돼 있어 추가는 코드 수정 필요.

**`tracker.py` — LifeTracker**
자유 텍스트를 받아 `classifier.classify_text`로 카테고리를 결정한 뒤 `Storage.insert_life_log`로 저장한다. 주간 요약은 카테고리별 빈도수와 최근 기록 샘플을 묶어 사람이 읽을 문자열로 포맷.

**`cli.py` — main**
`python -m msalt.lifestyle <command>` 엔트리포인트. 7개 서브커맨드: `sleep-record`, `sleep-stats`, `todo-add`, `todo-list`, `todo-done`, `log`, `summary`.

### 3.4 스킬 레이어 (L3: `msalt/skills/`)

스킬 파일은 nanobot의 `SKILL.md` 규약(YAML frontmatter + Markdown 본문)을 따른다. 본문은 LLM에게 "이 도구를 언제·어떻게 호출할지"를 설명하고, 실행은 내부적으로 `python -m msalt.news` 또는 `python -m msalt.lifestyle` CLI를 호출한다.

**`news/SKILL.md`** — 대화형 뉴스 스킬. 사용자가 "최근 뉴스 보여줘", "삼성전자 관련 기사 찾아줘" 같은 자유 질의를 던졌을 때 LLM이 이 스킬을 호출.

**`news-briefing/SKILL.md`** — 크론 스케줄 전용 스킬. `metadata: {"always": false}`로 일반 대화에서는 노출되지 않고, 07:00/19:00 cron 트리거에서만 호출된다.

**`lifestyle/SKILL.md`** — 수면·할일·자유 기록 통합 스킬. 사용자 의도에 따라 적절한 lifestyle 서브커맨드로 라우팅.

### 3.5 워크스페이스 템플릿 (`msalt/workspace/`)

**`SOUL.md`** — 봇 페르소나. 한국어 반말 톤, 경제 브리핑은 사실만, 생활 기록은 비판 없이 수용 등의 행동 원칙이 정의돼 있다. nanobot 첫 실행 시 `~/.nanobot/workspace/SOUL.md`로 복사돼 시스템 프롬프트에 주입된다.

**`USER.md`** — 사용자 정보 템플릿. 위치(한국)·언어(한국어)·관심사(경제/금융)·선호 브리핑 시간 등이 사전 기재돼 있다. 이후 dream 시스템이 대화에서 추출한 사실을 자동 추가.

## 4. 데이터 모델

SQLite 단일 파일(`~/.nanobot/workspace/msalt.db`)에 4개 테이블.

### `news_articles` — 수집된 뉴스/영상 원본

| 컬럼 | 타입 | 용도 |
|------|------|------|
| `id` | INTEGER PK | 자동 증가 |
| `source` | TEXT | 소스 식별자 (예: `hankyung`, `youtube:samprotv`) |
| `title` | TEXT | 기사/영상 제목 |
| `url` | TEXT UNIQUE | 원문 URL — UNIQUE 제약으로 중복 자동 차단 |
| `summary` | TEXT | RSS의 description 또는 영상 설명 |
| `category` | TEXT | `domestic`/`global`/`youtube` |
| `collected_at` | TEXT | 수집 시각 (`datetime('now')`) |

### `sleep_log` — 수면 기록 (날짜별 1건)

| 컬럼 | 타입 | 용도 |
|------|------|------|
| `date` | TEXT PK | `YYYY-MM-DD` — 같은 날짜 재기록 시 덮어씀 |
| `bedtime` | TEXT | 취침 시각 (`HH:MM`) |
| `wakeup` | TEXT | 기상 시각 (`HH:MM`) |
| `duration_min` | INTEGER | 수면 시간 (분) |
| `quality` | TEXT | 주관 평가 (옵션, 예: `good`/`bad`) |

### `todos` — 할일

| 컬럼 | 타입 | 용도 |
|------|------|------|
| `id` | INTEGER PK | 자동 증가 |
| `content` | TEXT | 할일 내용 |
| `due_at` | TEXT | 기한 (ISO8601, nullable) |
| `completed_at` | TEXT | 완료 시각 (nullable) |
| `status` | TEXT | `pending`/`done` (기본 `pending`) |

### `life_log` — 자유 텍스트 생활 기록

| 컬럼 | 타입 | 용도 |
|------|------|------|
| `id` | INTEGER PK | 자동 증가 |
| `timestamp` | TEXT | 기록 시각 |
| `raw_text` | TEXT | 사용자 원본 입력 |
| `category` | TEXT | classifier 결과 (`exercise`/`food`/`health`/`mood`/`sleep`/`other`) |
| `parsed_data` | TEXT | 추후 구조화 데이터(JSON) — 현재는 NULL |

## 5. 외부 의존성

| 의존성 | 용도 | 호출 위치 | 인증 |
|--------|------|-----------|------|
| **nanobot core** | 에이전트 루프, 채널, 크론, 메모리, dream | 호스트 프로세스 | — |
| **OpenAI API** (gpt-5-mini) | 브리핑 요약, 대화 응답 | `briefing.py`, nanobot agent loop | `OPENAI_API_KEY` |
| **Telegram Bot API** | 사용자 인터페이스 | nanobot telegram channel | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_ID` (allowlist) |
| **YouTube Data API v3** | 채널 최신 영상 조회 | `youtube.py` | `YOUTUBE_API_KEY` |
| **RSS 피드** (5개) | 한국·미국 뉴스 수집 | `rss.py` | 없음 (공개) |
| **feedparser** | RSS XML 파싱 | `rss.py` | — |
| **httpx** | YouTube API HTTP 호출 | `youtube.py` | — |
| **python-telegram-bot** | Telegram 통신 (nanobot 내부) | nanobot | — |
| **sqlite3** | DB I/O | `storage.py` | — (Python 표준) |

비밀값은 모두 `.env` 단일 파일에 정의하고, nanobot config(`config.json`)는 `${VAR}` 치환만 사용한다.

## 6. 배포 토폴로지

### 단일 노드 구성

```
Raspberry Pi 3B+ (1GB RAM, 1GB swap)
└── systemd: msalt-nanobot.service
    └── nanobot gateway
        ├── Telegram channel (long polling)
        ├── Cron service
        │   ├── 07:00 KST → news-briefing skill
        │   └── 19:00 KST → news-briefing skill
        ├── Agent loop (gpt-5-mini)
        ├── Memory & Dream (12h cycle)
        └── msalt 도메인 모듈 (skill 호출 시 활성화)

파일 시스템:
~/.nanobot/
├── config.json          # nanobot 설정 (.env 치환)
└── workspace/
    ├── SOUL.md          # 봇 페르소나
    ├── USER.md          # 사용자 정보
    ├── memory/
    │   ├── MEMORY.md    # dream 자동 관리 장기 기억
    │   └── history.jsonl
    └── msalt.db         # SQLite (뉴스/수면/할일/생활기록)
```

### 시작 절차

1. systemd가 부팅 시 서비스를 시작
2. nanobot이 `config.json` 로드 → `.env` 치환
3. workspace 초기화 (`SOUL.md`/`USER.md`는 사전 복사된 상태)
4. Telegram long polling 시작
5. cron 등록 (브리핑 2회/일)
6. 사용자 메시지 또는 cron 트리거 대기

### 정상 운영 가정

- 인터넷 연결 24시간 유지 (RSS·OpenAI·Telegram 호출 필수)
- RPi 전원·SD카드 안정성 (UPS·백업은 운영 정책)
- swap 1GB 활성화 (OOM 방지)
- 로그는 journald로 회수 (`journalctl -u msalt-nanobot`)

## 7. 테스트 전략

### 구성

- **프레임워크**: pytest
- **위치**: `tests/msalt/{news,lifestyle}/test_*.py`
- **import 모드**: `--import-mode=importlib` — `news/cli.py`와 `lifestyle/cli.py`의 basename 충돌 회피
- **`__init__.py` 정책**: 테스트 디렉토리에는 두지 않음 (프로젝트 컨벤션)
- **현재 테스트 수**: 38개 (전 모듈 통과)

### 모킹 정책

- **외부 API (OpenAI/YouTube/RSS)**: 모두 모킹. 실제 호출은 통합 테스트에서만 수동 수행.
- **SQLite**: 임시 파일 DB(`tmp_path`)로 실제 동작 검증 — 모킹하지 않음.
- **시간**: `freezegun` 또는 인자 주입으로 제어.

### 커버리지 우선순위

1. `classifier.py` — 키워드 분류 정확도 (분류 실패 시 다운스트림 영향 큼)
2. `storage.py` — DB 스키마·UNIQUE 제약·upsert 동작
3. `briefing.py` — dedup 로직, 카테고리 그룹핑
4. `sleep.py` — 자연어 시간 파싱 (다양한 표현 케이스)
5. CLI 엔트리포인트 — argparse 인자 처리

---

## 부록: 관련 문서

- [PRD (제품 요구사항)](msalt-prd.md)
- [설정 가이드](msalt-setup.md)
- [RPi 배포 가이드](msalt-rpi-deploy.md)
- [원본 설계 문서](superpowers/specs/2026-04-12-msalt-nanobot-design.md)
- [구현 계획](superpowers/plans/2026-04-12-msalt-nanobot.md)
- [nanobot SDK 참조](PYTHON_SDK.md)
- [nanobot 메모리 시스템](MEMORY.md)
