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
