import os
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from msalt.cli import _check_env, _load_env_file, _seed_if_missing, app


runner = CliRunner()


def test_load_env_file_respects_existing_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
    monkeypatch.setenv("FOO", "preexisting")
    monkeypatch.delenv("BAZ", raising=False)

    _load_env_file(env)

    assert os.environ["FOO"] == "preexisting"
    assert os.environ["BAZ"] == "qux"


def test_load_env_file_strips_quotes(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('TOKEN="abc123"\nKEY=\'def\'\n', encoding="utf-8")
    monkeypatch.delenv("TOKEN", raising=False)
    monkeypatch.delenv("KEY", raising=False)

    _load_env_file(env)

    assert os.environ["TOKEN"] == "abc123"
    assert os.environ["KEY"] == "def"


def test_check_env_detects_placeholders(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "your-bot-token-here")
    monkeypatch.setenv("TELEGRAM_USER_ID", "")

    missing = _check_env()
    assert "OPENAI_API_KEY" not in missing
    assert "TELEGRAM_BOT_TOKEN" in missing
    assert "TELEGRAM_USER_ID" in missing


def test_seed_if_missing_creates_files(tmp_path, monkeypatch):
    monkeypatch.setattr("msalt.cli.NANOBOT_HOME", tmp_path / "nano")
    created = _seed_if_missing()
    assert any("config.json" in c for c in created)
    assert any("SOUL.md" in c for c in created)
    assert any("USER.md" in c for c in created)
    assert (tmp_path / "nano" / "config.json").exists()
    assert (tmp_path / "nano" / "workspace" / "SOUL.md").exists()


def test_seed_substitutes_telegram_user_id_in_cron_jobs(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr("msalt.cli.NANOBOT_HOME", tmp_path / "nano")
    monkeypatch.setenv("TELEGRAM_USER_ID", "123456789")
    _seed_if_missing()
    jobs_file = tmp_path / "nano" / "workspace" / "cron" / "jobs.json"
    assert jobs_file.exists()
    data = json.loads(jobs_file.read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert len(jobs) == 2
    assert {j["id"] for j in jobs} == {
        "msalt-news-briefing-morning",
        "msalt-news-briefing-evening",
    }
    # ${TELEGRAM_USER_ID} 치환 확인
    assert all(j["payload"]["to"] == "123456789" for j in jobs)
    # 치환 후에는 플레이스홀더가 남아있지 않아야 한다
    assert "${TELEGRAM_USER_ID}" not in jobs_file.read_text(encoding="utf-8")
    # 스케줄
    schedules = {j["id"]: j["schedule"]["expr"] for j in jobs}
    assert schedules["msalt-news-briefing-morning"] == "0 7 * * *"
    assert schedules["msalt-news-briefing-evening"] == "0 19 * * *"


def test_seed_leaves_placeholder_when_telegram_user_id_missing(tmp_path, monkeypatch):
    """TELEGRAM_USER_ID 없이 seed된 경우 플레이스홀더 그대로 남아 doctor가 경고할 수 있어야 한다."""
    monkeypatch.setattr("msalt.cli.NANOBOT_HOME", tmp_path / "nano")
    monkeypatch.delenv("TELEGRAM_USER_ID", raising=False)
    _seed_if_missing()
    jobs_file = tmp_path / "nano" / "workspace" / "cron" / "jobs.json"
    assert "${TELEGRAM_USER_ID}" in jobs_file.read_text(encoding="utf-8")


def test_seed_copies_skills_so_agent_can_find_them(tmp_path, monkeypatch):
    """nanobot SkillsLoader는 ~/.nanobot/workspace/skills/만 스캔한다.
    seed 단계에서 msalt/skills/*를 거기로 복사해야 agent가 찾을 수 있다."""
    monkeypatch.setattr("msalt.cli.NANOBOT_HOME", tmp_path / "nano")
    _seed_if_missing()
    skills_root = tmp_path / "nano" / "workspace" / "skills"
    assert (skills_root / "news" / "SKILL.md").exists()
    assert (skills_root / "news-briefing" / "SKILL.md").exists()
    assert (skills_root / "tracking" / "SKILL.md").exists()


def test_seed_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("msalt.cli.NANOBOT_HOME", tmp_path / "nano")
    first = _seed_if_missing()
    second = _seed_if_missing()
    assert first  # 첫 실행은 seed
    assert second == []  # 이후엔 no-op


def test_gateway_exits_when_env_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("msalt.cli.NANOBOT_HOME", tmp_path / "nano")
    monkeypatch.setattr("msalt.cli.REPO_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    for k in ("OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_USER_ID"):
        monkeypatch.delenv(k, raising=False)

    result = runner.invoke(app, ["gateway"])
    assert result.exit_code == 1
    assert "누락된 환경 변수" in result.stdout


def test_tracking_subcommand_passes_argv_to_run_command(monkeypatch):
    """`msalt-nanobot tracking <args>` 가 args를 그대로 msalt.tracking.cli.run_command로 위임하는지 확인.

    이게 깨지면 봇이 'python3 -m msalt.tracking …' 같은 폴백을 쓰게 되고,
    Ubuntu 시스템 인터프리터에는 msalt가 없어 ModuleNotFoundError가 난다.
    """
    captured: dict = {}

    def fake_run_command(argv):
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr("msalt.tracking.cli.run_command", fake_run_command)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
    monkeypatch.setenv("TELEGRAM_USER_ID", "1")

    result = runner.invoke(
        app,
        ["tracking", "record", "영어공부", "--date", "2026-04-25",
         "--bool", "--raw", "영어공부 안함"],
    )

    assert result.exit_code == 0, result.stdout
    assert captured["argv"] == [
        "record", "영어공부", "--date", "2026-04-25",
        "--bool", "--raw", "영어공부 안함",
    ]


def test_tracking_subcommand_propagates_nonzero_exit(monkeypatch):
    monkeypatch.setattr("msalt.tracking.cli.run_command", lambda argv: 2)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
    monkeypatch.setenv("TELEGRAM_USER_ID", "1")

    result = runner.invoke(app, ["tracking", "list"])
    assert result.exit_code == 2


def test_default_invokes_gateway(tmp_path, monkeypatch):
    """인자 없이 실행하면 gateway로 분기되는지 확인."""
    monkeypatch.setattr("msalt.cli.NANOBOT_HOME", tmp_path / "nano")
    monkeypatch.setattr("msalt.cli.REPO_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    for k in ("OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_USER_ID"):
        monkeypatch.delenv(k, raising=False)

    result = runner.invoke(app, [])
    # env 누락이라 gateway가 exit 1 — 이는 default가 gateway로 갔다는 증거
    assert result.exit_code == 1
    assert "누락된 환경 변수" in result.stdout
