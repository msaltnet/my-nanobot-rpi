import pytest

from msalt.storage import Storage
from msalt.tracking.cli import _make_reply_markup, _make_telegram_sender, run_command
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
    out = capsys.readouterr().out
    assert "기록되었어: 수면 2026-04-13" in out
    assert "최근 7일" in out


def test_record_command_outputs_advice(db_path, capsys):
    s = Storage(db_path)
    items = TrackedItemManager(s)
    items.add("음주", "quantity", "g", "22:00")
    items.add("영어공부", "boolean", None, "22:00")
    run_command(
        ["record", "음주", "--date", "2026-04-08", "--num", "20",
         "--raw", "맥주"],
        db_path=db_path,
    )
    run_command(
        ["record", "음주", "--date", "2026-04-10", "--num", "30",
         "--raw", "와인"],
        db_path=db_path,
    )
    capsys.readouterr()

    rc = run_command(
        ["record", "음주", "--date", "2026-04-13", "--num", "48.3",
         "--raw", "소주"],
        db_path=db_path,
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "최근 7일 음주 3일" in out
    assert "최근 30일 음주 3일" in out
    assert "횟수와 양을 조금 줄이는 방향" in out
    assert "영어공부는 최근 7일과 최근 30일 모두 실천 기록이 없네" in out


def test_record_command_accepts_json_detail(db_path, capsys):
    s = Storage(db_path)
    TrackedItemManager(s).add("음주", "quantity", "g", "22:00")
    rc = run_command(
        [
            "record", "음주",
            "--date", "2026-04-13",
            "--num", "48.3",
            "--json",
            '{"drink_type":"소주","amount":1,"unit":"병","serving_ml":360,'
            '"abv_percent":17,"alcohol_g":48.3}',
            "--raw", "소주 1병",
        ],
        db_path=db_path,
    )
    assert rc == 0


def test_record_command_rejects_invalid_json(db_path, capsys):
    s = Storage(db_path)
    TrackedItemManager(s).add("음주", "quantity", "g", "22:00")
    rc = run_command(
        ["record", "음주", "--date", "2026-04-13", "--json", "{",
         "--raw", "소주 1병"],
        db_path=db_path,
    )
    assert rc == 2
    assert "invalid JSON" in capsys.readouterr().err


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


def test_make_reply_markup_builds_keyboard():
    markup = _make_reply_markup([["수면 7시간", "수면 8시간"]])
    assert markup["keyboard"][0][0]["text"] == "수면 7시간"
    assert markup["keyboard"][0][1]["text"] == "수면 8시간"
    assert markup["resize_keyboard"] is True
    assert markup["one_time_keyboard"] is True


def test_make_reply_markup_removes_keyboard_when_empty():
    assert _make_reply_markup(None) == {"remove_keyboard": True}


def test_telegram_sender_posts_reply_markup(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_USER_ID", "123")
    posted = {}

    def fake_post(url, json, timeout):
        posted["url"] = url
        posted["json"] = json
        posted["timeout"] = timeout

    monkeypatch.setattr("msalt.tracking.cli.httpx.post", fake_post)

    sender = _make_telegram_sender()
    sender("질문", [["수면 7시간", "수면 8시간"]])

    assert posted["url"] == "https://api.telegram.org/bottoken/sendMessage"
    assert posted["json"]["chat_id"] == "123"
    assert posted["json"]["text"] == "질문"
    assert posted["json"]["reply_markup"]["keyboard"][0][0]["text"] == "수면 7시간"
    assert posted["timeout"] == 10


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
