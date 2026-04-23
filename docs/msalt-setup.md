# msalt-nanobot 설정 가이드

## 사전 준비

### Telegram Bot Token 획득

1. Telegram에서 [@BotFather](https://t.me/BotFather)에게 메시지 전송
2. `/newbot` 명령어 입력
3. 봇 이름과 사용자명 설정 (사용자명은 `bot`으로 끝나야 함)
4. 발급된 **Bot Token**을 안전하게 보관

### OpenAI API Key 획득

1. [OpenAI Platform](https://platform.openai.com/)에 로그인
2. 우측 상단 계정 메뉴 → **API keys** 선택
3. **Create new secret key** 클릭
4. 발급된 **API Key**를 안전하게 보관 (재확인 불가)

### Telegram User ID 획득

1. Telegram에서 [@userinfobot](https://t.me/userinfobot)에게 메시지 전송
2. 응답으로 받은 **Id** 값을 메모 (숫자 형태)

---

## 설정과 기동

```bash
# 1. 설치
pip install -e .

# 2. 환경 변수
cp .env.example .env
# .env 편집 — 3개 값 입력:
#   OPENAI_API_KEY=sk-...
#   TELEGRAM_BOT_TOKEN=...
#   TELEGRAM_USER_ID=...   (숫자 ID)

# 3. 기동
msalt-nanobot
```

첫 실행 시 `~/.nanobot/config.json`과 `~/.nanobot/workspace/{SOUL,USER}.md`가
msalt 기본 템플릿으로 자동 생성됩니다.

## 상태 점검

```bash
msalt-nanobot doctor
```

`.env` 로드 여부, 필수 환경 변수, config·workspace 파일 존재, RSS 소스 11개의
실시간 연결 상태까지 한 번에 점검합니다.

## 선택: 웹 검색 provider

`.env`에 `TAVILY_API_KEY` 또는 `BRAVE_API_KEY`를 넣으면 해당 provider가
자동으로 사용됩니다. 키가 없으면 DuckDuckGo로 fallback.

`~/.nanobot/config.json`의 `tools.web.search.provider` 필드로 선택:
`tavily` (기본) / `brave` / `duckduckgo`.
