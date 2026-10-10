# Verification Report — #8 생활 기록 오프라인 검증

## Context

- Issue / 승인 설계: [#8](https://github.com/msaltnet/my-nanobot-rpi/issues/8), 상세 실행 설계 v1. 2026-10-09 KST Human이 승인 대상 안내 직후 “진행해”라고 응답한 근거를 본문에 기록했다. 유일한 Ready for Implementation 라벨을 확인했다.
- 브랜치: `codex/issue-8-tracking-validation`. 제품 기준 SHA `96f8b344519494cea5fd127dbe8818404fce3182`, 고정 nanobot `1bb712d3488915ca4ed9ccc1a93067ff722f5ab9`.
- 구현자: `tracking_tests`; Windows / Python 3.13.9 / 격리 worktree 전용 venv. `python -m pip install -e ./nanobot -e ".[dev]"` exit 0, editable 설치가 해당 checkout을 가리킴을 확인했다. uv는 없어 표준 venv를 사용했다.
- 범위: 테스트 1파일, 보조 실행 계획, 이 보고서와 색인. 제품·schema·설정·스킬·deploy·gitlink 변경 없음. 테스트 소스 commit은 4b184e868dcb058cdc5a45fa6d0c8afe641a4af1이다. 최종 보고서 포함 후보의 SHA/별도 Tester·Reviewer 기록은 연결 PR에서 확정한다.
- 신규 테스트는 socket/DNS/HTTP·AsyncClient와 임시 경로 밖 Storage 진입을 차단한다. parser·Telegram은 fake, DB·trigger·lock·reopen 및 session은 임시 합성 데이터다. 실제 사용자 데이터·운영 서버를 조회하지 않았다.

## Test Report

아래 PASS는 승인된 **오프라인 재현·테스트 보강 산출물**의 성공이다. 알려진 위험 동작을 재현하는 테스트 성공이 제품 안전성 PASS를 뜻하지 않는다.

| AC | 시나리오 | 명령 또는 재현 절차 | 실제 결과 / 근거 | PASS / FAIL / BLOCKED |
|----|----------|--------------------|------------------|-----------------------|
| AC1 | 4 schema reopen·same-date overwrite·zero/False | `test_four_schemas_survive_reopen_and_one_date_is_overwritten` | 실제 SQLite 재개 후 값 보존, 날짜별 메모 1행 갱신 | 오프라인 PASS |
| AC1 | 삭제 cascade·무관 데이터 보존 | `test_delete_cascades_only_target_records_and_preserves_news` | 삭제 대상 record 제거, 다른 tracking/news/briefed sentinel 보존 | 오프라인 PASS; 운영 삭제 미수행 |
| AC1 | invalid 항목·old schema initialize·음주 환산 | 기존 items/storage migration/alcohol/records 테스트 | 기존 정상/검증 경계 회귀 통과. 새로운 건강 기준을 만들지 않음 | 해당 기존 표본 PASS; 운영 데이터 보존 BLOCKED |
| AC2 | 날짜가 있는 부분/부정 답변·fake 날짜 parser→CLI→DB | `test_date_qualified_partial_button_saves_only_named_item`, `test_fake_parser_date_flows_through_per_item_cli_to_sqlite` | 명시 날짜에 named 항목만 저장, 무관 항목 보존. fake가 날짜 해석을 공급하므로 자연어 이해 검증은 아님 | 오프라인 handoff PASS; 실제 대화 BLOCKED |
| AC2 | fake timeout 및 list/null parser 응답 | `test_fake_parser_timeout_does_not_create_record`, `test_fake_parser_top_level_non_object_raises_attribute_error` | timeout 저장 없음; top-level 비객체 JSON은 AttributeError 재현 | 재현 PASS; 실제 모델 응답 미관찰 |
| AC3 | 묶음 둘째 저장 실패 | `test_batch_second_save_failure_leaves_first_commit_and_no_second_success` | SQLite trigger로 둘째 실패, 첫 commit 보존, 둘째 성공 문구 없음 | 재현 PASS; 실제 agent 부분 성공 응답 BLOCKED |
| AC3 | DB lock·저장 뒤 advice 실패 | `test_locked_sqlite_write_returns_no_success_and_preserves_record`, `test_advice_failure_after_commit_leaves_saved_record_and_success_line` | 실제 BEGIN IMMEDIATE+짧은 timeout에서 새 row/성공 문구 없음. advice 예외에서는 저장·성공 문구 후 command 예외 | 재현 PASS; advice 실패 정책 미수용 |
| AC3 | follow-up 실패 | 기존 `test_record_command_keeps_save_success_when_follow_up_fails` | 기존 저장 성공 유지 회귀 | 기존 표본 PASS |
| AC4 | 7/30일 start-1/start/ref/ref+1 및 통계 | `test_period_start_end_and_future_row_pollute_summary` | start-1 제외, start/ref 포함, ref+1도 포함되어 2/3=66%로 오염, 실제 advice의 7/30일 수행 횟수에도 미래 행 포함 | 결함 재현 PASS; 기간 정책 수정 미수행 |
| AC4 | False/NULL/absence·기록일 분모 | boolean false/missing·null 테스트 및 기존 summary/advice 표본 | False/NULL은 record로 존재하며 performed 아님; 분모는 기록 수. 빈 기록·다른 schema·7/30일 조언은 기존 표본 대조 | 오프라인 PASS; 실제 톤/내용 수용 BLOCKED |
| AC5 | same-window 반복/DB reopen | `test_repeated_scheduled_window_resends_after_database_reopen` | 08:00→08:01 KST, 같은 DB 재개 후 fake send 2회 | 결함 재현 PASS |
| AC5 | send 뒤 state 저장 실패 | `test_send_then_state_failure_allows_duplicate_after_restart` | fake send1회 후 pending 저장 실패; pending없음, 재시작 fake send 추가1회 | 불확실성 재현 PASS; 동시 실행/실수신 BLOCKED |
| AC5 | UTC·naive KST·exclusive window start | `test_schedule_window_timezone_and_exclusive_start` | UTC 23:00=KST08:00 및 naive08:00 발송,08:30은 슬롯 제외 | 오프라인 PASS |
| AC5 | HTTP/JSON 거절·timeout | sender rejected/timeout 테스트 | HTTP401 또는200/ok=false에서도 session+pending/last_asked 갱신. timeout에서는 outbound 기록 없음 | 결함 재현 PASS; 실제 Telegram BLOCKED |
| AC5 | retry·pending 대상 날짜·키보드·중복 응답 억제 | 기존 dispatcher/reply_tool 테스트 | fake 경계 회귀 통과. retry의 같은 슬롯 처리와 scheduled 반복 결함은 구분 | 기존 표본 PASS; 실제 UI/수신 BLOCKED |
| AC6 | 재현 결함 분리 | 아래 후속 Issue 기록 및 PR 링크 | 재현·영향·제안 AC·승인 필요성을 추적. 제품 수정은 별도 승인 | 후속 #16–#20 Open 기록 완료; 수정·실사용 BLOCKED |
| AC7 | 외부 영향·운영 관찰 | 차단 fixture·실행 명령 범위 | 추가 유료 LLM0, 실제 Telegram0, 운영 DB 쓰기/배포/중단0 | 오프라인 범위 PASS; 운영 관찰/최종 수용 BLOCKED |

### Regression

전용 venv의 python으로 실행한 구현자 자체 검증:

- 기준선 `python -m pytest tests/msalt/ -q --tb=short --basetemp=.pytest_cache/issue8-baseline`: 200 passed / exit0.
- 신규 `python -m pytest tests/msalt/tracking/test_offline_validation.py -q --tb=short --basetemp=.pytest_cache/issue8-task1-r1-new`: 23 passed / exit0.
- 전체 `python -m pytest tests/msalt/ -q --tb=short --basetemp=.pytest_cache/issue8-task1-r1-full`: 223 passed / exit0.
- 새 파일 Ruff check 및 format --check: PASS / exit0.
- 초기 비승격 테스트 실행의 basetemp 권한 오류는 환경 장애였으며 승격 후 새 임시 경로로 재검증했다. 실패를 PASS로 재사용하지 않는다.
- 이 보고서의 구현자 결과는 최종 후보의 독립 검수를 대신하지 않는다. 현재 후보 SHA의 Tester/Reviewer 실행과 diff --check는 연결 PR에 기록한다.

### Result

승인된 오프라인 범위 구현자 검증 PASS. 전체 #8은 AC2 실제 대화, AC3 수정/응답 정책, AC5 실제 알림/수신, AC6 후속 수정, AC7 관찰·Human 수용이 남아 **미완료**다.

## Agent Review Report

### Scope

Issue #8 승인 v1, 제품 기준 SHA 대비 신규 테스트·보조 계획·보고서·색인, 관련 tracking/storage 및 nanobot session 경계. 별도 컨텍스트 Task reviewer는 테스트 전달물을 먼저 검토하고 최종 Reviewer는 커밋된 전체 후보를 직접 확인한다.

### Findings

최종 후보의 독립 Tester/Reviewer, SHA, 실제 명령, Critical/Major/Minor 및 PASS/FAIL/BLOCKED 판정은 연결 PR의 현재 기록을 기준으로 한다. 작성 시 미완료인 검증을 PASS로 표시하지 않는다. 체크 범위는 승인 일치·임시 데이터 보존·실패/중복/KST·비밀값/자원·유지보수·회귀다. 제품 결함 공개와 검증 산출물 리뷰 결함을 구분한다.

## Human Review Handoff

- 미래 행이 과거 기준일의 통계를 바꾸는지, scheduled 같은 슬롯 재실행과 발송 후 상태 저장 실패가 어떻게 중복되는지, sender 거절이 기록/상태에 어떻게 나타나는지 확인한다.
- parser fake dates의 성공은 실제 agent 문맥 이해를 증명하지 않는다. 실제 단답/묶음/부정/버튼의 저장 결과는 별도 승인된 실제 흐름에서 확인한다.
- 이 PR은 `Related to #8`로 연결하고 전체 AC를 삭제하거나 Issue를 자동 종료하지 않는다. 테스트/문서 배포·Dogfooding N/A는 Human 수용 전 제안이다.
- 실제 대상·고정 SHA·비식별 표본·기간·발송/API 한도·백업/복귀·비용 측정을 승인받은 뒤 관찰한다. #7/#13/#14는 다른 세션 담당이며 임의 변경하지 않는다.
- 제품 결함 수정·운영 배포·병합은 이번 승인에 포함하지 않는다.


### Checklist

- 승인 설계·범위·AC: v1 오프라인 범위, 원래 AC1–7 유지. 최종 독립 검수는 연결 PR 기준.
- 데이터 보존·마이그레이션: 임시 SQLite만 사용, 제품 및 schema 변경 없음.
- 오류 경로·중복·시간대: 실패 주입, 재시작, KST/UTC 표본 재현. 동시 실행 미검증.
- 비밀값·자원: 합성 token/chat, 실제 외부 호출 0. 유료 비용 및 운영 자원 변경 없음.
- 유지보수·회귀: 신규 테스트 23개, 전체 223개 구현자 통과. 보고서가 제품 안전성 PASS를 주장하지 않음.

### Result

최종 커밋의 독립 Tests / Agent Review 판정은 연결 PR에서 확인한다. 운영 검증 및 Human 수용은 BLOCKED.

## 후속 Open Issues

- [#16 기간 상한·통계·조언](https://github.com/msaltnet/my-nanobot-rpi/issues/16)
- [#17 예약 슬롯·재시작 중복](https://github.com/msaltnet/my-nanobot-rpi/issues/17)
- [#18 Telegram 거절 응답](https://github.com/msaltnet/my-nanobot-rpi/issues/18)
- [#19 비객체 JSON parser](https://github.com/msaltnet/my-nanobot-rpi/issues/19)
- [#20 저장 성공 뒤 advice 실패 응답 계약](https://github.com/msaltnet/my-nanobot-rpi/issues/20)

전체 Issue를 조회해 기존 중복을 확인한 뒤 재현·기준 SHA·테스트·제안 AC·데이터 보존·롤백 고려를 기록했다. 모두 Open이며 수정 설계 승인 또는 Ready 전환을 대신하지 않는다. #20은 실제 사용자 재시도 영향이 미확인인 응답 정책 조사도 포함한다.
