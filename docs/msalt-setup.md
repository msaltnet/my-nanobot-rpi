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

## 환경 변수 설정

`~/.bashrc` 또는 `~/.zshrc` 파일에 다음 내용을 추가:

```bash
export OPENAI_API_KEY="sk-..."
export TELEGRAM_BOT_TOKEN="1234567890:ABC..."
```

설정 후 터미널을 재시작하거나 `source ~/.bashrc` 실행.

---

## nanobot config 설정

### config 예시 복사

프로젝트 루트에서 다음 명령 실행:

```bash
cp msalt/nanobot-config.example.json nanobot-config.json
```

### allowFrom 편집

`nanobot-config.json` 파일에서 `allowFrom` 값을 본인의 Telegram User ID로 변경:

```json
"allowFrom": ["123456789"]
```

---

## 실행 방법

### 패키지 설치

```bash
pip install -e .
```

### nanobot gateway 실행

```bash
nanobot gateway
```

Telegram 봇이 활성화되어 메시지를 수신하기 시작합니다.
