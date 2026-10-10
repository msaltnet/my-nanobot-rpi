"""Issue #8: offline characterization of tracking state and failure boundaries.

The tests describe observed behavior. Passing reproductions are not acceptance of
the product's duplicate-send or future-date behavior.
"""

import socket
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from nanobot.session.manager import SessionManager

from msalt.storage import Storage
from msalt.tracking.cli import _make_telegram_sender, run_command
from msalt.tracking.dispatcher import Dispatcher
from msalt.tracking.items import TrackedItemManager
from msalt.tracking.parser import NaturalLanguageParser
from msalt.tracking.records import RecordManager

KST = ZoneInfo("Asia/Seoul")


@pytest.fixture(autouse=True)
def offline_only(tmp_path, monkeypatch):
    """All storage belongs to pytest; any accidental network use fails closed."""
    original_init = Storage.__init__

    def guarded_init(self, db_path):
        assert Path(db_path).resolve().is_relative_to(tmp_path.resolve()), db_path
        original_init(self, db_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("offline tracking test attempted network access")

    monkeypatch.setattr(Storage, "__init__", guarded_init)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket.socket, "sendto", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(httpx, "post", forbidden)
    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("TELEGRAM_USER_ID", "123")


@pytest.fixture
def tracking(tmp_path):
    db = tmp_path / "tracking.db"
    store = Storage(str(db))
    store.initialize()
    items = TrackedItemManager(store)
    records = RecordManager(store, items)
    return db, store, items, records


def test_four_schemas_survive_reopen_and_one_date_is_overwritten(tracking):
    db, _, items, records = tracking
    for name, schema, unit, value in (
        ("메모", "freetext", None, {"value_text": "첫 메모"}),
        ("수면", "duration", None, {"value_num": 420}),
        ("물", "quantity", "잔", {"value_num": 0}),
        ("운동", "boolean", None, {"value_bool": False}),
    ):
        items.add(name, schema, unit, "22:00")
        records.upsert(name, "2026-10-08", raw_input="synthetic", **value)
    records.upsert("메모", "2026-10-08", raw_input="second", value_text="수정")

    reopened = Storage(str(db))
    reopened.initialize()
    reopened_records = RecordManager(reopened, TrackedItemManager(reopened))
    assert [row["value_text"] for row in reopened_records.recent("메모", 7, "2026-10-09")] == [
        "수정"
    ]
    assert reopened_records.recent("수면", 7, "2026-10-09")[0]["value_num"] == 420
    assert reopened_records.recent("물", 7, "2026-10-09")[0]["value_num"] == 0
    assert reopened_records.recent("운동", 7, "2026-10-09")[0]["value_bool"] == 0


def test_delete_cascades_only_target_records_and_preserves_news(tracking):
    db, store, items, records = tracking
    items.add("삭제대상", "boolean", None, "22:00")
    items.add("보존대상", "boolean", None, "22:00")
    records.upsert("삭제대상", "2026-10-08", raw_input="yes", value_bool=True)
    records.upsert("보존대상", "2026-10-08", raw_input="no", value_bool=False)
    store.insert_article("synthetic", "article", "https://example.invalid/a", "s", "c")
    store.mark_articles_briefed(["https://example.invalid/a"], "synthetic")

    items.delete("삭제대상")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM news_briefed_articles").fetchone()[0] == 1
    assert records.recent("보존대상", 7, "2026-10-09")[0]["value_bool"] == 0


def test_date_qualified_partial_button_saves_only_named_item(tracking, capsys):
    db, store, items, records = tracking
    items.add("운동", "boolean", None, "22:00")
    items.add("물", "quantity", "잔", "22:00")
    records.upsert("물", "2026-10-07", raw_input="물 3잔", value_num=3)
    unrelated_before = records.recent("물", 7, "2026-10-08")
    negative_input = "운동 2026-10-08 안 했어"
    assert (
        run_command(
            [
                "record",
                "운동",
                "--date",
                "2026-10-08",
                "--no-bool",
                "--raw",
                negative_input,
            ],
            db_path=str(db),
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "기록되었어: 운동 2026-10-08" in out
    saved = store.get_records_for_item(items.get("운동")["id"], 1, "2026-10-08")
    assert len(saved) == 1
    assert saved[0]["value_bool"] == 0
    assert saved[0]["raw_input"] == negative_input
    assert not store.record_exists(items.get("물")["id"], "2026-10-08")
    assert records.recent("물", 7, "2026-10-08") == unrelated_before


@pytest.mark.parametrize(
    "input_text,parsed_date",
    [("운동 2026-10-07 했어", "2026-10-07"), ("어제 운동했어", "2026-10-08")],
)
def test_fake_parser_date_flows_through_per_item_cli_to_sqlite(
    tracking, capsys, input_text, parsed_date
):
    """The fake supplies date interpretation; this only proves the parser/CLI handoff."""
    db, store, items, _ = tracking
    items.add("운동", "boolean", None, "22:00")
    items.add("물", "quantity", "잔", "22:00")
    payload = (
        '{"item_name":"운동","recorded_for":"' + parsed_date + '",'
        '"value_bool":true,"confidence":0.9}'
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
                )
            )
        )
    )
    parsed = NaturalLanguageParser(client, "synthetic-model").parse_record(
        input_text, items.list_all(), "2026-10-09T08:00:00+09:00"
    )
    boolean_flag = "--bool" if parsed.value_bool is True else "--no-bool"
    assert (
        run_command(
            [
                "record",
                parsed.item_name,
                "--date",
                parsed.recorded_for,
                boolean_flag,
                "--raw",
                input_text,
            ],
            db_path=str(db),
        )
        == 0
    )
    assert f"기록되었어: 운동 {parsed_date}" in capsys.readouterr().out
    saved = store.get_records_for_item(items.get("운동")["id"], 1, parsed_date)
    assert len(saved) == 1
    assert saved[0]["value_bool"] == 1
    assert saved[0]["raw_input"] == input_text
    assert not store.record_exists(items.get("물")["id"], parsed_date)


def test_fake_parser_timeout_does_not_create_record(tracking):
    _, store, items, _ = tracking
    items.add("운동", "boolean", None, "22:00")

    def timeout(**kwargs):
        raise TimeoutError("synthetic model timeout")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=timeout)))
    with pytest.raises(TimeoutError, match="synthetic model timeout"):
        NaturalLanguageParser(client, "synthetic-model").parse_record(
            "운동했어", items.list_all(), "2026-10-09T08:00:00+09:00"
        )
    assert not store.record_exists(items.get("운동")["id"], "2026-10-09")


@pytest.mark.parametrize("payload,expected_count", [
    ('{"item_name":"운동","recorded_for":"2026-10-09",'
     '"value_bool":true,"confidence":0.9}', 1),
    ("[]", 0),
    ("null", 0),
    ('{"item_name":["secret-model-output-marker"],"confidence":0.9}', 0),
])
def test_fake_parser_response_controls_cli_record_creation(
    tracking, capsys, payload, expected_count
):
    db, store, items, _ = tracking
    items.add("운동", "boolean", None, "22:00")
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
                )
            )
        )
    )
    parsed = NaturalLanguageParser(client, "synthetic-model").parse_record(
        "운동했어", items.list_all(), "2026-10-09T08:00:00+09:00"
    )
    assert parsed.recorded_for == "2026-10-09"
    if parsed.item_name is not None:
        assert run_command(
            ["record", parsed.item_name, "--date", parsed.recorded_for,
             "--bool" if parsed.value_bool is True else "--no-bool",
             "--raw", "운동했어"],
            db_path=str(db),
        ) == 0
    else:
        assert parsed.confidence == 0.0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == expected_count
    assert store.record_exists(items.get("운동")["id"], "2026-10-09") == bool(expected_count)
    captured = capsys.readouterr()
    assert "secret-model-output-marker" not in captured.out + captured.err


def test_batch_second_save_failure_leaves_first_commit_and_no_second_success(tracking, capsys):
    db, store, items, _ = tracking
    items.add("운동", "boolean", None, "22:00")
    items.add("물", "quantity", "잔", "22:00")
    assert (
        run_command(
            ["record", "운동", "--date", "2026-10-08", "--bool", "--raw", "synthetic"],
            db_path=str(db),
        )
        == 0
    )
    capsys.readouterr()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TRIGGER reject_water BEFORE INSERT ON records "
            "WHEN NEW.item_id = (SELECT id FROM tracked_items WHERE name = '물') "
            "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        run_command(
            ["record", "물", "--date", "2026-10-08", "--num", "2", "--raw", "synthetic"],
            db_path=str(db),
        )
    assert "기록되었어: 물" not in capsys.readouterr().out
    assert store.record_exists(items.get("운동")["id"], "2026-10-08")
    assert not store.record_exists(items.get("물")["id"], "2026-10-08")


def test_locked_sqlite_write_returns_no_success_and_preserves_record(tracking, capsys, monkeypatch):
    db, store, items, records = tracking
    items.add("운동", "boolean", None, "22:00")
    records.upsert("운동", "2026-10-07", raw_input="existing", value_bool=False)
    original_connect = sqlite3.connect

    def short_connect(*args, **kwargs):
        kwargs["timeout"] = 0.01
        return original_connect(*args, **kwargs)

    # Reserve the write lock; keep CLI reads real and bypass only its startup DDL/seed.
    monkeypatch.setattr(sqlite3, "connect", short_connect)
    monkeypatch.setattr(Storage, "initialize", lambda self: None)
    monkeypatch.setattr(TrackedItemManager, "seed_defaults", lambda self: None)
    lock = original_connect(db)
    try:
        lock.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            run_command(
                ["record", "운동", "--date", "2026-10-08", "--bool", "--raw", "new"],
                db_path=str(db),
            )
    finally:
        lock.rollback()
        lock.close()
    assert "기록되었어" not in capsys.readouterr().out
    assert not store.record_exists(items.get("운동")["id"], "2026-10-08")
    assert records.recent("운동", 7, "2026-10-09")[0]["raw_input"] == "existing"


def test_advice_failure_after_commit_leaves_saved_record_and_success_line(
    tracking, capsys, monkeypatch
):
    db, store, items, _ = tracking
    items.add("운동", "boolean", None, "22:00")

    def fail_advice(*args, **kwargs):
        raise RuntimeError("synthetic advice failure")

    monkeypatch.setattr(RecordManager, "advice_after_record", fail_advice)
    with pytest.raises(RuntimeError, match="synthetic advice failure"):
        run_command(
            ["record", "운동", "--date", "2026-10-08", "--bool", "--raw", "synthetic"],
            db_path=str(db),
        )
    assert "기록되었어: 운동 2026-10-08" in capsys.readouterr().out
    assert store.record_exists(items.get("운동")["id"], "2026-10-08")


@pytest.mark.parametrize("days,start", [(7, "2026-10-03"), (30, "2026-09-10")])
def test_period_start_and_ref_date_boundaries_exclude_future_rows(tracking, days, start):
    _, store, items, records = tracking
    items.add("운동", "boolean", None, "22:00")
    item_id = items.get("운동")["id"]
    before_start = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    for day, value in (
        (before_start, True),
        (start, True),
        ("2026-10-09", False),
        ("2026-10-10", True),
    ):
        records.upsert("운동", day, raw_input="synthetic", value_bool=value)
    rows = store.get_records_for_item(item_id, days, "2026-10-09")
    assert [row["recorded_for"] for row in rows] == ["2026-10-09", start]
    assert store.record_exists(item_id, "2026-10-10")
    assert records.summarize("운동", days, "2026-10-09") == (
        f"운동: 최근 {days}일 1/2회 수행 (50%)"
    )
    advice = records.advice_after_record("운동", "2026-10-09", days=days)
    assert f"최근 {days}일 1번" in advice
    assert f"최근 30일 {2 if days == 7 else 1}번" in advice


def test_boolean_false_and_missing_are_distinct_in_recorded_day_denominator(tracking):
    _, _, items, records = tracking
    items.add("운동", "boolean", None, "22:00")
    records.upsert("운동", "2026-10-07", raw_input="yes", value_bool=True)
    records.upsert("운동", "2026-10-08", raw_input="no", value_bool=False)
    assert records.summarize("운동", 7, "2026-10-09") == "운동: 최근 7일 1/2회 수행 (50%)"
    assert records.find_recent_missing("2026-10-09")[1] == "2026-10-06"


def test_null_value_is_counted_as_recorded_but_not_done(tracking):
    _, store, items, records = tracking
    items.add("운동", "boolean", None, "22:00")
    records.upsert("운동", "2026-10-08", raw_input="ambiguous")
    assert records.summarize("운동", 7, "2026-10-09") == "운동: 최근 7일 0/1회 수행 (0%)"
    assert store.record_exists(items.get("운동")["id"], "2026-10-08")


def test_repeated_scheduled_window_resends_after_database_reopen(tracking):
    db, store, items, records = tracking
    items.add("운동", "boolean", None, "08:00")
    sent = []
    Dispatcher(items, records, sent.append).run(datetime(2026, 10, 9, 8, 0, tzinfo=KST))
    reopened = Storage(str(db))
    reopened_items = TrackedItemManager(reopened)
    Dispatcher(reopened_items, RecordManager(reopened, reopened_items), sent.append).run(
        datetime(2026, 10, 9, 8, 1, tzinfo=KST)
    )
    assert len(sent) == 2
    assert all("2026-10-09" in text for text in sent)
    assert store.get_tracked_item_by_name("운동")["pending_recorded_for"] == "2026-10-09"


def test_send_then_state_failure_allows_duplicate_after_restart(tracking, monkeypatch):
    db, store, items, records = tracking
    items.add("운동", "boolean", None, "08:00")
    sent = []

    def fail_pending(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic pending failure")

    monkeypatch.setattr(store, "set_pending_since", fail_pending)
    with pytest.raises(sqlite3.OperationalError, match="synthetic pending failure"):
        Dispatcher(items, records, sent.append).run(datetime(2026, 10, 9, 8, 0, tzinfo=KST))
    assert len(sent) == 1
    assert store.get_tracked_item_by_name("운동")["pending_since"] is None

    reopened = Storage(str(db))
    reopened_items = TrackedItemManager(reopened)
    Dispatcher(reopened_items, RecordManager(reopened, reopened_items), sent.append).run(
        datetime(2026, 10, 9, 8, 1, tzinfo=KST)
    )
    assert len(sent) == 2


@pytest.mark.parametrize(
    "now,expected",
    [
        (datetime(2026, 10, 8, 23, 0, tzinfo=timezone.utc), 1),
        (datetime(2026, 10, 9, 8, 0), 1),
        (datetime(2026, 10, 9, 8, 30, tzinfo=KST), 0),
    ],
)
def test_schedule_window_timezone_and_exclusive_start(tracking, now, expected):
    _, _, items, records = tracking
    items.add("운동", "boolean", None, "08:00")
    sent = []
    messages = Dispatcher(items, records, sent.append).run(now)
    assert len(messages) == expected
    assert len(sent) == expected


@pytest.mark.parametrize("status,ok", [(401, False), (200, False)])
def test_sender_records_rejected_http_response_as_outbound(
    tracking, tmp_path, monkeypatch, status, ok
):
    _, store, items, records = tracking
    items.add("운동", "boolean", None, "08:00")
    workspace = tmp_path / "session"
    workspace.mkdir()
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: SimpleNamespace(status_code=status, json=lambda: {"ok": ok}),
    )
    messages = Dispatcher(items, records, _make_telegram_sender(workspace)).run(
        datetime(2026, 10, 9, 8, 0, tzinfo=KST)
    )
    history = SessionManager(workspace).get_or_create("telegram:123").get_history()
    assert len(messages) == 1
    assert "운동" in history[-1]["content"]
    item = store.get_tracked_item_by_name("운동")
    assert item["pending_recorded_for"] == "2026-10-09"
    assert item["last_asked_at"] is not None


def test_sender_timeout_does_not_record_outbound(tracking, tmp_path, monkeypatch):
    _, _, _, _ = tracking
    workspace = tmp_path / "session"
    workspace.mkdir()

    def timeout(*args, **kwargs):
        raise httpx.TimeoutException("synthetic timeout")

    monkeypatch.setattr(httpx, "post", timeout)
    with pytest.raises(httpx.TimeoutException):
        _make_telegram_sender(workspace)("synthetic timeout")
    assert SessionManager(workspace).get_or_create("telegram:123").get_history() == []
