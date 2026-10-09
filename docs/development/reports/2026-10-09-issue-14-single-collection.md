# Issue #14 v1 Verification Report — Implementer evidence

## Context

- Issue / 승인 설계 버전: [#14](https://github.com/msaltnet/my-nanobot-rpi/issues/14) v1. 2026-10-09 KST Human 직접 메시지로 설계·AC 승인; 유일 상태 라벨 `Ready for Implementation` 확인 내용은 승인된 Issue 본문 스냅샷 기준이다.
- 브랜치 / 검증한 구현 커밋 SHA: `codex/issue-14-single-collection` / `778d3d1c39a5abcba2884b95190aea51d13fd953`.
- 검증 환경: Windows, Python 3.12 격리 `.venv`; `pip install -e ./nanobot -e '.[dev]'` 성공. nanobot gitlink `1bb712d3488915ca4ed9ccc1a93067ff722f5ab9` 보존. 네 수집기·OpenAI는 fake이고 socket/DNS는 차단했다. SQLite는 pytest 임시 DB다.
- Tester / Reviewer: 이 문서의 검증은 Implementer가 수행했다. 별도 컨텍스트의 Tester와 Reviewer는 아직 수행하지 않았고 각각 **BLOCKED**다.

## Test Report

| AC | 시나리오 | 명령 또는 재현 절차 | 실제 결과 / 근거 | PASS / FAIL / BLOCKED |
|----|----------|--------------------|------------------|-----------------------|
| AC1 | 실제 `SKILL.md`의 실행 가능한 CLI 블록에서 시각별 한 명령 선택; 네 fake 수집 경로 | `test_skill_briefing_collects_all_four_paths_once`의 morning/afternoon/evening | 수정 전 각 경로 2회로 3건 실패, 수정 후 각 경로 1회 및 SQLite 기사 4건/URL 출력 | 오프라인 PASS; 운영 표본 BLOCKED |
| AC2 | 독립 collect 및 세 briefing 인자, 기존 기사 선택·출력 | `test_manual_collect_remains_a_single_collection`, AC1 테스트, `test_kst_schedule_query_boundary_and_exclusions` | 수동 collect 1회, 각 briefing 1회, 기존 기사와 기간·URL 유지 | 오프라인 PASS |
| AC3 | 한 소스 실패, 전부 빈 결과/기존 DB 기사, 완전 빈 DB, URL 중복, SQLite 부분 저장 실패 | `test_skill_keeps_one_collection_for_partial_empty_and_duplicate_results`, `test_skill_storage_error_does_not_generate_or_repeat`, 기존 수집/저장·LLM fallback 테스트 | 추가 전체 수집 없음; 기존 첫 payload 보존; 저장 실패는 예외로 전파되고 생성/LLM 호출 없음. 임시 SQLite에 첫 기사만 남는 기존 부분 저장 경계 확인 | 오프라인 PASS |
| AC4 | 관리 스킬 갱신, 두 번 실행 멱등성, 사용자 추가 파일 보존, 전체 회귀 | `test_seed_updates_existing_msalt_skills`, 관련 및 전체 pytest, lint, diff check | 관리 SKILL.md가 seed 원본으로 갱신; 사용자 파일 유지; 두 번째 실행 no-op. 전체 208 통과. 독립 Tester/Reviewer 미수행 | 구현자 PASS; 독립 검수 BLOCKED |
| AC5 | #13 포함 최종 후보의 단일 수집 및 승인된 #7 운영 관찰·Human 수용 | 미실행 | 통합 후보/실제 스킬 소비·수신 확인 없음 | BLOCKED |

### Regression

- 기준선: `.\\.venv\\Scripts\\python.exe -m pytest tests/msalt/news/ tests/msalt/test_cli.py -q --basetemp=.pytest-issue-14` → 83 passed, exit 0. 첫 시도는 기본 Windows temp ACL로 47 passed / 36 setup errors, exit 1; 작업 트리 내 `--basetemp`로 해결한 환경 문제다.
- RED: `.\\.venv\\Scripts\\python.exe -m pytest tests/msalt/news/test_offline_validation.py -q --basetemp=.pytest-issue-14` → 3 failed / 17 passed, exit 1. 세 시각 모두 `collect_all` 호출이 기대 1회 대신 2회였다.
- GREEN: 같은 명령 → 20 passed, exit 0.
- 변경 완료 후 관련: `.\\.venv\\Scripts\\python.exe -m pytest tests/msalt/news/ tests/msalt/test_cli.py -q --basetemp=.pytest-issue-14` → 91 passed, exit 0.
- 구현 커밋 SHA에서 전체: `.\\.venv\\Scripts\\python.exe -m pytest tests/msalt/ -q --basetemp=.pytest-issue-14` → 208 passed, exit 0.
- `.\\.venv\\Scripts\\python.exe -m ruff check tests/msalt/news/test_offline_validation.py tests/msalt/test_cli.py` → All checks passed, exit 0. `git diff --cached --check` (커밋 직전) 및 `git diff HEAD --check` (커밋 후) → exit 0.

### Result

구현자의 오프라인 테스트는 PASS. 독립 Tester 검증, 독립 Agent Review, #13 최종 통합 SHA 검증, 승인 후 운영 표본은 **BLOCKED**. 이 상태를 전체 Tests PASS 또는 PR 생성 Gate 통과로 표시하지 않는다.

## Agent Review Report

### Scope

- 승인 Issue #14 v1, 비교 기준 `96f8b344519494cea5fd127dbe8818404fce3182`, 구현 SHA `778d3d1c39a5abcba2884b95190aea51d13fd953`.
- 변경 파일: `msalt/skills/news-briefing/SKILL.md`, `tests/msalt/news/test_offline_validation.py`, `tests/msalt/test_cli.py`, 구현 계획과 이 보고서. 제품 Python/schema/cron/API 설정/gitlink 변경 없음.
- 별도 Reviewer가 diff와 Issue를 직접 검토하는 단계는 미수행.

### Findings

| 심각도 | 파일 / 위치 | 문제와 근거 | 수정 제안 | 해결 여부 |
|--------|-------------|-------------|-----------|-----------|
| 미검토 | 전체 diff | 독립 Reviewer 결과 없음 | 별도 컨텍스트에서 승인 범위와 AC 검토 | BLOCKED |

### Checklist

- 승인 설계·범위·AC 일치: 구현자 확인; 독립 검토 BLOCKED.
- 데이터 보존·마이그레이션: schema 변경 없음. URL 중복/기존 payload·tracking 보존은 오프라인 테스트 확인.
- 오류 경로·중복 처리·시간대: 부분/빈/저장 오류 및 KST 세 시각 오프라인 테스트 확인. 실제 LLM 스킬 소비는 미확인.
- 비밀값·자원·동시성: 외부 네트워크/Telegram/운영 DB 사용 없음. 실제 비용·시간·동시 실행은 미측정.
- 로그·운영 가능성·유지보수: 실패/빈 결과 뒤 스킬 임의 반복 금지를 문서화. 운영자 custom 관리 스킬은 동기화 전 보관 필요.
- 테스트 누락·회귀: 전체 208 통과; 독립 Tester와 통합 후보 최종 SHA 재검증 필요.

### Result

독립 Agent Review **BLOCKED**. 구현자는 이를 PASS로 대체하지 않는다.

## Human Review Handoff

후속 Tester/Reviewer는 Issue #14 v1과 이 SHA의 diff를 직접 확인하고 독립 보고서를 남긴다. #13 반영으로 관리 스킬이 다시 바뀌면 최종 통합 SHA에서 단일 수집 및 전달 정책을 다시 검증한다. 운영 대상·후보 SHA·비용/중단/rollback 조건을 구체화하고 별도 Human 승인 후 #7 표본에서 실제 tool/CLI 경계와 수신 결과를 기록한다. 현재 #14만으로 발송 전 mark 결함은 해결되지 않았으며 실제 발송·배포·DB 복원·merge를 수행하지 않았다.

## 후속 독립 검수 — 2026-10-09 KST

위 Implementer 보고서의 “독립 검수 BLOCKED”는 작성 시점 이력이다. 후속 검증 후보 `f6e78746180d3175e2433a065c77f402659d67ad`에서 별도 Tester `tester_14`와 Reviewer `reviewer_14`가 Issue·diff를 직접 확인했다.

- 독립 Tester: `python -m pytest tests/msalt/news/ tests/msalt/test_cli.py -q -p no:cacheprovider --basetemp=.pytest_cache/independent-tester14`: 91 passed, exit 0. `python -m pytest tests/msalt/ -q -p no:cacheprovider --basetemp=.pytest_cache/independent-tester14`: 208 passed, exit 0. 코드 SHA `778d3d1c39a5abcba2884b95190aea51d13fd953`와 후보의 diff는 이 보고서 추가만 있으며 코드/테스트 변화 없음을 확인했다.
- 독립 Reviewer: 후보 전체 diff 및 승인 v1 직접 검토, Agent Review PASS, Critical/Major 0. Minor의 보고서 독립 결과/SHA 반영을 이 절로 해결한다.
- 현재 AC1–4 오프라인 구현 Tests/Agent Review PASS. **AC5 실제 통합 운영/실수신과 Human 수용은 BLOCKED**다. 이번 문서 반영 뒤 최종 후보 SHA의 diff/재검수 근거는 연결 PR에 고정한다. 운영 배포·발송·병합 승인을 대신하지 않는다.
