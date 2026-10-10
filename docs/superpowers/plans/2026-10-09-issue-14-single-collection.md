# Issue 14 single collection implementation plan
> For agentic workers: use subagent-driven-development task execution; Issue body is the binding spec.
**Goal:** execute one collection per news skill turn without changing the existing manual CLI.
**Architecture:** remove the skill's collect command and execute its extracted briefing invocation with fake external collectors and a real temporary SQLite DB.
**Tech Stack:** Python 3.11+, pytest, SQLite, Markdown skill, pinned nanobot.
**Spec:** https://github.com/msaltnet/my-nanobot-rpi/issues/14 (approved v1, exact snapshot in task-1-brief.md).
## Global Constraints
- Preserve main/user edits; use codex/issue-14-single-collection.
- No product Python/schema/gitlink/source/schedule/tracking changes.
- No external API/Telegram/production DB/service/deployment/merge.
- Separate Tester/Reviewer and current SHA PASS before initial PR. Live AC5 remains BLOCKED.
### Task 1: Fix and test skill consumption
**Files:** msalt/skills/news-briefing/SKILL.md; tests/msalt/news/test_offline_validation.py; existing seed tests if needed; docs/development/reports/2026-10-09-issue-14-single-collection.md.
**Interfaces:** preserve run_collect()/run_briefing(time_of_day)->str.
- [ ] Before production edit, adapt the existing two-collection characterization into a regression that extracts the actual skill's executable briefing/collect command groups and executes one valid time variant with run_collect/run_briefing against fake external collectors+real SQLite. Expected collector count per path is one; red against old skill is two.
- [ ] Run isolated regression and confirm behavioral FAIL before removing the pre-collect stage.
- [ ] Remove only pre-collect and clarify one invocation, no blind repeats on empty/error. Keep CLI forms.
- [ ] Check morning/afternoon/evening, manual collect, partial/empty/duplicate/storage error, seed idempotence and preservation using relevant existing tests plus needed behavioral cases.
- [ ] Run news tests then full tests/msalt and diff --check. Report red/green exact commands/counts/exit.
- [ ] Write verification-template report: implementation/offline evidence; live workflow and actual receiving not tested.
- [ ] Commit code/tests/docs; report SHA and concerns. Parent supplies independent tester/reviewer evidence later.
