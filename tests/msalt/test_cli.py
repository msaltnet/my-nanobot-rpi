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
