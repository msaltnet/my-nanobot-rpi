---
name: tracking
description: 사용자가 정의한 항목(수면·음주·영어공부 등)에 대한 기록·조회·통계, 항목 추가/삭제를 처리합니다.
---

# 추적 항목 관리 스킬

## 사용 시점

다음 의도가 보이면 이 스킬을 사용:
- 무언가를 기록한다 (예: "어제 11시에 잤어", "오늘 영어 1시간 했어")
- 새 항목 추적을 원한다 (예: "독서도 매일 기록할래")
- 통계·조회 (예: "지난주 수면 평균은?", "이번 주 음주 얼마나 했어?")
- 항목 목록 (예: "뭐뭐 기록하고 있지?")
- 항목 삭제 (예: "영어공부 더 이상 기록 안 할래")

## 처리 절차

### 기록 입력
사용자 발화를 자연어 그대로 다음 명령에 전달. 시점·값 파싱은 내부 LLM 파서가 처리.

```bash
# 일반 흐름은 nanobot agent가 직접 NaturalLanguageParser를 호출하는 것이 이상적이지만,
# 현 구현에서는 agent가 시점·값을 추출한 뒤 CLI로 호출:
python -m msalt.tracking record <항목명> --date YYYY-MM-DD --num <분 or 양> --raw "<원문>"
python -m msalt.tracking record <항목명> --date YYYY-MM-DD --bool --raw "<원문>"
python -m msalt.tracking record <항목명> --date YYYY-MM-DD --text "<자유텍스트>" --raw "<원문>"
```

### 항목 추가
사용자에게 schema/시각 추론 결과를 확인받은 뒤:

```bash
python -m msalt.tracking add <이름> <schema> --time HH:MM [--unit <단위>]
```

확인 흐름 예: "독서 시간도 기록할래" → "이렇게 등록할게: 독서 / duration / 매일 22:00. 맞아?" → "응" → add 실행.

### 조회/통계

```bash
python -m msalt.tracking list
python -m msalt.tracking summary <항목명> --days 7
```

### 삭제

```bash
python -m msalt.tracking delete <항목명>
```

## 응답 가이드

- 자연어 시점 표현은 절대 날짜로 변환해 사용자에게 다시 확인.
- 항목 추가는 반드시 사용자 yes/no 확인 후 실행.
- 통계는 CLI 출력 그대로 전달하되, 한 줄 코멘트 추가 가능 (단, 평가/훈계 금지).
- 미확실하면 묻는다. 추측하지 않는다.
