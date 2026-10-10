# Verification Report — 뉴스 통합 후보 준비, 2026-10-10 KST

## Context

- 계약: [#13 v1.1](https://github.com/msaltnet/my-nanobot-rpi/issues/13), [#14 v1](https://github.com/msaltnet/my-nanobot-rpi/issues/14), [#7 v2 및 최신 비용 결정](https://github.com/msaltnet/my-nanobot-rpi/issues/7). 실제 재조회에서 세 Issue OPEN/유일 Ready, #25 OPEN/유일 Open·미승인 보류.
- 기준 main: `3ee7ba93eed9cd3c74dd7334e8367c4d0f28ffab`.
- 제품 후보: PR #24 `4cacca235731240ca51467817f23f7f065988abf`, PR #22 `1c1d05e1b34098c22107b616e077e5a2018663ed` 포함. dependency `13c7435eb85577d3004ee4bbee5fcb4fbdcc203d`.
- 실행 문서 검수 후보: PR #23 `b1647005387036078747d50c7af9e5a963fd916c`. 최신 main과 색인 충돌의 양쪽 보고서 보존, runbook/21slot 양식 및 과거 보고서의 현재 결정 우선 표시.
- 기존 Issue별 worktree와 PR 브랜치를 재사용했다. 루트 사용자 수정, worktree 미추적 준비 파일·계획은 보존했다.
- 금액 guard/비용 예약 원장/fork 비용 capability/공유 대화·기록 차단/새 횟수 제한을 구현하지 않았다. 기존 전달 안전성·호출 ceiling은 유지한다. US$5/US$4는 운영자 비용 관리·관찰 기준이며 앱 자동 차단/절대 청구 상한 보장이 아니다. #25 구현·hard enforcement 증명은 운영 선행 조건에서 제외했다.
- 별도 Tester `tester`, Reviewer `reviewer`. 과거 321/43 PASS는 새 SHA 결과로 재사용하지 않았다. 테스트는 Windows Python/격리 SQLite/fake 모델·HTTP 및 외부 네트워크 차단 경계 사용.

## Test Report

독립 Tester가 실제 승인 본문·후보 diff·설치된 API와 소스를 직접 확인하고 최종 제품 SHA `4cacca2`에서 재실행했다. Python 3.12.7 / Windows.

| AC | 시나리오·근거 | 실제 결과 | 판정 |
|---|---|---|---|
| #13 AC1 | preview/empty/fallback 및 legacy keyword 무확정 | 임시 DB briefed 미변경/재선택 | offline PASS |
| #13 AC2–3 | known-unsent3·unknown0·ACK skip·저장실패·crash/cancel·경쟁/lease/fencing·명시수동 snapshot | delivery/hardening 실제 SQLite/외부fake·runtime assertions | offline PASS |
| #13 AC4 | additive migration 반복·모든 DDL fault rollback·legacy4table·구코드 복귀와 새 tracking delta 보존 | 합성/임시 backup/restore 회귀 | offline PASS; 운영 보존 미실행 |
| #13 AC5 v1.1 | 실제 tool/AgentLoop USER/SYSTEM/cron·claim·주입입력·unsupported | root runtime/integration 및 fork ownership | offline PASS |
| #13 AC6 | 4part/3500·overflow/manifest tamper·deadline·원자 누적 ceiling·LLM/HTTP 실패·tracking | 전체 회귀 경계 assertions | offline PASS; 금액보장 의미 아님 |
| #13 AC7 | 현재 SHA 설치/독립검수·Linux/실수신 | Windows 아래 명령 PASS, 새 Linux CI 별도 기록 | 부분 PASS / 운영 BLOCKED |
| #14 AC1–4 | 실제 세slot 스킬/tool 단일 collect·수동collect·부분실패/빈DB·URL/저장오류·seed 사용자파일 보존 | 최신 main 포함 전체 회귀 | offline PASS |
| #14 AC5 | 통합 및 운영 수용 | PR22 ancestry 및 offline integration PASS | offline PASS / live BLOCKED |
| #7 준비 | 최신 비용결정·Gates/ceiling·21slot9열·모두BLOCKED·상대링크·문서만 변경 | Tester 직접파싱/Issue/diff 검증 | 준비 PASS |
| #7 AC1–6 | 실제소스·21예약·실수신/중복·원문·비용/자원/보존·수용 | 미실행 | BLOCKED |

### Regression

아래 명령의 basetemp는 실제 전용 디렉터리를 지정했으며 공개 기록에서는 개인 경로를 생략한다.

```text
.venv/Scripts/python.exe -m pytest tests/msalt/ -q --basetemp=<isolated-root-test-directory>
# 344 passed, 42.12s, exit 0 (4cacca2)
# cwd nanobot:
../.venv/Scripts/python.exe -m pytest tests/agent/test_delivery_ownership.py -q --basetemp=<isolated-fork-test-directory>
# 43 passed, 33.16s, exit 0 (pin13c7435)
.venv/Scripts/python.exe -m pip check
# No broken requirements found, exit 0
git diff --check 3ee7ba93eed9cd3c74dd7334e8367c4d0f28ffab..HEAD
# product/docs each exit 0
```

importlib.metadata/API 검사에서 API1·news_briefing entrypoint 정확히1개/실제 class load·console entrypoint를 확인했다. 첫 기본 temp 실행은 환경 권한 WinError5로 root104 passed/240 setup errors·fork43 setup errors(exit1)였고 새 전용 temp에서 전체를 다시 실행했다. 최초 API 모듈명 검사 오타도 실제 모듈로 수정해 exit0를 확인했다. 실패를 숨기거나 과거 PASS로 대체하지 않았다.

**Windows 오프라인/문서 준비 Tests PASS.** 현재 후보 Linux3.11/3.12는 push 후 새 CI 결과가 필요하다.

## Agent Review Report

- 독립 Reviewer가 실제 Issue 조회 본문, 두 후보 diff와 fork 소스/API, 전달 원장·sender·coordinator·tool·CLI·schema·설치/CI·테스트를 직접 확인했다.
- 제품 `4cacca2` 및 문서 `b164700` scoped Review PASS, 미해결 Critical/Major/Minor 0.
- 발견/해결: 제품 안내 문서의 잔존 금액 guard 필수조건(Major)을 운영자 비용관리로 수정하고 역사 보고서에 최신 결정 우선 표시; 문장 연결 Minor도 해결했다. 두 수정 후 source/tests/gitlink 불변과 최종 SHA diff를 재검토했다.
- main ancestry/PR22 포함, diff --check exit0, Markdown 상대 링크 product19/docs14 missing0, 21slot 확인.
- 승인 범위·additive migration/현재 DB 유지 rollback·ACK/소유권/Human 수신 구분·unknown 자동0·단일 수집·KST·원자 ceiling/동시성·비밀값 비노출 scoped Review PASS. 실제 운영 백업·설치·수신/수용은 범위 밖이다.

## 현재 운영 읽기 진단

2026-10-10 09:17 KST 기존 지정 OCI 대상에서 최소 allowlist 읽기 진단만 수행했다. 현재 운영 root `4148191789bf7f17dafbc76f7b88ba6c7db9a730` / dependency `1bb712d3488915ca4ed9ccc1a93067ff722f5ab9`, tracked clean. gateway active/running·NRestarts0, tracking/watchdog timer active/waiting·enabled, OS UTC/NTP 동기화 확인. tracking 다음 시각 09:30 KST였으며 안전 작업창은 실행 직전 모든 예약과 다시 대조해야 한다. 서비스 상태는 실제 실행/수신·로그 무오류 증거가 아니다. journal 읽기 timeout 관련 #26은 이 작업에서 해결/무오류로 판정하지 않았다.

## Human Review Handoff

- 실제 #7 AC1–6: BLOCKED. smoke·7일21예약 수신/중복·원문 수용, 최신 writer 정지 일관 백업·전체 격리 복구, 후보 적용·운영자 사용량/비용 관찰 및 최종 수용 미실행.
- 운영 적용 패키지는 고정 root/dependency와 문서 SHA, 기존 비공개 OCI 대상·현재 수신자 재대조, 모든 writer/cron·timezone·작업창, 이전 SHA/설정/workspace/unit/일관 DB 백업과 rollback 명령·검증을 포함한다. 백업은 후보 기동/doctor/seed보다 먼저 수행한다.
- 정지 최대20분, 15분에 중단/복귀 착수. 현재 DB·ACK/unknown·신규 생활 기록을 보존하는 코드/의존성·설정 복귀와 뉴스 중지를 우선한다. 운영 DB 덮어쓰기는 별도 승인. 이전 비활성 timer/job을 켜지 않는다.
- 별도 실행 승인 후에만 수동 smoke 최대3회+7일21예약. 기존 생성24/summary72/configured 검색96/논리전달25/part100/POST300 및 수동retry1 제한을 유지한다. 실패/timeout/retry 포함, counter 자동 초기화 없음. unknown/부분/중복·DB 불일치·자원/실행한도 위반은 뉴스 중지와 운영자 판단.
- 공급자 설정/사용량 조회 방법·관찰 담당 및 US$4 수동 중단/US$5 관리 기준을 비공개 기록한다. 앱 비용 guard 설계 승인을 다시 요구하지 않는다. 구체 실행 승인이 예산 확대를 뜻하지 않는다.
- 이번 작업의 새 유료 API·Telegram 발송·운영 app DB/설정 쓰기·서비스 변경·배포·병합은 0. 운영 적용/발송·최종 Human 수용·명시적 merge 승인 미확보. 준비 PASS로 Issue를 닫거나 merge하지 않는다.
