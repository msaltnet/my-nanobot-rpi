import json

import pytest
from typer.testing import CliRunner

from msalt.cli import app
from msalt.storage import Storage
from msalt.watch.cli import run_command


def test_notification_cli_confirmations_and_default_status(tmp_path, capsys):
    path = str(tmp_path / "notify.db")
    assert run_command(["notify", "status", "--json"], db_path=path) == 0
    assert json.loads(capsys.readouterr().out) == {"enabled": False, "deliveries": []}
    for mode in ["enable", "disable"]:
        assert run_command(["notify", mode, "--json"], db_path=path) == 2
        assert "confirm" in json.loads(capsys.readouterr().out)["error"]
    assert run_command(["notify", "enable", "--confirm", "--json"], db_path=path) == 0
    assert json.loads(capsys.readouterr().out)["enabled"]
    assert run_command(["notify", "disable", "--confirm", "--json"], db_path=path) == 0
    assert not json.loads(capsys.readouterr().out)["enabled"]


def test_notification_cli_dispatch_requires_diagnostic_flag_and_no_configuration_when_disabled(
    tmp_path, capsys
):
    path = str(tmp_path / "notify.db")
    assert (
        run_command(["notify", "dispatch", "--now", "2026-10-10T00:00:00Z", "--json"], db_path=path)
        == 2
    )
    assert "diagnostic" in json.loads(capsys.readouterr().out)["error"]
    assert run_command(["notify", "dispatch", "--json"], db_path=path) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "disabled"
    assert (
        run_command(
            ["notify", "dispatch", "--now", "invalid", "--diagnostic-time", "--json"], db_path=path
        )
        == 2
    )
    assert "ISO8601" in json.loads(capsys.readouterr().out)["error"]


def test_notification_root_cli_json_and_sanitized_database_failure(tmp_path, monkeypatch):
    from msalt.watch import cli

    monkeypatch.setattr(cli, "DEFAULT_DB", str(tmp_path / "root.db"))
    result = CliRunner().invoke(app, ["watch", "notify", "status", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["enabled"] is False

    def fail(self):
        raise OSError("private fixture path")

    monkeypatch.setattr(Storage, "initialize", fail)
    result = CliRunner().invoke(app, ["watch", "notify", "status", "--json"])
    assert result.exit_code == 1
    assert "private fixture" not in result.stdout


@pytest.mark.parametrize(
    "arguments",
    [
        ["resolve", "missing", "--outcome", "sent", "--confirm"],
        ["resolve", "missing", "--outcome", "retry", "--evidence", "fixture"],
        ["enable"],
    ],
)
def test_notification_cli_missing_receipt_confirmation_no_send(tmp_path, capsys, arguments):
    path = str(tmp_path / "notify.db")
    assert run_command(["notify", *arguments, "--json"], db_path=path) == 2
    assert "error" in json.loads(capsys.readouterr().out)


def test_cli_real_dispatch_and_receipt_resolution_offline(tmp_path, monkeypatch, capsys):
    from datetime import datetime, timezone

    from msalt.watch.evaluation import Evaluator
    from msalt.watch.evaluation_store import EvaluationStore
    from msalt.watch.notification_store import NotificationStore
    from msalt.watch.store import WatchStore

    path = str(tmp_path / "notify.db")
    storage = Storage(path)
    storage.initialize()
    watches = WatchStore(storage)
    item = watches.add("fixture", description="fixture", keywords=[], excluded_keywords=[])
    watches.resume(item.id, expected_revision=1)
    storage.insert_article("fixture", "GPU", "https://fixture/1", "GPU", "fixture")
    Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="Changed", evidence="GPU"),
    ).run()
    notifications = NotificationStore(storage)
    notifications.set_enabled(True, confirm=True)
    monkeypatch.setenv("TELEGRAM_USER_ID", "123456")
    monkeypatch.setattr("msalt.cli._load_dotenv", lambda: None)
    monkeypatch.setattr("msalt.news.reply_tool.authorized_target", lambda target: "fixture-token")
    posted = []

    async def post(payload):
        posted.append(payload)
        return 200, {"ok": True, "result": {"message_id": 9}}

    monkeypatch.setattr("msalt.watch.sender.BotAPI", lambda token: post)
    assert (
        run_command(
            ["notify", "dispatch", "--now", "2026-10-10T00:05:00Z", "--diagnostic-time", "--json"],
            db_path=path,
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["state"] == "sent" and len(posted) == 1
    assert "123456" not in json.dumps(output) and "fixture-token" not in json.dumps(output)
    # Actual state machine unknown fixture followed by CLI operator receipt; no POST.
    storage.insert_article("fixture", "GPU2", "https://fixture/2", "GPU", "fixture")
    Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="Changed", evidence="GPU"),
    ).run()
    prepared = notifications.prepare(
        "123456", now=datetime(2026, 10, 10, 1, 5, tzinfo=timezone.utc)
    )
    token = notifications.start_sending(
        prepared["delivery_id"], now=datetime(2026, 10, 10, 1, 5, tzinfo=timezone.utc)
    )
    notifications.finish(prepared["delivery_id"], token, state="unknown")
    assert (
        run_command(
            [
                "notify",
                "resolve",
                prepared["delivery_id"],
                "--outcome",
                "sent",
                "--evidence",
                "Human receipt",
                "--message-id",
                "88",
                "--confirm",
                "--json",
            ],
            db_path=path,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["state"] == "sent"
    assert len(posted) == 1


def test_disabled_cli_dispatch_recovers_sending_without_configuration_or_post(tmp_path, capsys):
    from datetime import datetime, timezone

    from msalt.watch.evaluation import Evaluator
    from msalt.watch.evaluation_store import EvaluationStore
    from msalt.watch.notification_store import NotificationStore
    from msalt.watch.store import WatchStore

    path = str(tmp_path / "notify.db")
    storage = Storage(path)
    storage.initialize()
    watches = WatchStore(storage)
    item = watches.add("fixture", description="fixture", keywords=[], excluded_keywords=[])
    watches.resume(item.id, expected_revision=1)
    storage.insert_article("fixture", "GPU", "https://fixture/1", "GPU", "fixture")
    Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="Changed", evidence="GPU"),
    ).run()
    notifications = NotificationStore(storage)
    notifications.set_enabled(True, confirm=True)
    now = datetime(2026, 10, 10, 0, 5, tzinfo=timezone.utc)
    row = notifications.prepare("123456", now=now)
    notifications.start_sending(row["delivery_id"], now=now)
    notifications.set_enabled(False, confirm=True)
    assert run_command(["notify", "dispatch", "--json"], db_path=path) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "disabled"
    assert notifications.show(row["delivery_id"])["state"] == "unknown"
