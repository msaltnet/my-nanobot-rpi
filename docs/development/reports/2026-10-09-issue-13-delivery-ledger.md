# Verification Report — Issue #13 delivery ledger v1.1

## Context

- Issue / 승인 설계 버전: #13 v1.1. Human의 “승인할께”와 유일한 Ready for Implementation 상태를 부모 작업이 확인했다. 구현·후보 준비 범위이며 실제 발송·운영 배포·병합 승인은 포함하지 않는다.
- 브랜치: `codex/issue-13-delivery-ledger`.
- 검증한 제품 코드/테스트 SHA: `c7bb3fb292907b91b2a53f42af6cbd01b7e649e8`; 비교 base `1c1d05e1b34098c22107b616e077e5a2018663ed` (#14 포함). 이 보고서는 제품 코드 변경 없는 후속 문서 커밋이다. 독립 검증은 보고서를 포함한 최종 후보 SHA에서 수행한다.
- nanobot: [관리 fork](https://github.com/msaltnet/nanobot) immutable gitlink `13c7435eb85577d3004ee4bbee5fcb4fbdcc203d`. 원격 가용성 및 이 SHA의 독립 upstream Tester 315 PASS / Reviewer 회귀 43 PASS·지적 없음은 부모 작업에서 확인한 별도 근거다. 이 보고서는 upstream 소스를 수정하지 않았다.
- 환경: Windows, Python 3.12.7, worktree 전용 editable root/dependency 설치. 새 테스트는 임시 SQLite/workspace, socket/DNS 차단, fake 모델/HTTP를 사용한다. subprocess crash 검증도 실제 sender와 프로세스 내부 네트워크 차단을 사용한다.
- 수행자: Implementer 자체 검증, 별도 컨텍스트 test_root_13 및 review_root_13. 독립 최종 판정 대상은 e3c18126a876e2474e08795ee2c6423906222f8b이며, 본 후속 변경은 판정 결과를 기록하는 문서 수정이다.

## Test Report

| AC | 시나리오 | 명령 또는 재현 절차 | 실제 결과 / 근거 | PASS / FAIL / BLOCKED |
|----|----------|--------------------|------------------|-----------------------|
| AC1 | 생성과 전송 확정 분리; default/legacy True preview가 mark하지 않음 | test_briefing, test_offline_validation, test_delivery | 기존 실패 재현 7건을 승인된 안전 기대값으로 변경. 실제 ACK 전 mark 0; 전체 ACK 후 정확한 snapshot URL만 확정 | 독립 오프라인 PASS |
| AC2 | 알려진 미발송 재시도와 명시적 수동 복구 | test_delivery, test_delivery_hardening | 최초 포함 최대 3 POST, 1/2초 backoff, unknown 자동 재발송 0; manual은 ACK skip, confirm-uncertain 필수, observation window 전체 1회; no-payload 거부·regenerate 동일 ID | 독립 오프라인 PASS |
| AC3 | 경쟁·재시작·부분 전송·저장 실패·충돌과 기한 | 세 delivery 테스트 모듈 | 실제 SQLite slot/active reservation 경쟁; 잘못된 attempt ACK/reject 무변경; lease 복구와 stale owner fencing; 실제 child abrupt exit 5시점; final insert trigger 원자 rollback·ACK 유지·POST 없는 수동 finalize | 독립 오프라인 PASS |
| AC4 | legacy 기사/briefed/생활 데이터 보존·migration·복귀 | test_delivery_hardening 및 기존 storage/tracking 회귀 | additive migration 재실행, 새 DDL 각 실패 지점 rollback; 누락/약화 index·slot UNIQUE 거부; 임시 backup/restore·코드 복귀 후 최신 생활 기록 유지 | 독립 오프라인 PASS |
| AC5 | 설치된 tool·현재 대상/thread·USER 및 실제 bound-cron SYSTEM 경계 | test_delivery_integration, test_news_runtime | 실제 installed entry point/API1, 세 slot 스킬 consumer→실제 tool/loop, USER/cron sent/failed/unknown/partial/empty/generation failure/cancel, 잘못된 allowFrom/target/sender/token, unsupported runtime 외부 작업 0 | 독립 오프라인 PASS |
| AC6 | 불변 payload/URL/parts, 자원 한도, 외부 실패 | test_delivery_hardening, test_delivery 및 전 뉴스 회귀 | payload·manifest·part hash 검사, URL 보존 분할/overflow, 5종 누적 quota race/restart, summary reservation, SDK retries0/10초 timeout, 실제 BotAPI trace 분류·토큰 log redaction, 종료 가능한 생성 child deadline/cancel | 독립 오프라인 PASS; 금액 상한은 #7 별도 |
| AC7 | 최종 root/gitlink 독립 검수·Python 3.11/3.12 Linux·운영 수용 | CI에 installed Python 환경/두 버전 matrix/고정 upstream ownership 테스트 연결 | 로컬 3.12 자체 검증 완료; 독립 root Gate PASS; Linux/3.11 CI 실행·Human smoke/실수신·배포·merge 미수행 | **BLOCKED** |

### Regression

Worktree venv의 실제 실행 명령과 결과:

```text
.venv/Scripts/python.exe -m pytest tests/msalt/ -q -p no:cacheprovider --basetemp=.superpowers/root-final-manifest-regression --tb=short
321 passed in 37.25s; exit 0

.venv/Scripts/python.exe -m pip check
No broken requirements found; exit 0

.venv/Scripts/python.exe -m ruff check msalt/news/delivery.py msalt/news/delivery_schema.py msalt/news/sender.py msalt/news/coordinator.py msalt/news/reply_tool.py msalt/news/delivery_cli.py msalt/news/briefing.py msalt/news/cli.py msalt/cli.py msalt/storage.py tests/msalt/news/test_delivery.py tests/msalt/news/test_delivery_integration.py tests/msalt/news/test_delivery_hardening.py tests/msalt/news/test_news_runtime.py tests/msalt/news/test_briefing.py tests/msalt/news/test_offline_validation.py
All checks passed; exit 0

git diff --check
git diff --cached --check
exit 0
```

Windows linked worktree Git에는 process-local `GIT_WORK_TREE`를 해당 checkout으로 지정했다. 공유 Git 설정은 변경하지 않았다. 설치 확인은 root와 nanobot import가 모두 해당 isolated checkout에 있는지, API version 1인지, 설치된 `news_briefing = msalt.news.reply_tool:NewsBriefingTool` entry point가 정확히 하나인지 확인했다. nanobot checkout은 위 gitlink로 clean이다.

초기 WIP의 224 PASS/기존 기대값 7 FAIL과 공백 실패는 과거 미완료 근거이며 이번 결과로 대체된다. TDD RED→GREEN 근거에는 예약 재사용/attempt identity/본문 손상/empty 최종 상태/readonly show/무한 retry_after, 없는 coordinator·entrypoint·CLI, 약화 schema, HTTP 상태 불일치·토큰 로그, durable claim 사이 deadline, late ACK, URL manifest 손상(POST 전/후), 수동 retry 누적 한도가 포함된다. 일시적 test temp 권한 및 editable backend 환경 문제는 명시적 임시 경로/정상 editable 설치로 해결했고 제품 실패 PASS로 계산하지 않았다.

### Result

제품 코드 SHA 및 문서 포함 최종 후보 e3c18126a876e2474e08795ee2c6423906222f8b에 대해 **독립 Tests PASS / Agent Review PASS**. Tester는 전체 회귀 321 passed in 41.00s, Reviewer는 별도 전체 회귀 321 passed in 41.40s를 확인했다. 두 역할 모두 최종 후보와 c7bb3fb 사이 소스·테스트·gitlink 변경 없음 및 diff --check를 확인했다. Linux Python 3.11/3.12 CI는 후보 PR에서 확인하고, 운영 실행·실수신 수용·Human Review·명시적 병합 승인은 후속 Gate다. 미실행 운영 검증과 전체 AC7은 **BLOCKED**로 유지하며 최초 PR 생성의 선행 조건으로 혼동하지 않는다. 소스·테스트 수정이 생기면 영향 범위를 다시 검증한다.

## Agent Review Report

### Scope

위 base부터 제품 코드 SHA까지 root 23개 파일. 원장/마이그레이션/sender/coordinator/tool/operator CLI/preview/skill/tests/docs/CI/gitlink 포함. upstream 소스, 일반 ChannelManager, tracking sender, gateway 생명주기 변경 없음.

### Findings

| 심각도 | 파일 / 위치 | 문제와 근거 | 수정 제안 | 해결 여부 |
|--------|-------------|-------------|-----------|-----------|
| Major | delivery_schema | 컬럼만 검사하면 같은 이름의 비유일 index 또는 slot UNIQUE 누락을 허용 | 정규화된 table/index 전체 정의를 쓰기 전에 검증 | 3 RED 후 수정·회귀 PASS |
| Major | sender | durable claim 중 deadline 만료 후 즉시 POST가 실행될 수 있음 | claim 뒤 명시적 잔여시간 검사·late 실제 ACK는 보존 후 unknown | 2 RED 후 수정·회귀 PASS |
| Major | sender | HTTPX INFO가 credential-bearing Telegram URL을 기록 | 해당 API 로그만 redaction; 예외 원문을 원장에 저장하지 않음 | RED 후 실제 adapter/log 검증 PASS |
| Major | delivery | payload와 URL manifest 사이 연관이 손상되면 잘못된 최종 이력 가능 | manifest hash 및 매 claim/최종 transaction에서 snapshot 재검증 | POST 전/후 RED 후 수정·회귀 PASS |
| Major | reply_tool | custom agent workspace에서 기존 CLI DB와 다른 DB를 선택할 가능성 | 기존 MsaltConfig.db_path를 tool/preview/operator 공통 기준으로 보존 | 경로 일치·미생성 확인 PASS |

### Checklist

- 승인 설계·범위·AC: v1.1 공개 ownership API만 사용; tool argument는 time_of_day만, retry 권한 없음.
- 데이터 보존·마이그레이션: 기존 행 소급 재분류/삭제 없음, active unknown 예약 유지, 원자 migration/최종 mark.
- 오류·중복·시간대: KST slot 키, UTC/wall lease+공유 monotonic action deadline, API ACK와 Human 증거 분리.
- 비밀·자원·동시성: raw 예외/토큰 비기록, status 대상/본문 비노출, SQLite reservation/quota 선확정, bounded generation process 회수.
- 운영 가능성: readonly list/show, operator retry/resolve/regenerate, 현재 DB 보존 rollback 문서화.
- 회귀: 독립 Tester 전체 321 PASS 및 Reviewer 전체 321 PASS. Python 3.11/Linux는 후보 PR CI에서 확인한다.

### Result

별도 컨텍스트 review_root_13이 최종 후보 e3c18126a876e2474e08795ee2c6423906222f8b 전체 diff와 승인 Issue를 직접 확인하여 **독립 Agent Review PASS**. 미해결 Critical/Major/Minor 0. 위 지적과 최종 문서 정정은 모두 해결되었다.

## Human Review Handoff

독립 Tester/Reviewer Gate 완료 후 결과 기록만 반영한 문서 커밋을 범위 재확인하고 후보 PR을 준비한다. 배포 전 구체 대상·후보 SHA·작업창·backup/rollback·추가 유료 비용/중단 기준을 승인받고 #7의 smoke/실수신·생활 데이터 보존 수용을 확인한다. 이번 작업은 production DB/설정·서버·실제 모델/검색/Telegram을 사용하지 않았으며 push·root PR·배포·병합을 수행하지 않았다.

운영 제약: 전용 전달 coordinator 동작(명시 regenerate/retry 포함)에 대한 DB 전체 누적 24 생성/72 요약/25 논리 전달/100 part/300 POST, 수동 retry action 1회는 자동 초기화되지 않는다. 독립 CLI preview는 원장을 쓰지 않으므로 이 전달 계수에 포함되지 않는다. preview의 수집·요약 비용과 검색·대화 모델·오케스트레이션을 포함한 총비용 강제 차단은 #7 budget preflight에서 별도 검증해야 한다. subprocess 종료의 bounded 정리 시간은 최대 4초이며 외부 요청이 이미 처리·과금되었는지는 보장하지 않는다. 정확히 한 번 전달 또는 US$5 총액 차단을 이 기능만으로 주장하지 않는다. generation worker는 동작 상한/취소 시 종료되어 이후 요청을 계속하는 thread를 남기지 않는다.

### Independent verification evidence

- Tester: 별도 컨텍스트 `test_root_13`; `.venv/Scripts/python.exe -m pytest tests/msalt/ -q -p no:cacheprovider --basetemp=.superpowers/tester-root13-temp` 실행, 321 PASS / 41.00s / exit 0. pip check, 변경 16개 파일 Ruff, installed API1·단일 entry point, source/test/gitlink unchanged, candidate diff check 모두 PASS.
- Reviewer: 별도 컨텍스트 `review_root_13`; Issue v1.1과 base→candidate 전체 diff 직접 검토, 독립 pytest 전체 321 PASS / 41.40s / exit 0. 이전 지적 해결과 최종 문서 범위 확인, 미해결 발견 사항 0.
- 제품·테스트 SHA `c7bb3fb292907b91b2a53f42af6cbd01b7e649e8`; 두 역할 최종 검수 SHA `e3c18126a876e2474e08795ee2c6423906222f8b`; immutable dependency `13c7435eb85577d3004ee4bbee5fcb4fbdcc203d`.
- AC1–6 독립 오프라인 PASS. AC7의 Linux CI 및 운영/Human 항목은 위 판정과 구분한다. 후보 PR의 CI와 배포/실수신 승인 결과는 PR에서 후속 기록한다.