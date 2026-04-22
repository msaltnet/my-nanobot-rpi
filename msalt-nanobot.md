# msalt-nanobot

nanobot 포크 기반 개인 AI 비서 — 경제 뉴스 브리핑 + 추적 항목 기반 생활 기록

## 개요

nanobot 프레임워크를 기반으로 라즈베리파이 3B+에서 구동되는 개인 비서.
텔레그램을 통해 경제 뉴스 브리핑과 사용자 정의 추적 항목 기록 기능을 제공한다.

## 주요 기능

### 1. 경제 뉴스 비서
- 한국 뉴스 (한국경제, 매일경제, 경향신문 경제) RSS 수집
- 해외 뉴스 (BBC Business, CNBC) RSS 수집
- GPT 기반 요약 브리핑 생성
- 하루 2회 자동 브리핑 (아침 07:00, 저녁 19:00)
- 키워드 검색, 주간 요약 등 대화형 요청 지원
- 추후 X(Twitter), Reddit 등 확장 가능

### 2. 추적 항목 기반 생활 기록
- 사용자 정의 항목 (수면·음주·영어공부 시드 + 자연어로 추가)
- 4가지 schema: freetext / duration / quantity / boolean
- 30분 단위 디스패처가 시각 도래·누락 항목을 능동 알림
- LLM 기반 자연어 입력 ("어제 11시에 잤어", "지난주 화요일에 영어 1시간")
- 통계: 평균·합계·수행률

### 3. 인프라
- 라즈베리파이 3B+ (1GB RAM) 구동
- 텔레그램 인터페이스 (푸시 + 대화형)
- OpenAI GPT (gpt-5-mini) API
- systemd 서비스로 자동 시작

## 기술 스택

| 구성 요소 | 기술 |
|----------|------|
| 프레임워크 | nanobot (포크, upstream 동기화) |
| 언어 | Python 3.11+ |
| LLM | OpenAI GPT (gpt-5-mini) |
| 채널 | Telegram (python-telegram-bot) |
| 뉴스 수집 | feedparser (RSS) |
| 데이터 저장 | SQLite |
| 스케줄링 | nanobot 크론 시스템 |
| 배포 | Raspberry Pi 3B+, systemd |

## 프로젝트 구조

```
msalt/
├── config.py                 # msalt 전용 설정
├── storage.py                # SQLite 저장소 (뉴스 + 추적 항목/기록)
├── news/
│   ├── rss.py                # RSS 수집기
│   ├── collector.py          # 수집 오케스트레이터
│   ├── briefing.py           # 브리핑 생성기
│   ├── cli.py                # CLI (collect, briefing, search)
│   └── sources.json          # 소스 설정
├── tracking/
│   ├── items.py              # TrackedItem CRUD + 시드
│   ├── records.py            # 기록 upsert + 통계
│   ├── parser.py             # LLM 자연어 파서
│   ├── dispatcher.py         # 30분 디스패처
│   └── cli.py                # CLI (dispatch/add/list/delete/record/summary)
├── skills/
│   ├── news/SKILL.md          # 뉴스 대화형 스킬
│   ├── news-briefing/SKILL.md # 크론 브리핑 스킬
│   └── tracking/SKILL.md      # 추적 항목 스킬
└── workspace/
    ├── SOUL.md                # 봇 페르소나 템플릿 (사전 세팅용)
    └── USER.md                # 사용자 정보 템플릿
```

## 시작하기

```bash
# 1. 환경 변수 설정
cp .env.example .env
# .env 편집 — 아래 3개 값 입력:
#   OPENAI_API_KEY=sk-...
#   TELEGRAM_BOT_TOKEN=... (@BotFather에서 발급)
#   TELEGRAM_USER_ID=...   (@userinfobot에서 확인)

# 2. nanobot config 복사 (편집 불필요 — .env에서 자동 참조)
cp msalt/nanobot-config.example.json ~/.nanobot/config.json

# 3. workspace 사전 세팅 (봇 페르소나 / 사용자 정보 템플릿)
mkdir -p ~/.nanobot/workspace
cp msalt/workspace/SOUL.md ~/.nanobot/workspace/SOUL.md
cp msalt/workspace/USER.md ~/.nanobot/workspace/USER.md

# 4. 설치 및 실행
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

