---
name: news
description: 경제 뉴스를 검색하고 요약합니다. 사용자가 뉴스, 경제, 시장 관련 질문을 할 때 사용하세요.
---

# 뉴스 검색 스킬

사용자가 뉴스나 경제 관련 질문을 하면 shell 도구로 아래 콘솔 명령을 실행하세요. `python -m …` / `python3 -m …` 형태는 venv 외부 인터프리터로 풀려 `ModuleNotFoundError`가 나니 금지.

## 최신 뉴스 브리핑 요청 시

```bash
msalt-nanobot news briefing           # 아침 (기본)
msalt-nanobot news briefing evening   # 저녁
```

## 키워드로 뉴스 검색 시

```bash
msalt-nanobot news search "키워드"
```

## 뉴스 수집 실행 (수동)

```bash
msalt-nanobot news collect
```

## 응답 가이드

- 결과를 한국어로 자연스럽게 요약해서 전달하세요
- 원문 링크를 반드시 포함하세요
- 중복 기사는 하나로 합쳐서 전달하세요
