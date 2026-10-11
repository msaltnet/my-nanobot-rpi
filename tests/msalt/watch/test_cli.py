import json
import sqlite3

from typer.testing import CliRunner

from msalt.cli import _seed_if_missing, app
from msalt.storage import Storage


def invoke(monkeypatch, tmp_path, args):
    monkeypatch.setattr("msalt.cli._load_dotenv", lambda: None)
    monkeypatch.setattr("msalt.watch.cli.DEFAULT_DB", str(tmp_path / "watch.db"))
    return CliRunner().invoke(app, ["watch", *args])


def test_cli_crud_json_and_revision(monkeypatch, tmp_path):
    result = invoke(monkeypatch, tmp_path, ["add", "표시 ＡＩ", "--description", "원문 설명",
                                         "--keywords-json", '["AI"]', "--excluded-json", "[]", "--json"])
    assert result.exit_code == 0, result.output
    item = json.loads(result.stdout)
    assert (item["name"], item["revision"], item["active"]) == ("표시 ＡＩ", 1, False)
    identifier = str(item["id"])
    for args, revision, active in [
        (["show", identifier], 1, False),
        (["pause", identifier, "--expected-revision", "1"], 1, False),
        (["resume", identifier, "--expected-revision", "1"], 2, True),
        (["update", identifier, "--expected-revision", "2", "--description", "새 설명"], 3, True),
        (["delete", identifier, "--expected-revision", "3", "--confirm"], 4, False),
    ]:
        result = invoke(monkeypatch, tmp_path, [*args, "--json"])
        assert result.exit_code == 0, result.output
        item = json.loads(result.stdout)
        assert (item["revision"], item["active"]) == (revision, active)
    result = invoke(monkeypatch, tmp_path, ["list", "--json"])
    assert json.loads(result.stdout) == []
    result = invoke(monkeypatch, tmp_path, ["--json", "list", "--all"])
    assert json.loads(result.stdout)[0]["deleted_at"]


def test_cli_bad_inputs_exit_two_without_change(monkeypatch, tmp_path):
    result = invoke(monkeypatch, tmp_path, ["add", "valid", "--description", "text",
                                         "--keywords-json", "[]", "--excluded-json", "[]"])
    assert result.exit_code == 0
    bad = [
        ["add", "other", "--description", "text", "--keywords-json", "not json", "--excluded-json", "[]"],
        ["add", "other", "--description", "text", "--keywords-json", '{}', "--excluded-json", "[]"],
        ["add", "other", "--description", "text", "--keywords-json", '[1]', "--excluded-json", "[]"],
        ["add", "other", "--description", ""], ["show", "0"], ["show", "999"],
        ["pause", "1"], ["resume", "1"], ["delete", "1", "--expected-revision", "1"],
        ["update", "1", "--expected-revision", "1"],
        ["update", "1", "--expected-revision", "2", "--name", "stale"],
        ["update", "1", "--expected-revision", "1", "--keywords-json", 'null'],
    ]
    for args in bad:
        result = invoke(monkeypatch, tmp_path, [*args, "--json"])
        assert result.exit_code == 2, (args, result.output)
    result = invoke(monkeypatch, tmp_path, ["show", "1", "--json"])
    assert json.loads(result.stdout)["revision"] == 1
    result = invoke(monkeypatch, tmp_path, ["show", "999", "--json"])
    assert "error" in json.loads(result.stdout)


def test_cli_database_errors_exit_one_hide_driver_details(monkeypatch, tmp_path):
    def broken(_self):
        raise sqlite3.OperationalError("private-path-and-interest")
    monkeypatch.setattr(Storage, "initialize", broken)
    result = invoke(monkeypatch, tmp_path, ["list", "--json"])
    assert result.exit_code == 1
    assert "error" in json.loads(result.stdout)
    assert "private-path-and-interest" not in result.output


def test_seed_installs_watch_without_new_jobs_and_preserves_local_notes(monkeypatch, tmp_path):
    monkeypatch.setattr("msalt.cli.NANOBOT_HOME", tmp_path / "nano")
    note = tmp_path / "nano/workspace/skills/watch/operator-notes.md"
    note.parent.mkdir(parents=True)
    note.write_text("preserve", encoding="utf-8")
    _seed_if_missing()
    skill = note.parent / "SKILL.md"
    assert skill.exists()
    from nanobot.agent.skills import SkillsLoader
    loader = SkillsLoader(tmp_path / "nano/workspace")
    assert "watch" in {entry["name"] for entry in loader.list_skills()}
    jobs_path = tmp_path / "nano/workspace/cron/jobs.json"
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))["jobs"]
    assert {job["id"] for job in jobs} == {
        "msalt-news-briefing-morning", "msalt-news-briefing-afternoon", "msalt-news-briefing-evening"}
    before = jobs_path.read_bytes()
    assert _seed_if_missing() == []
    assert jobs_path.read_bytes() == before
    assert note.read_text(encoding="utf-8") == "preserve"


def test_cli_unexpected_integrity_error_is_database_failure(monkeypatch, tmp_path):
    storage = Storage(str(tmp_path / "watch.db"))
    storage.initialize()
    with storage._connect() as conn:
        conn.execute("CREATE TRIGGER fixture_failure BEFORE INSERT ON watch_conditions BEGIN SELECT RAISE(ABORT, 'private-integrity-detail'); END")
    result = invoke(monkeypatch, tmp_path, ["add", "fixture", "--description", "fixture",
                                          "--keywords-json", "[]", "--excluded-json", "[]", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"error": "Watch database operation failed"}
    assert "private-integrity-detail" not in result.output


def test_cli_integer_outside_sqlite_range_is_invalid_input(monkeypatch, tmp_path):
    result = invoke(monkeypatch, tmp_path, ["show", str(2**63), "--json"])
    assert result.exit_code == 2
    assert "error" in json.loads(result.stdout)
    result = invoke(monkeypatch, tmp_path, ["add", "fixture", "--description", "fixture",
                                         "--keywords-json", "[]", "--excluded-json", "[]", "--json"])
    assert result.exit_code == 0
    result = invoke(monkeypatch, tmp_path, ["pause", "1", "--expected-revision", str(2**63), "--json"])
    assert result.exit_code == 2
    assert "error" in json.loads(result.stdout)
