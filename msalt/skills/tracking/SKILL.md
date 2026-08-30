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

기록할 항목·날짜·값을 사용자 발화와 아래 기본값으로 결정할 수 있으면 **확인 질문 없이 즉시 CLI를 실행**한다.
"저장할까?", "이대로 기록할까?"처럼 실행 전에 허락을 다시 묻거나 실행 명령을 미리 보여주지 않는다.
"오늘"/"어제" 같은 상대 날짜는 현재 시각 기준 절대 날짜로 변환해 바로 사용한다.

알림이나 버튼 텍스트에 `YYYY-MM-DD` 날짜가 들어 있으면 그 날짜가 기록 대상이다.
이 날짜를 `--date`에 그대로 사용하고, 현재 날짜나 "오늘/어제" 추정으로 바꾸지 않는다.

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
1. 수면 (2026-05-22 기록) — 몇 시간/얼마나?
2. 음주 (2026-05-22 기록) — 몇 잔?
3. 영어공부 (2026-05-22 기록) — 했어?
```

사용자가 `"7시간 잤고 2잔 마셨어, 영어 했어"` 같이 한 번에 답하면 **각 항목별로 record CLI를 한 번씩 호출**한다. 부분 답("수면만 7시간")이면 매칭된 항목만 기록하고 나머지는 건드리지 않는다 (다음 retry 슬롯에서 다시 묻게 됨).
묶음 알림에 날짜가 여러 개 섞여 있으면 각 항목 옆의 날짜를 해당 항목의 `--date`로 사용한다.

### 키보드 버튼 답변

dispatcher는 schema별 Telegram reply keyboard 버튼을 보낼 수 있다. 버튼을 누른 메시지는 일반 텍스트와 똑같이 처리한다. 버튼 텍스트에는 보통 항목명이 포함된다.
버튼 텍스트에 날짜가 포함되어 있으면 반드시 그 날짜를 `--date`로 사용한다.

- `"수면 2026-05-22 7시간"` → `--date 2026-05-22 --num 420`
- `"독서 2026-05-22 30분"` → `--date 2026-05-22 --num 30`
- `"물 2026-05-22 2잔"`처럼 quantity 항목이면 → `--date 2026-05-22 --num 2`
- `"음주 2026-05-22 안 마심"` / `"음주 2026-05-22 안 마셨어"` → `--date 2026-05-22 --num 0 --json '{"drink_type":null,"amount":0,"unit":"잔","serving_ml":null,"abv_percent":null,"alcohol_g":0}'`
- `"음주 2026-05-22 맥주 1캔"` / `"음주 2026-05-22 소주 1병"` 등은 순알코올 g으로 환산해서 `--num <g>`와 구조화 JSON을 같이 기록한다.
- 음주 용량·도수가 생략되면 제공된 기본 alcohol profile을 사용해 추정하고 즉시 기록한다. 사용자가 밝힌 용량·도수는 기본값보다 우선한다.
- `--json` 구조화 데이터는 DB 저장을 위한 내부 CLI 인자다. 사용자에게 JSON이나 전체 CLI 명령을 보여주지 않는다.
- `"영어공부 2026-05-22 했어"` → `--date 2026-05-22 --bool`
- `"영어공부 2026-05-22 안 했어"` → `--date 2026-05-22 --no-bool`

### boolean 부정 답

boolean schema 항목에서 사용자가 "아니" / "안 했어" / "no" / "패스" 등 부정 의미를 표현하면 `--no-bool`로 기록한다. 예: "영어공부 안 했어" → `my-nanobot-rpi tracking record 영어공부 --date YYYY-MM-DD --no-bool --raw "영어공부 안 했어"`.

## 응답 가이드

- 기록 입력 응답은 **CLI 성공 후** 다음 순서로 답한다: `추정 기준과 값(필요한 경우) → 기록된 항목·날짜 → CLI가 출력한 최근 7일/30일 조언`.
- 성공한 `tracking record` 출력의 `FOLLOW_UP_JSON`은 내부 제어 정보다. JSON 자체는 사용자에게 보여주지 않는다.
- 기록 응답은 항상 `message` 도구로 현재 대화에 한 번만 보낸다. 순서는 `저장 결과 → 최근 7일/30일 조언 → follow-up question`이다.
- `FOLLOW_UP_JSON.question`이 문자열이면 응답 마지막에 그대로 붙이고 `reply_keyboard`를 `message` 도구에 전달한다.
- `FOLLOW_UP_JSON.question`이 `null`이면 질문을 붙이지 않고 빈 `reply_keyboard`를 전달해 기존 Telegram 키보드를 제거한다.
- `message` 도구로 현재 대화에 전송한 뒤 같은 내용을 일반 최종 응답으로 중복 전송하지 않는다.
- 음주 추정값은 `맥주 1캔을 기본값 500ml·5%로 계산해 순알코올 약 19.7g으로 기록했어.`처럼 짧은 자연어로 알린다.
- 기록 응답에는 구조화 JSON, 전체 CLI 명령, 저장 전 확인 질문을 포함하지 않는다.
- 항목 추가는 반드시 사용자 yes/no 확인 후 실행.
- 통계는 CLI 출력 그대로 전달하되, 한 줄 코멘트 추가 가능 (단, 평가/훈계 금지).
- 항목·날짜·값을 사용자 발화와 정의된 기본값으로도 결정할 수 없을 때만 필요한 정보 하나를 묻는다.
