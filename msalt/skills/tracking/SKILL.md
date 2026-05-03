---
name: tracking
description: 사용자가 정의한 항목(수면·음주·영어공부 등)에 대한 기록·조회·통계, 항목 추가/삭제를 처리합니다.
always: true
---

# 추적 항목 관리 스킬

## 🚨 절대 규칙 (먼저 읽을 것)

기록 의도가 보이면 **무조건 `my-nanobot-rpi tracking record …` CLI**를 호출. 다른 길은 없다.

- ❌ `write_file` / `edit_file` / `append` 등으로 `~/.nanobot/workspace/` 어디에도 기록 파일을 만들지 말 것. 디렉토리 이름이 `tracking_notes/`, `notes/`, `records/`, 무엇이든 동일.
- ❌ "기록 완료"라고 답해놓고 DB에 안 들어갔다면 거짓 응답이다. 진실의 단일 출처는 `~/.nanobot/workspace/msalt.db` 뿐.
- ❌ CLI 실행이 실패하면 **에러 원문(stderr)과 실행한 명령을 그대로 사용자에게 보여주고 멈춘다.** 사용자가 명시적으로 다른 방식을 지시하기 전까지 우회·폴백 금지.
- ❌ `python -m msalt.tracking …` / `python3 -m …` 형태 금지. venv 외부 인터프리터로 풀려 `ModuleNotFoundError` 난다. `my-nanobot-rpi tracking …`만 사용.

## 사용 시점

다음 의도가 보이면 이 스킬을 사용:
- 무언가를 기록한다 (예: "어제 11시에 잤어", "오늘 영어 1시간 했어")
- 새 항목 추적을 원한다 (예: "독서도 매일 기록할래")
- 통계·조회 (예: "지난주 수면 평균은?", "이번 주 음주 얼마나 했어?")
- 항목 목록 (예: "뭐뭐 기록하고 있지?")
- 항목 삭제 (예: "영어공부 더 이상 기록 안 할래")

## 처리 절차

### 기록 입력
사용자 발화를 자연어 그대로 다음 명령에 전달. agent가 시점·값을 추출해 호출:

```bash
my-nanobot-rpi tracking record <항목명> --date YYYY-MM-DD --num <분 or 양> --raw "<원문>"
my-nanobot-rpi tracking record <항목명> --date YYYY-MM-DD --bool --raw "<원문>"
my-nanobot-rpi tracking record <항목명> --date YYYY-MM-DD --no-bool --raw "<원문>"
my-nanobot-rpi tracking record <항목명> --date YYYY-MM-DD --text "<자유텍스트>" --raw "<원문>"
```

`--bool`은 "함/했음" 기록, `--no-bool`은 "안함/실패" 기록.

### 항목 추가
사용자에게 schema/시각 추론 결과를 확인받은 뒤:

```bash
my-nanobot-rpi tracking add <이름> <schema> --time HH:MM [--unit <단위>]
```

확인 흐름 예: "독서 시간도 기록할래" → "이렇게 등록할게: 독서 / duration / 매일 22:00. 맞아?" → "응" → add 실행.

### 조회/통계

```bash
my-nanobot-rpi tracking list
my-nanobot-rpi tracking summary <항목명> --days 7
```

### 삭제

```bash
my-nanobot-rpi tracking delete <항목명>
```

### 묶음 알림에 답하기

dispatcher가 여러 항목을 한 메시지로 묶어 보낼 수 있다. 예:

```
📝 기록할 항목 3개:
1. 수면 — 몇 시간/얼마나?
2. 음주 — 몇 잔?
3. 영어공부 — 했어?
```

사용자가 `"7시간 잤고 2잔 마셨어, 영어 했어"` 같이 한 번에 답하면 **각 항목별로 record CLI를 한 번씩 호출**한다. 부분 답("수면만 7시간")이면 매칭된 항목만 기록하고 나머지는 건드리지 않는다 (다음 retry 슬롯에서 다시 묻게 됨).

### boolean 부정 답

boolean schema 항목에서 사용자가 "아니" / "안 했어" / "no" / "패스" 등 부정 의미를 표현하면 `--no-bool`로 기록한다. 예: "영어공부 안 했어" → `my-nanobot-rpi tracking record 영어공부 --date YYYY-MM-DD --no-bool --raw "영어공부 안 했어"`.

## 응답 가이드

- 자연어 시점 표현은 절대 날짜로 변환해 사용자에게 다시 확인.
- 항목 추가는 반드시 사용자 yes/no 확인 후 실행.
- 통계는 CLI 출력 그대로 전달하되, 한 줄 코멘트 추가 가능 (단, 평가/훈계 금지).
- 미확실하면 묻는다. 추측하지 않는다.
