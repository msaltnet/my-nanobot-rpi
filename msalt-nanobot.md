# msalt-nanobot

nanobot 포크 기반 개인 AI 비서 — 경제 뉴스 브리핑 + 생활 습관 관리

## 개요

nanobot 프레임워크를 기반으로 라즈베리파이 3B+에서 구동되는 개인 비서.
텔레그램을 통해 경제 뉴스 브리핑과 생활 습관 관리 기능을 제공한다.

## 주요 기능

### 1. 경제 뉴스 비서
- 한국 뉴스 (한경, 매경, 조선비즈) RSS 수집
- 미국 뉴스 (Reuters, CNBC) RSS 수집
- YouTube 채널 (삼프로TV, 슈카월드) 영상 수집
- GPT 기반 요약 브리핑 생성
- 하루 2회 자동 브리핑 (아침 07:00, 저녁 19:00)
- 키워드 검색, 주간 요약 등 대화형 요청 지원
- 추후 X(Twitter), Reddit 등 확장 가능

### 2. 생활 습관 관리
- **수면 기록**: 자연어 입력 → 취침/기상/수면시간 파싱 → 주간/월간 통계
- **할일 관리**: 추가, 완료, 리마인더, 기한별 조회
- **자유 기록**: "5km 달림", "커피 3잔" 등 자유 텍스트 → 자동 분류 (운동/식단/건강/감정)
- 주간 생활 리포트 자동 생성

### 3. 인프라
- 라즈베리파이 3B+ (1GB RAM) 구동
- 텔레그램 인터페이스 (푸시 + 대화형)
- OpenAI GPT (gpt-4o-mini) API
- systemd 서비스로 자동 시작

## 기술 스택

| 구성 요소 | 기술 |
|----------|------|
| 프레임워크 | nanobot (포크, upstream 동기화) |
| 언어 | Python 3.11+ |
| LLM | OpenAI GPT (gpt-4o-mini) |
| 채널 | Telegram (python-telegram-bot) |
| 뉴스 수집 | feedparser (RSS), YouTube Data API, httpx |
| 데이터 저장 | SQLite |
| 스케줄링 | nanobot 크론 시스템 |
| 배포 | Raspberry Pi 3B+, systemd |

## 프로젝트 구조

```
msalt/
├── config.py                 # msalt 전용 설정
├── storage.py                # SQLite 저장소 (뉴스/수면/할일/생활기록)
├── news/
│   ├── rss.py                # RSS 수집기
│   ├── youtube.py            # YouTube 수집기
│   ├── collector.py          # 수집 오케스트레이터
│   ├── briefing.py           # 브리핑 생성기
│   ├── cli.py                # CLI (collect, briefing, search)
│   └── sources.json          # 소스 설정
├── lifestyle/
│   ├── sleep.py              # 수면 기록/통계
│   ├── todo.py               # 할일 관리
│   ├── classifier.py         # 키워드 기반 자동 분류
│   ├── tracker.py            # 자유 텍스트 생활 기록
│   └── cli.py                # CLI (sleep, todo, log, summary)
└── skills/
    ├── news/SKILL.md          # 뉴스 대화형 스킬
    ├── news-briefing/SKILL.md # 크론 브리핑 스킬
    └── lifestyle/SKILL.md     # 생활 습관 스킬
```

## 시작하기

```bash
# 1. 환경 변수 설정
cp .env.example .env
# .env 편집 — 아래 4개 값 입력:
#   OPENAI_API_KEY=sk-...
#   TELEGRAM_BOT_TOKEN=... (@BotFather에서 발급)
#   TELEGRAM_USER_ID=...   (@userinfobot에서 확인)
#   YOUTUBE_API_KEY=...    (Google Cloud Console에서 발급)

# 2. nanobot config 복사 (편집 불필요 — .env에서 자동 참조)
cp msalt/nanobot-config.example.json ~/.nanobot/config.json

# 3. 설치 및 실행
pip install -e .
nanobot gateway
```

라즈베리파이 배포는 [docs/msalt-rpi-deploy.md](docs/msalt-rpi-deploy.md) 참고.

## 문서

- [설정 가이드](docs/msalt-setup.md)
- [RPi 배포 가이드](docs/msalt-rpi-deploy.md)
- [설계 문서](docs/superpowers/specs/2026-04-12-msalt-nanobot-design.md)
- [구현 계획](docs/superpowers/plans/2026-04-12-msalt-nanobot.md)

## 추후 확장

- X(Twitter), Reddit 소스 추가
- 블로그/커뮤니티 크롤링
- 텔레그램 인라인 버튼/메뉴 UI
- 데이터 시각화 (차트 이미지 생성)

