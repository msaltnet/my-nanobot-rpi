# Agentic Workflow Preparation Implementation Plan

이 문서는 최초 준비 당시의 실행 기록이다. 이후 Human의 보드 없는 진행 지시로 상태 기준이
Issue 라벨로 변경됐다. 현재 규칙은 [개발 워크플로우](../../development/agentic-workflow.md)와
[Issue 상태 관리](../../development/github-issue-workflow-setup.md)를 따른다.

> **For agentic workers:** Use executing-plans to execute the checklist in order. This preparation records the user's supplied operating design; it does not authorize product implementation or cloud deployment.

**Goal:** 사용자가 제공한 두 운영안을 개발에 쓸 수 있는 규칙·템플릿·프롬프트로 만들고 프로젝트 방향을 정리한다.

**Architecture:** Issue 본문을 설계 계약, Projects 세 상태를 구현 가능 여부, PR을 검증·배포·Human 수용 기록으로 사용한다. 실제 GitHub 설정과 로컬 문서 준비를 구분한다.

**Tech Stack:** Markdown, GitHub Issue/PR templates, existing pytest CI, GitHub Projects.

**Spec:** 사용자가 제공한 두 Agentic Development Workflow 운영안. 저장소 적용 결과는 `docs/development/agentic-workflow.md`.

## Global Constraints

- Status는 Open / Planning / Ready for Implementation 세 가지다.
- Human 설계 승인 전 구현하지 않으며 Tests PASS·Agent Review PASS 이후 처음 PR을 생성한다.
- 최신 추가 운영안에 따라 배포·Dogfooding·Human 수용 이후 Merge한다.
- 공개 배포 문서는 RPi/OCI 공통 절차를 제공하고 실제 서버 값은 운영자별로 관리한다. 이번 준비에서 운영 서비스는 변경하지 않는다.
- README의 기존 사용자 수정을 보존한다. 확장 후보를 구현 완료·승인된 큐로 표시하지 않는다.

## Task 1: 개발 계약과 템플릿

- [x] AGENTS.md에 승인·상태·검증·배포·병합 규칙 기록.
- [x] `.github/ISSUE_TEMPLATE/01-open.md`, `02-planning.md`로 초기 문제와 승인 후보 설계 분리.
- [x] `.github/pull_request_template.md`에 현재 SHA의 검증·리뷰 및 배포·실사용 기록 포함.
- [x] `docs/development/agentic-workflow.md`에 단계/담당/작업/산출물/진입 조건과 수정 루프 기록.

## Task 2: 역할별 실행과 제품 방향

- [x] `docs/development/agent-prompts.md`에 Planner·Implementer·Tester·Reviewer·Human 승인·배포·회고 프롬프트 작성.
- [x] `verification-report-template.md`, `lifecycle-report-template.md`에 근거 중심 기록 형식 준비.
- [x] `docs/project-direction.md`에 현재 기능·확장 후보·최종 방향·우선순위 제안 구분.
- [x] README와 과거 PRD에서 최신 방향·워크플로우 문서로 연결.

## Task 3: GitHub 연결과 검증

- [x] GitHub 저장소 및 CLI 인증 접근 확인.
- [x] Projects 권한 부족 확인, `github-project-setup.md`에 실제 미설정 상태와 설정·점검 절차 기록.
- [ ] 보드 URL 확정·권한 확보 후 실제 Projects 필드와 뷰 설정 및 동작 확인.
- [x] 로컬 변경의 링크·템플릿 구조·요구사항 일치·diff 공백 검증 (문서 9개·로컬 링크 35개, 새 파일 11개 공백·코드 블록, Issue 템플릿 메타데이터·필수 섹션 확인).

GitHub 보드 설정이 남은 상태를 완료로 보고하지 않는다. 문서 변경에는 앱 회귀 테스트나 새 실행 프로그램을 추가하지 않는다.
