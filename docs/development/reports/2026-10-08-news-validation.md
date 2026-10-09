# Verification Report — #7 뉴스 오프라인 검증

## Context

- Issue / 승인 설계 버전: [#7](https://github.com/msaltnet/my-nanobot-rpi/issues/7), 상세 실행 설계 v1. 2026-10-08 KST Human 직접 채팅 “승인”; 본문에 승인 근거 및 유일한 Ready for Implementation 라벨을 기록했다.
- 브랜치: `codex/issue-7-news-validation`.
- 제품 기준 SHA: `d76da7162790d50d8b94f38f66d6cfdbec93c911`.
- 테스트 검증 SHA: `d784c80357205088d6ec1acbea23b5e0bf141126`. 보고서 추가 후 최종 후보 SHA의 독립 Tests / Agent Review는 연결 PR에 기록한다. 이 보고서 자체가 최종 후보 검증을 대신하지 않는다.
- nanobot: 기존 gitlink `1bb712d3488915ca4ed9ccc1a93067ff722f5ab9` (v0.3.5)를 격리 checkout에 초기화했다. 참조 변경 없음.
- 환경: Windows, Python 3.13.9, worktree 전용 venv. 지정 개발 설치 `python -m pip install -e ./nanobot -e ".[dev]"` exit 0. nanobot/msalt import가 이 격리 checkout을 가리킴을 확인했다. Linux / Python 3.11·3.12는 로컬 미실행이며 CI 결과를 별도로 확인한다.
- Implementer: `news_tests`, `delivery_tests`; 독립 Tester: `independent_tester` (별도 컨텍스트). 아래 테스트 SHA를 직접 검증했다. 최종 보고서 후보의 Tester 재확인 및 Reviewer 결과·SHA는 연결 PR과 Issue 진행 기록에 남긴다. 단일 컨텍스트 자기 점검을 독립 PASS로 표시하지 않는다.
- 범위: 테스트 2개 파일 및 보고서/색인. 제품·schema·스킬·cron·submodule 참조 변경 없음. 합성 SQLite, fake 네 수집 경로/OpenAI/발송 경계만 사용한다. 새 테스트는 socket/DNS 접근을 차단하고 뉴스 CLI의 기본 운영 DB 진입을 차단한 뒤 임시 DB를 주입한다.

## Test Report

아래 PASS는 **현재 동작의 오프라인 재현·검증 성공**이다. 위험한 동작을 기대값으로 재현한 테스트의 성공을 제품 안전성 PASS로 해석하지 않는다.

| AC | 시나리오 | 명령 또는 재현 절차 | 실제 결과 / 근거 | PASS / FAIL / BLOCKED |
|----|----------|--------------------|------------------|-----------------------|
| AC1 | 네 수집 경로 정상 / 한 경로 예외 / 전부 빈 결과 | `test_four_collector_paths_have_isolated_results` | 각각 4/3/0개 합성 URL 저장, 모든 경로 호출; 한 소스 예외가 다른 결과를 막지 않음 | 오프라인 재현 PASS; 실제 소스 상태 BLOCKED |
| AC1 | SQLite insert 실패 | `test_insert_failure_commits_prefix_and_aborts_rest_characterization` | 실제 SQLite trigger로 둘째 기사 실패; 첫 기사는 commit, 나머지 저장 중단, 예외 전파 | 재현 PASS; 부분 저장은 알려진 제한 |
| AC2 | URL 소스/DB 중복, 반복 수집 | `test_source_and_database_url_duplicates_keep_first_payload` | 첫 payload 보존, 반복 실행 추가 저장 0 | PASS |
| AC2 | 07/14/20 KST 시작 경계·오래된/발행일 없는/이미 briefed 기사 | `test_kst_schedule_query_boundary_and_exclusions` (3개) | 시작과 +1초 포함, -1초/2021 기사/NULL 발행/briefed 제외 | PASS |
| AC2 | category별 10개 제한 | `test_category_cap_marks_only_rendered_articles` | 3개 category×12개 중 최신 30개만 출력·mark; 나머지 6개 재선택 가능 | PASS |
| AC2 | keyword 검색·주간 요청 현재 한계 | `test_keyword_search_includes_old_articles_and_over_ten_without_marking`; CLI/뉴스 스킬 직접 읽기 | 2021 합성 매칭 기사 12개 전부 출력, 2020 이전 제외, briefed 포함. 전용 주간/기간/개수 인자 없음 | 조사/재현 PASS; 새 검색 정책 미승인 |
| AC3 | 세 예약 설정 및 upstream 레거시 변환 | `test_three_news_cron_schedules_configuration_only`; `test_legacy_cron_normalization_preserves_route_enabled_and_kst` | 07/14/20 Asia/Seoul; 합성 수신자 경로·enabled·tz 보존, 변환 멱등성 | 설정 검증 PASS |
| AC3 | 실제 각 시각 실행·생성·발송·Human 실수신 | 운영 실행 없음 | 어떤 실제 예약/수신 결과도 수집하지 않음 | BLOCKED |
| AC4 | mock LLM API 오류/timeout/빈 응답·plain 모드 | `test_mock_llm_failure_falls_back_and_marks_plain_output`; `test_plain_mode_makes_no_llm_call` | plain 원문 fallback; plain은 LLM 0회. 실패 fallback도 출력 URL을 mark | 재현 PASS |
| AC4 | 생성 후 fake 발송 실패, DB 재시작 | `test_generated_state_survives_fake_failed_send_and_suppresses_restart_retry` | 발송 전 durable mark; 실패 뒤 새 Storage에서도 해당 기사 제외 | 재현 PASS; 제품 누락 결함 [#13](https://github.com/msaltnet/my-nanobot-rpi/issues/13) 미해결 |
| AC4 | mark 저장 실패 | `test_mark_failure_returns_no_text_and_restart_retry_is_available` | 실제 SQLite trigger 실패로 텍스트 반환 없음/mark 없음; 실패 제거 뒤 새 Generator 재시도 가능 | 재현 PASS |
| AC4 | retry 성공/소진/nonretryable/취소 | `test_delivery_boundary.py`의 fake ChannelManager 검증 | 최대 3회, sleep 1/2초; 성공·소진·nonretryable 모두 None 반환. send/backoff 취소는 전파 | 제한된 mock PASS; 실제 Telegram timeout/부분 발송/재수신 BLOCKED |
| AC4 | 스킬 collect → briefing | `test_collect_then_cli_briefing_collects_all_four_paths_twice` | 각 경로 2회 호출, URL 4개만 저장. 실제 API 비용은 측정하지 않음 | 재현 PASS; [#14](https://github.com/msaltnet/my-nanobot-rpi/issues/14) 미해결 |
| AC4 | 전달 확정·재전송 정책 Human 수용 | 아래 선택지와 후속 #13 | 정책을 임의로 바꾸지 않았음 | BLOCKED |
| AC5 | 확인된 결함 분리 / 후속 수정 검증 | #13, #14는 Open으로 생성 | 재현·영향·제안 AC·회귀와 후속 승인 필요성을 각 본문에 기록. 수정 미수행 | 이슈 분리 PASS; 수정·실사용 BLOCKED |
| AC6 | 승인된 첫 오프라인 실행의 외부 영향 한도 | fake/임시 DB·차단 fixture, 명령 범위 확인 | 실제 유료 LLM/Telegram 발송 0, 운영 DB 쓰기/중단/배포 0. 의존성 설치·GitHub 기록은 개발 준비/검수 작업 | 오프라인 범위 PASS |
| AC6 | 운영 기간·비용/수신 한도·실제 관찰·최종 수용 | 운영 실행 없음 | 운영자가 구체 범위를 승인하고 Human이 수용해야 함 | BLOCKED |

### Source / Delivery Inspection

- root `NewsCollector`는 RSS/official/search/fallback의 수집 예외를 각 경로에서 격리한다. 저장 예외는 격리하지 않으며 건별 commit이므로 prefix가 남는다. 원자성/계속 처리 여부를 새 요구사항으로 임의 확정하지 않고 제한을 공개한다.
- root `BriefingGenerator`는 기본 발행 시각·briefed 제외 후 category별 최대 10개 출력 URL을 반환 전에 mark한다. 발송 결과와 연결되는 ack가 없어 #13으로 분리했다.
- 고정 upstream `cron/service.py::_normalize_agent_turn_job`는 레거시 channel/to/deliver를 session-bound 경로로 변환한다. `gateway_runtime.py::on_cron_job` → `cron/bound_runner.py::run_bound_cron_job` → agent의 session turn으로 진행한다. cron의 ok는 실제 사용자 수신 증거가 아니다.
- 고정 upstream `channels/manager.py::_send_with_retry`는 fake 검증에서 재시도 소진과 nonretryable 예외를 로그 후 None으로 반환한다. 이 함수의 반환을 뉴스 전달 확정 근거로 사용할 수 없다. 실제 Telegram plugin의 부분 전송·네트워크 timeout·API 응답 및 Human 실수신은 이번 검증에 포함되지 않았다.
- 뉴스 keyword 검색은 2020 이후 DB 조회와 title/summary 필터이며 개수·종료 기간 제한이 없다. 주간 자연어 요청을 정확한 최근 7일 전용 검색으로 보장하지 않는다. 기간/개수 정책 변경은 별도 승인 대상이다.

### Retransmission / Search Decisions for Human Review

#13 Planning에서는 (1) 생성/발송 결과 분리 및 알려진 실패만 재시도, (2) 결과 불확실한 timeout·발송 후 저장 실패를 별도 상태로 두고 수동 재전송 여부 확인, (3) 자동 재시도 선택 시 중복 가능성과 실행/발송 한도 명시를 비교해야 한다. 단순히 mark를 늦추는 것만으로 동시 실행·결과 불확실성·exactly-once가 해결되지는 않는다. 기존 이력 보존과 migration/복귀가 필요하다.

검색은 현행 전체 keyword 조회 유지 또는 기간·개수·정렬/페이징 인자 추가를 비교한다. 주간 범위·KST 경계·미발행 기사 포함을 확정해야 한다. 이번 검증 승인으로 이 선택지가 수용된 것은 아니다.

### Regression

worktree 전용 venv에서 실행했다. 일반형 명령의 `python`은 그 인터프리터다.

- 기존 뉴스 기준선: `python -m pytest tests/msalt/news/ -q --basetemp=<새 격리 임시 경로>`: 40 passed, exit 0.
- 신규 SQLite/뉴스 검증: `python -m pytest tests/msalt/news/test_offline_validation.py -q --basetemp=.pytest_cache/issue7-parent-offline`: 18 passed, exit 0.
- 신규 upstream 전달 경계: `python -m pytest tests/msalt/news/test_delivery_boundary.py -q --basetemp=.pytest_cache/issue7-delivery`: 11 passed, exit 0.
- 전체 회귀: `python -m pytest tests/msalt/ -q --basetemp=.pytest_cache/issue7-final-source`: 200 passed, exit 0.
- 새 파일 `python -m ruff check ...`: All checks passed, exit 0. `git diff --check`: exit 0.
- 합성 tracking record를 같은 DB에 유지한 채 뉴스 수집·중복·실패 검증 후 값과 항목이 보존됨을 확인했다. 운영 데이터는 읽거나 변경하지 않았다.
- 초기 기본 tmp 경로 권한 오류, 전역 Typer/Click 충돌·filelock 누락은 환경 장애였다. 접근 가능한 격리 basetemp 및 worktree venv 설치로 재검증했다. 실패 실행을 PASS로 재사용하지 않았다.

### Result

승인된 **오프라인 재현·테스트 보강 범위**의 구현자 검증 및 독립 Tests PASS. `independent_tester`가 테스트 SHA `d784c80357205088d6ec1acbea23b5e0bf141126`의 Issue·diff를 직접 확인하고 뉴스 69개 (exit 0), 전체 회귀 200개 (exit 0), diff --check (exit 0)를 독립 재실행했다. 독립 명령은 `python -m pytest tests/msalt/news/ -q --basetemp=.pytest_cache/issue7-independent-tester-news`와 `python -m pytest tests/msalt/ -q --basetemp=.pytest_cache/issue7-independent-tester`다. Agent Review는 아직 완료 선언하지 않는다. 최종 후보 결과는 연결 PR을 기준으로 한다.

전체 #7 AC3·AC4·AC5·AC6의 실제 수신·정책 수용·결함 수정·운영 관찰이 남아 있어 **전체 Issue BLOCKED / 미완료**다. 이번 산출물만으로 #7을 종료하거나 병합하지 않는다.

## Agent Review Report

### Scope

비교 기준 `d76da7162790d50d8b94f38f66d6cfdbec93c911`, 테스트 SHA `d784c80357205088d6ec1acbea23b5e0bf141126`. 최종 보고서 후보의 독립 Reviewer는 Issue/승인·전체 diff·실행 결과를 직접 읽고 검토 SHA를 연결 PR에 기록한다.

### Findings / Checklist / Result

독립 리뷰는 이 보고서 작성 시 미완료다. 실제 수행 전 PASS 체크를 채우지 않는다. 최종 후보의 승인 범위 일치, 임시 DB 격리, 오류·중복·KST, 비밀값·자원·테스트 누락·보고서 과장 여부와 Critical/Major/Minor 결과를 연결 PR에 명시한다. 제품 결함의 공개 기록은 검증 산출물 리뷰 FAIL와 구분한다.

## Human Review Handoff

#13의 pre-send mark → fake 실패 → 재시작 제외 및 #14의 수집 2회 재현을 테스트/후속 이슈와 대조한다. 코드와 운영 설정이 변경되지 않았고 데이터가 합성이었는지 확인한다. 이 PR의 테스트/문서 배포는 N/A 제안이며 Human 수용 전 확정하지 않는다.

운영 관찰은 대상·고정 SHA·수신자·기간·발송/API 예산·데이터 영향·백업/복귀를 별도 승인한 뒤 세 예약의 실행/생성/발송/실수신을 각각 확인한다. 후속 결함 수정은 해당 Open Issue의 Planning·Human 설계 승인·Ready 이후다. Human PR Review·실사용/제한 수용·명시적 병합 승인 전에는 merge하지 않는다.
