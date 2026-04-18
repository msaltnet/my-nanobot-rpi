from unittest.mock import patch
import pytest

from msalt.tracking.cli import build_parser, run_command
from msalt.storage import Storage
from msalt.tracking.items import TrackedItemManager


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "test.db"
    s = Storage(str(p))
    s.initialize()
    return str(p)


def test_add_command(db_path, capsys):
    rc = run_command(["add", "독서", "duration", "--time", "22:00"],
                     db_path=db_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "독서" in out
    s = Storage(db_path)
    items = TrackedItemManager(s)
    assert items.get("독서") is not None


def test_add_command_quantity_requires_unit(db_path, capsys):
    rc = run_command(["add", "음주", "quantity", "--time", "22:00"],
                     db_path=db_path)
    assert rc != 0
    err = capsys.readouterr().err
    assert "unit" in err.lower()


def test_list_command(db_path, capsys):
    s = Storage(db_path)
    TrackedItemManager(s).add("수면", "duration", None, "08:00")
    rc = run_command(["list"], db_path=db_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "수면" in out


def test_record_command(db_path, capsys):
    s = Storage(db_path)
    TrackedItemManager(s).add("수면", "duration", None, "08:00")
    rc = run_command(
        ["record", "수면", "--date", "2026-04-13", "--num", "480",
         "--raw", "8시간"],
        db_path=db_path,
    )
    assert rc == 0


def test_summary_command(db_path, capsys):
    s = Storage(db_path)
    TrackedItemManager(s).add("수면", "duration", None, "08:00")
    run_command(
        ["record", "수면", "--date", "2026-04-13", "--num", "480",
         "--raw", "8h"],
        db_path=db_path,
    )
    rc = run_command(["summary", "수면", "--days", "7",
                      "--ref", "2026-04-13"], db_path=db_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "수면" in out


def test_dispatch_command_invokes_dispatcher(db_path, capsys, monkeypatch):
    s = Storage(db_path)
    TrackedItemManager(s).add("수면", "duration", None, "08:00")

    sent: list[str] = []
    monkeypatch.setattr(
        "msalt.tracking.cli._make_telegram_sender",
        lambda: sent.append,
    )
    rc = run_command(["dispatch", "--now", "2026-04-14T08:05:00+09:00"],
                     db_path=db_path)
    assert rc == 0
    assert any("수면" in m for m in sent)


def test_first_run_seeds_defaults(tmp_path, capsys):
    db = tmp_path / "fresh.db"
    rc = run_command(["list"], db_path=str(db))
    assert rc == 0
    out = capsys.readouterr().out
    assert "수면" in out
    assert "음주" in out
    assert "영어공부" in out


def test_seed_only_on_empty_db(tmp_path, capsys):
    db = tmp_path / "fresh.db"
    run_command(["list"], db_path=str(db))   # seeds
    run_command(["delete", "수면"], db_path=str(db))
    capsys.readouterr()
    rc = run_command(["list"], db_path=str(db))
    out = capsys.readouterr().out
    assert "수면" not in out
    assert "음주" in out  # 다른 시드는 그대로
