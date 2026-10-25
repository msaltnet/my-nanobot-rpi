# Issue #38 Korean news Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 영어 기사도 한국어 요약과 원문 링크로 전달한다.
**Architecture:** 기존 모델 요청에 번역을 명시하고 실패 시 보수적인 한국어 원문 표시 규칙과 안내를 사용한다. 전달 원장은 변경하지 않는다.
**Tech Stack:** Python >=3.11, 기존 OpenAI SDK/pytest/SQLite.
**Spec:** https://github.com/msaltnet/my-nanobot-rpi/issues/38 (approved v1, 2026-10-25).

## Global Constraints
추가 서비스·모델 호출·재시도·DB 변경 없음. 사용자 수정 보존. 운영 배포·실수신·merge는 별도 승인.

## Review Focus
영어와 한글이 한 필드에 섞인 fallback, 빈 모델 응답, 한국어 제목/영어 요약, 출처·URL·예약 URL 보존, 숫자·약어 보존.

### Task 1: 한국어 요약과 실패 표시
**Files:** msalt/news/briefing.py, msalt/skills/news/SKILL.md, tests/msalt/news/test_briefing.py
**Interfaces:** BriefingGenerator.render_articles / GeneratedBriefing.text, urls 유지.
- [ ] 기존 baseline 17개 PASS 확인.
- [ ] 영어 원문 fallback 미노출, 혼합 필드, 예외/빈 응답, 성공 프롬프트·수치·URL 보존 테스트를 먼저 추가한다.
- [ ] python -m pytest tests/msalt/news/test_briefing.py -q: 변경 요구로 실패함을 확인한다.
- [ ] SYSTEM_PROMPT와 _format_plain만 최소 수정하고 뉴스 스킬 지시를 명확히 한다.
- [ ] 관련 뉴스 테스트와 python -m pytest tests/msalt/ 및 전체 pytest를 실행한다.
- [ ] 후보 커밋 생성 후 독립 Tester/Reviewer가 Issue와 diff를 직접 확인한다.
- [ ] 현재 SHA 검증 결과를 PR에 기록한다. AC5는 배포 전 BLOCKED로 유지한다.

## Execution ledger
Baseline: 17 passed (Python 3.13, Windows, external calls mocked).
Ruling: 사용자가 승인 설계대로 구현·테스트·리뷰를 명시했으므로 추가 계획 승인 없이 실행한다.
Ruling: fallback은 번역기가 아니다. 한글이 있고 한글 사이의 각 구간에 영문 단어가 최대 하나인 필드만 원문 표시하며 그 외에는 한국어 안내로 대체한다. 고유명사 하나가 섞인 한국어는 보존하며, 여러 영문 단어로 된 고유명사는 안내로 대체될 수 있다. 성공 요약에는 이 규칙을 적용하지 않는다.
Pre-flight: 단일 작업, 인터페이스 변경 없음.

RED: 11 failed, 16 passed; 영어 원문 노출과 번역 지시 누락을 확인한 후 구현.

Review fix RED: 한글+대문자 영어 본문 노출 2 failed, 5 passed. 연속 대문자 단어도 안내로 대체한다.

Review fix RED: iPhone/OpenAI 한국어 보존 및 숫자로 분리된 영어 문장 2 failed, 7 passed. 영문 단어 여러 개를 포함한 비한글 구간을 숨기는 표시 규칙으로 보완. 기존 offline fallback 영어 원문 기대 3실패도 새 정책과 URL/이력보존 검증으로 갱신.
