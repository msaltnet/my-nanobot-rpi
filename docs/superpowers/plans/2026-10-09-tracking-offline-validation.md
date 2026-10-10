# Issue 8 Offline Tracking Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute task-by-task.

**Goal:** Characterize existing tracking failures using temporary SQLite and fake boundaries, without product fixes.
**Architecture:** Add offline validation tests for persistence/statistics and delivery/state. Capture observed unsafe behavior explicitly; PASS means reproduction, not product safety. Reports map original AC1–7 and mark live paths BLOCKED.
**Tech Stack:** Python >=3.11, pytest, pytest-asyncio, SQLite, unittest.mock, existing pinned nanobot.
**Spec:** GitHub Issue #8 current approved 상세 실행 설계 v1. Read Issue body directly; root base 96f8b344519494cea5fd127dbe8818404fce3182.

## Global Constraints

- Only tests/msalt/tracking/test_offline_validation.py, optional test_delivery_boundary.py, this supporting plan, verification report and report index may change.
- Product/schema/skill/deploy/nanobot gitlink changes forbidden. External paid LLM calls 0, real Telegram sends 0, operational writes/deployment/downtime 0.
- Use temporary DB via run_command(db_path=...). Block default DB and socket/DNS/HTTP, fake LLM and Telegram. Synthetic data only.
- Keep AC1–7 unchanged; characterize known failures rather than silently fixing them. No new behavior assertion that claims unsafe behavior is safe.
- Separate Tester/Reviewer verify current SHA; create related partial PR after PASS, never Closes #8. No deployment or merge.

## Task 1: Offline tracking characterization tests

**Files:** Create tests/msalt/tracking/test_offline_validation.py and test_delivery_boundary.py only if separation improves clarity.
**Consumes:** Storage.initialize/upsert_record/get_records_for_item; TrackedItemManager; RecordManager; NaturalLanguageParser; run_command(argv, db_path); Dispatcher.run(now); _make_telegram_sender; TrackingReplyTool.
**Produces:** Independently executable tests and coverage notes listing scenario-to-AC mapping.

- [x] Read existing tests; do not copy existing happy-path assertions without an uncovered boundary.
- [x] Add fail-closed autouse socket/DNS/client/default DB protection with explicit synthetic token/client fakes and real SQLite tmp_path.
- [x] AC1: 4 schemas persistence/reopen and same-date overwrite; invalid inputs/no state changes; cascade deletion with unrelated news/briefed/other tracking sentinels intact; legacy schema migration idempotence if not already adequately covered; alcohol user override/zero bounds.
- [x] AC2: fake parser malformed/timeout/explicit and relative dates; invalid types and missing context characterize limits rather than claim actual agent understanding; explicit date button/partial batch via actual per-item CLI and unchanged other records. Document skill dependency.
- [x] AC3: trigger-backed rejected insert/no false success; locked DB (short connection timeout, no 5sec sleeps); first item commit/second failure; committed DB despite advice failure; follow-up failure behavior already covered, only add if needed.
- [x] AC4: 7/30-day start/end/+1-date boundaries and empty/0/False/NULL versus absence, record-count denominator, future-date pollution in query/summary/advice. Verify actual output, not only call counts.
- [x] AC5: same scheduled window repeated run + DB reopen; naive/KST/UTC exact boundaries; pending target dates and partial response; sender timeout vs HTTP status/ok failure; send before pending/state update failure and restart duplicate risk; TrackingReplyTool validation/failures/current-chat suppress marker. Use fake boundaries, no plugins/network startup.

Example characterization (observed defect, not desired final behavior):
```python
store.upsert_record(item_id, '2026-10-10', value_bool=True, raw_input='synthetic')
rows = store.get_records_for_item(item_id, 7, '2026-10-09')
assert [row['recorded_for'] for row in rows] == ['2026-10-10']
```

Example persistence failure assertion:
```python
with sqlite3.connect(db_path) as conn:
    conn.execute("CREATE TRIGGER reject_record BEFORE INSERT ON records BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
with pytest.raises(sqlite3.IntegrityError):
    run_command(['record', 'synthetic', '--date', '2026-10-09', '--bool', '--raw', 'synthetic'], db_path=db_path)
assert not store.record_exists(item_id, '2026-10-09')
assert '기록되었어' not in capsys.readouterr().out
```

- [x] Run related tests, new tests Ruff check/format, then all tests/msalt. No production RED/GREEN cycle because product implementation is forbidden; evidence comes from real boundary injection and state/output assertions.
- [x] Return report with commands/exit/count, new tests by AC, reproducible defects with locations, and limitations. Do not create remote Issues/PRs or commit; controller reviews first.

## Task 2: Verification reports and reproducible defect Issues

**Files:** Create docs/development/reports/2026-10-09-tracking-validation.md; modify reports/README.md.
**Consumes:** Task 1 execution evidence, approved Issue, fresh independent tests and review.
**Produces:** AC1–7 report and separately traced Open defect Issues.

- [ ] Independently review test safety/spec/quality; fix only test/report defects.
- [ ] Create small Open Issues only for demonstrated distinct product defects, with reproduction, current SHA, impact, expected behavior, proposed AC, data preservation/rollback considerations and Related to #8. Search duplicates first, including #13/#14 owned elsewhere.
- [ ] Record actual tested source SHA, environment, exact commands and counts. Report AC3 actual response/live send and AC5/7 operational acceptance as BLOCKED; no PASS inference from mocks.
- [ ] Commit source/docs, then have separate Tester run full suite and Reviewer inspect Issue/diff/current SHA and execute new tests. Fixes invalidate affected checks.
- [ ] Write final exact SHA test/review evidence in PR body. Create Related to #8 PR only after both PASS and CI inspection. Keep deployment/Dogfooding N/A as proposal pending Human acceptance.

## Execution Ledger

- Setup: native isolated worktree; base 96f8b344519494cea5fd127dbe8818404fce3182. Human “진행해” recorded on Issue #8; unique Ready label.
- Task 1/Task 2 share only test evidence, controller owns reports and remote mutations. No file-edit overlap.
- Ruling: TDD applies to future product fixes; this approved unit must characterize existing behavior without production code changes.
- Task 1: source 4b184e868dcb058cdc5a45fa6d0c8afe641a4af1; 23 focused / 223 full implementer PASS; independent focused review PASS after two evidence-gap fixes. Task 2: Open Issues #16–#20 created; report/index prepared. Final candidate checks and PR evidence are maintained on the linked PR.
