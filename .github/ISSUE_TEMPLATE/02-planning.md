---
name: "구현 설계 · Planning"
about: "Planner가 Issue 본문을 설계 계약으로 정리합니다. 생성 자체는 승인이 아닙니다."
title: ""
labels: ""
assignees: ""
---

## Problem

<!-- 문제, 재현 조건, 사용자 영향과 현재 코드 근거. -->

## Goal

<!-- 이번 Issue가 달성할 결과. -->

## User Experience

<!-- 사용자 입력 → 응답·알림 → 실패·재시도 흐름과 구체적 예시. -->

## Requirements

<!-- 필수 동작과 제약. 각 항목에 R1, R2처럼 ID를 부여합니다. -->

## Non-goals

<!-- 이번 범위에서 제외할 사항. -->

## Design

### Architecture

<!-- 기존 nanobot/msalt 구조와 변경 흐름. 필요하면 Mermaid. -->

### Data Model

<!-- SQLite 테이블·키·호환성·마이그레이션·기존 데이터 보존. 해당 없으면 이유. -->

### Interface / UX

<!-- Telegram, CLI, 환경 변수, 설정, 스킬 인터페이스와 호환성. -->

### Components

<!-- 컴포넌트 책임, 외부 API 오류와 자원 관리. -->

### Integration Points

<!-- nanobot 도구/스킬, 뉴스 크론, tracking timer, OCI/RPi 배포에 미치는 영향. -->

## Implementation Scope

<!-- 변경 파일·새 의존성·변경하지 않을 영역. -->

## Acceptance Criteria

<!-- AC1, AC2처럼 ID를 부여하고 검증 가능한 조건을 작성합니다. -->

## Test Scenarios

<!-- AC별 정상·오류·경계·회귀 시나리오, 테스트 명령과 수동 검증 방법. -->

## Observability

<!-- 운영 로그·진단·확인 명령. 비밀값을 남기지 않는 방식. -->

## Deployment / Dogfooding Plan

<!-- 후보 배포 대상, 배포 승인 범위, 백업·마이그레이션·롤백, smoke test, 실사용 기간과 수용 기준. 실제 사용 확인 뒤 Merge합니다. -->

## Design Decisions

<!-- 선택한 방식, 대안, 이유, 비용·운영 위험. -->

## Design Review

단계: **Planning**. 미결정 제품·설계 질문이 없어지면 Human에게 검토를 요청합니다.

- 승인한 Human:
- 승인 근거 (Issue 댓글 또는 직접 승인 기록):
- 승인된 설계 버전 / 본문 갱신 시각:

<!-- 위 승인 정보를 Agent가 꾸며 작성하지 않습니다. Human 승인 뒤에만 Projects Status를 Ready for Implementation으로 변경합니다. -->
