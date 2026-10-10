import asyncio
import importlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

from msalt.storage import Storage
from msalt.watch.evaluation import Evaluator
from msalt.watch.evaluation_store import EvaluationStore
from msalt.watch.store import WatchStore

NOW = datetime(2026, 10, 10, 0, 5, tzinfo=timezone.utc)
TARGET = "123456"


@pytest.fixture
def setup(tmp_path):
    storage = Storage(str(tmp_path / "notify.db"))
    storage.initialize()
    watches = WatchStore(storage)
    item = watches.add("Supply", description="fixture", keywords=[], excluded_keywords=[])
    item = watches.resume(item.id, expected_revision=1)
    return storage, watches, item


def candidates(storage, count=1):
    for i in range(count):
        storage.insert_article(
            "fixture",
            f"GPU news {i + 1}",
            f"https://fixture/{i + 1}",
            "GPU supply grows",
            "fixture",
        )
    Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="Supply changed", evidence="GPU"),
    ).run(max_calls=10)


def api(storage):
    return importlib.import_module("msalt.watch.notification_store").NotificationStore(storage)


def dispatcher(store, post):
    return importlib.import_module("msalt.watch.dispatcher").Dispatcher(store, post=post)


class Post:
    def __init__(self, result=(200, {"ok": True, "result": {"message_id": 321}}), hook=None):
        self.result, self.hook, self.payloads = result, hook, []

    async def __call__(self, payload):
        self.payloads.append(payload)
        if self.hook:
            self.hook()
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def send(store, post, now=NOW):
    return asyncio.run(dispatcher(store, post).run(TARGET, now=now))


def test_additive_notification_schema(setup):
    storage, _, _ = setup
    with storage._connect() as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "watch_notifications",
        "watch_notification_urls",
        "watch_notification_candidates",
        "watch_notification_attempts",
        "watch_notification_audit",
        "watch_notification_settings",
    } <= names


def test_default_disabled_and_shared_enable_confirmation(setup):
    storage, _, _ = setup
    candidates(storage)
    store, post = api(storage), Post()
    assert not store.status()["enabled"]
    assert send(store, post)["state"] == "disabled"
    assert post.payloads == [] and store.status()["deliveries"] == []
    with pytest.raises(ValueError):
        store.set_enabled(True)
    store.set_enabled(True, confirm=True)
    assert api(storage).status()["enabled"]
    assert send(store, post)["state"] == "sent"
    store.set_enabled(False, confirm=True)
    assert not api(storage).status()["enabled"]


def test_current_high_fifo_same_url_snapshot_and_no_model_regeneration(setup):
    storage, watches, item = setup
    other = watches.add("Other", description="fixture", keywords=[], excluded_keywords=[])
    watches.resume(other.id, expected_revision=1)
    candidates(storage, 5)
    with storage._connect() as conn:
        conn.execute("UPDATE watch_evaluations SET importance='medium' WHERE article_id=2")
        conn.execute(
            "UPDATE watch_evaluations SET relevant=0,status='irrelevant' WHERE article_id=3"
        )
        conn.execute("UPDATE news_articles SET title='MUTATED',url='https://changed/' || id")
    store, post = api(storage), Post()
    store.set_enabled(True, confirm=True)
    assert send(store, post)["state"] == "sent"
    text = post.payloads[0]["text"]
    assert text.count("https://fixture/1") == 1
    assert "Supply" in text and "Other" in text and "Supply changed" in text
    assert text.index("GPU news 1") < text.index("GPU news 4") < text.index("GPU news 5")
    assert "MUTATED" not in text and "https://changed/" not in text
    assert "GPU news 2" not in text and "GPU news 3" not in text
    assert len(store.show(store.status()["deliveries"][0]["delivery_id"])["candidates"]) == 6


@pytest.mark.parametrize(
    "instant,expected",
    [
        ("2026-10-09T23:59:59+00:00", "quiet"),
        ("2026-10-10T00:00:00+00:00", "sent"),
        ("2026-10-10T11:59:59+00:00", "sent"),
        ("2026-10-10T12:00:00+00:00", "quiet"),
    ],
)
def test_kst_window_boundaries(setup, instant, expected):
    storage, _, _ = setup
    candidates(storage)
    store, post = api(storage), Post()
    store.set_enabled(True, confirm=True)
    assert send(store, post, datetime.fromisoformat(instant))["state"] == expected
    assert len(post.payloads) == int(expected == "sent")


def test_hour_day_and_three_article_backlog_limits(setup):
    storage, _, _ = setup
    candidates(storage, 10)
    # More than evaluator's single-run ten-call cap, without a new collector.
    for i in range(10, 22):
        storage.insert_article(
            "fixture", f"GPU news {i + 1}", f"https://fixture/{i + 1}", "GPU", "fixture"
        )
    Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="Supply changed", evidence="GPU"),
    ).run()
    Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="Supply changed", evidence="GPU"),
    ).run()
    store, post = api(storage), Post()
    store.set_enabled(True, confirm=True)
    for hour in range(6):
        result = send(store, post, NOW + timedelta(hours=hour))
        assert result["state"] == "sent"
        assert len(post.payloads[-1]["text"]) <= 3500
        assert post.payloads[-1]["text"].count("https://fixture/") == 3
        assert send(store, post, NOW + timedelta(hours=hour, minutes=20))["state"] == "limited"
    assert send(store, post, NOW + timedelta(hours=6))["state"] == "limited"
    assert len(post.payloads) == 6
    assert send(store, post, NOW + timedelta(days=1))["state"] == "sent"
    assert len(post.payloads) == 7


def test_real_workers_one_atomic_claim_and_no_duplicate_post(setup):
    storage, _, _ = setup
    candidates(storage, 4)
    store = api(storage)
    store.set_enabled(True, confirm=True)
    barrier = Barrier(2)

    def worker():
        post = Post()
        barrier.wait()
        result = send(api(storage), post)
        return result, post.payloads

    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(lambda _: worker(), range(2)))
    assert sum(len(p) for _, p in outputs) == 1
    assert len(store.status()["deliveries"]) == 1
    assert len(store.show(store.status()["deliveries"][0]["delivery_id"])["attempts"]) == 1


def test_pending_resume_committed_snapshot_and_stale_all_batch_cancel(setup):
    storage, watches, item = setup
    other = watches.add("Other", description="fixture", keywords=[], excluded_keywords=[])
    other = watches.resume(other.id, expected_revision=1)
    candidates(storage, 2)
    store = api(storage)
    store.set_enabled(True, confirm=True)
    row = store.prepare(TARGET, now=NOW)
    watches.pause(item.id, expected_revision=item.revision)
    post = Post()
    assert send(store, post)["state"] == "cancelled"
    assert store.show(row["delivery_id"])["state"] == "cancelled"
    assert post.payloads == []
    assert send(store, post)["state"] == "limited"
    assert send(store, post, NOW + timedelta(hours=1))["state"] == "sent"
    assert "• Supply:" not in post.payloads[0]["text"]
    assert "Other" in post.payloads[0]["text"]


@pytest.mark.parametrize("change", ["disable", "delete", "update"])
def test_final_gate_cancels_on_any_control_change(setup, change):
    storage, watches, item = setup
    candidates(storage)
    store = api(storage)
    store.set_enabled(True, confirm=True)
    row = store.prepare(TARGET, now=NOW)
    if change == "disable":
        api(storage).set_enabled(False, confirm=True)
    elif change == "delete":
        watches.delete(item.id, expected_revision=item.revision)
    else:
        watches.update(item.id, expected_revision=item.revision, description="changed")
    from msalt.watch.sender import NotificationSender

    post = Post()
    assert (
        asyncio.run(NotificationSender(store, post=post).send(row["delivery_id"], now=NOW))
        == "cancelled"
    )
    assert post.payloads == []


@pytest.mark.parametrize(
    "response,want",
    [
        ((200, {"ok": True, "result": {"message_id": 42}}), "sent"),
        ((200, {"ok": True}), "unknown"),
        ((503, {"ok": True, "result": {"message_id": 42}}), "unknown"),
        ((503, {"ok": False, "error_code": 429}), "rejected"),
        ((200, {"ok": False}), "rejected"),
        ((400, {}), "unknown"),
        ((200, ["ok"]), "unknown"),
        ((200, {"ok": 1, "result": {"message_id": 42}}), "unknown"),
        ((200, {"ok": True, "result": {"message_id": True}}), "unknown"),
        (TimeoutError("private-token"), "unknown"),
    ],
)
def test_strict_delivery_classification_and_saved_attempts(setup, response, want):
    storage, _, _ = setup
    candidates(storage)
    store, post = api(storage), Post(response)
    store.set_enabled(True, confirm=True)
    result = send(store, post)
    assert result["state"] == want
    row = store.show(result["delivery_id"])
    assert row["state"] == want and len(row["attempts"]) == 1
    assert row["attempts"][0]["state"] == want
    assert "private-token" not in json.dumps(store.status())
    if want in ("sent", "unknown"):
        assert send(store, post, NOW + timedelta(days=1))["state"] == "empty"
        assert len(post.payloads) == 1


def test_rejected_extra_attempt_newslot_and_cancel_preserves_spent_url_history(setup):
    storage, _, _ = setup
    candidates(storage)
    store, post = api(storage), Post((400, {"ok": False}))
    store.set_enabled(True, confirm=True)
    assert send(store, post)["state"] == "rejected"
    row = store.prepare(TARGET, now=NOW + timedelta(hours=1))
    store.set_enabled(False, confirm=True)
    from msalt.watch.sender import NotificationSender

    assert (
        asyncio.run(
            NotificationSender(store, post=post).send(
                row["delivery_id"], now=NOW + timedelta(hours=1)
            )
        )
        == "cancelled"
    )
    store.set_enabled(True, confirm=True)
    assert send(store, post, NOW + timedelta(hours=2))["state"] == "rejected"
    assert send(store, post, NOW + timedelta(hours=3))["state"] == "empty"
    assert len(post.payloads) == 2
    with storage._connect() as conn:
        assert conn.execute("SELECT attempts FROM watch_notification_urls").fetchone()[0] == 2


def test_unknown_resolution_receipt_no_post_and_retry_shared_cap_audit(setup):
    storage, _, _ = setup
    candidates(storage)
    store, post = api(storage), Post(TimeoutError())
    store.set_enabled(True, confirm=True)
    row = send(store, post)
    with pytest.raises(ValueError):
        store.resolve(row["delivery_id"], outcome="sent", confirm=True)
    with pytest.raises(ValueError):
        store.resolve(row["delivery_id"], outcome="retry")
    store.resolve(
        row["delivery_id"],
        outcome="retry",
        confirm=True,
        evidence="operator confirmed absent receipt",
    )
    assert send(store, post)["state"] == "limited"
    row2 = send(store, post, NOW + timedelta(hours=1))
    assert row2["state"] == "unknown"
    with pytest.raises(ValueError):
        store.resolve(row2["delivery_id"], outcome="retry", confirm=True, evidence="absent")
    store.resolve(
        row2["delivery_id"],
        outcome="sent",
        confirm=True,
        evidence="Human confirmed receipt",
        message_id=77,
    )
    assert send(store, post, NOW + timedelta(days=1))["state"] == "empty"
    assert len(post.payloads) == 2
    assert store.show(row2["delivery_id"])["ack_message_id"] == 77
    assert len(store.show(row2["delivery_id"])["audit"]) == 1


def test_crash_sending_startup_unknown_and_ownership_guard(setup):
    storage, _, _ = setup
    candidates(storage)
    store = api(storage)
    store.set_enabled(True, confirm=True)
    row = store.prepare(TARGET, now=NOW)
    token = store.start_sending(row["delivery_id"], now=NOW)
    assert token and store.show(row["delivery_id"])["state"] == "sending"
    with pytest.raises(ValueError):
        store.resolve(row["delivery_id"], outcome="retry", confirm=True, evidence="absent")
    assert store.finish(row["delivery_id"], "wrong-owner", state="sent", message_id=1) is False
    api(storage).recover()
    assert store.show(row["delivery_id"])["state"] == "unknown"
    post = Post()
    assert send(store, post, NOW + timedelta(days=1))["state"] == "empty"
    assert post.payloads == []


def test_claim_database_failure_post_zero_and_ack_failure_never_resends(setup):
    storage, _, _ = setup
    candidates(storage)
    store, post = api(storage), Post()
    store.set_enabled(True, confirm=True)
    with storage._connect() as conn:
        conn.execute(
            "CREATE TRIGGER reject_claim BEFORE INSERT ON watch_notifications BEGIN SELECT RAISE(ABORT,'fixture'); END"
        )
    with pytest.raises(sqlite3.Error):
        send(store, post)
    assert post.payloads == [] and store.status()["deliveries"] == []
    with storage._connect() as conn:
        conn.execute("DROP TRIGGER reject_claim")
        conn.execute(
            "CREATE TRIGGER reject_ack BEFORE UPDATE ON watch_notifications WHEN NEW.state IN ('sent','unknown') BEGIN SELECT RAISE(ABORT,'fixture'); END"
        )
    result = send(store, post)
    assert result["state"] == "sending"
    assert len(post.payloads) == 1
    assert send(store, post, NOW + timedelta(hours=1))["state"] == "empty"
    assert len(post.payloads) == 1


def test_post_outside_transaction_and_disable_after_start_does_not_cancel(setup):
    storage, _, _ = setup
    candidates(storage)
    store = api(storage)
    store.set_enabled(True, confirm=True)

    def hook():
        conn = storage._connect()
        conn.execute("BEGIN IMMEDIATE")
        assert conn.execute("SELECT state FROM watch_notifications").fetchone()[0] == "sending"
        conn.rollback()
        conn.close()
        api(storage).set_enabled(False, confirm=True)

    post = Post(hook=hook)
    assert send(store, post)["state"] == "sent"
    assert len(post.payloads) == 1


def test_global_fifo_later_watch_not_starved_by_first_hundred(setup):
    storage, watches, first = setup
    later = watches.add("Later", description="fixture", keywords=[], excluded_keywords=[])
    later = watches.resume(later.id, expected_revision=1)
    # Later Watch owns the globally oldest article; first Watch has >100 newer rows.
    for i in range(1, 103):
        storage.insert_article("fixture", f"GPU news {i}", f"https://fifo/{i}", "GPU", "fixture")
    evaluations = EvaluationStore(storage)
    for _ in range(22):
        Evaluator(
            evaluations,
            lambda s: dict(relevant=True, importance="high", reason="Supply", evidence="GPU"),
        ).run()
    with storage._connect() as conn:
        conn.execute("DELETE FROM watch_evaluations WHERE watch_id=? AND article_id=1", (first.id,))
        conn.execute("DELETE FROM watch_evaluations WHERE watch_id=? AND article_id>1", (later.id,))
    store, post = api(storage), Post()
    store.set_enabled(True, confirm=True)
    assert send(store, post)["state"] == "sent"
    assert post.payloads[0]["text"].index("https://fifo/1") < post.payloads[0]["text"].index(
        "https://fifo/2"
    )


def test_long_reasons_all_watch_names_and_url_intact(setup):
    storage, watches, _ = setup
    for i in range(18):
        item = watches.add(
            f"Watch-{i}-" + "x" * 60, description="fixture", keywords=[], excluded_keywords=[]
        )
        watches.resume(item.id, expected_revision=1)
    candidates(storage)
    evaluations = EvaluationStore(storage)
    Evaluator(
        evaluations,
        lambda s: dict(relevant=True, importance="high", reason="y" * 500, evidence="GPU"),
    ).run()
    with storage._connect() as conn:
        conn.execute("UPDATE watch_evaluations SET reason=?", ("y" * 500,))
    store, post = api(storage), Post()
    store.set_enabled(True, confirm=True)
    assert send(store, post)["state"] == "sent"
    text = post.payloads[0]["text"]
    assert len(text) <= 3500 and text.count("https://fixture/1") == 1
    assert all(f"Watch-{i}-" in text for i in range(18))


def test_pending_restart_resume_no_extra_attempt_and_later_slot_rebuild(setup):
    storage, _, _ = setup
    candidates(storage)
    store = api(storage)
    store.set_enabled(True, confirm=True)
    prepared = store.prepare(TARGET, now=NOW)
    post = Post()
    assert send(api(storage), post)["delivery_id"] == prepared["delivery_id"]
    assert len(store.show(prepared["delivery_id"])["attempts"]) == 1
    # Distinct URL new candidate, pending crosses hour: preserve old quota and re-reserve.
    candidates(storage, 2)
    prepared2 = store.prepare(TARGET, now=NOW + timedelta(hours=1))
    result = send(api(storage), post, NOW + timedelta(hours=2))
    assert result["state"] == "sent" and result["delivery_id"] != prepared2["delivery_id"]
    assert store.show(prepared2["delivery_id"])["state"] == "cancelled"
    assert len(store.show(prepared2["delivery_id"])["attempts"]) == 0


def test_real_workers_last_day_slot_do_not_exceed_quota(setup):
    storage, _, _ = setup
    candidates(storage, 10)
    store = api(storage)
    store.set_enabled(True, confirm=True)
    for hour in range(5):
        send(store, Post((400, {"ok": False})), NOW + timedelta(hours=hour))
    barrier = Barrier(2)

    def worker(hour):
        post = Post()
        barrier.wait()
        result = send(api(storage), post, NOW + timedelta(hours=hour))
        return result, post.payloads

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, [5, 6]))
    assert sum(len(p) for _, p in results) == 1
    assert len(store.status()["deliveries"]) == 6


def test_utc_date_change_does_not_reset_kst_day_quota(setup):
    storage, _, _ = setup
    candidates(storage, 10)
    store = api(storage)
    store.set_enabled(True, confirm=True)
    for hour in range(6):
        send(store, Post((400, {"ok": False})), NOW + timedelta(hours=hour))
    assert send(store, Post(), NOW + timedelta(hours=11))["state"] == "limited"
    assert send(store, Post(), NOW + timedelta(hours=16))["state"] == "quiet"
    assert send(store, Post(), NOW + timedelta(days=1))["state"] == "sent"


def test_ack_url_survives_new_revision_and_backlog_limit(setup):
    storage, watches, item = setup
    candidates(storage)
    store, post = api(storage), Post()
    store.set_enabled(True, confirm=True)
    assert send(store, post)["state"] == "sent"
    watches.update(item.id, expected_revision=item.revision, description="revision change")
    # New saved article ID may reuse old snapshot URL after source mutation.
    with storage._connect() as conn:
        conn.execute("UPDATE news_articles SET url='https://moved/1'")
    storage.insert_article("fixture", "New GPU", "https://fixture/1", "GPU", "fixture")
    Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="Changed", evidence="GPU"),
    ).run()
    assert send(store, post, NOW + timedelta(hours=1))["state"] == "empty"
    assert len(post.payloads) == 1


def test_notification_migration_repeat_and_failure_preserve_all_rows(setup, monkeypatch):
    storage, _, _ = setup
    candidates(storage, 2)
    store = api(storage)
    store.set_enabled(True, confirm=True)
    send(store, Post(TimeoutError()))
    storage.insert_tracked_item("fixture", "quantity", "units", "09:00")
    with storage._connect() as conn:
        conn.execute(
            "INSERT INTO records(item_id, recorded_for, value_num, raw_input) VALUES(1,'2026-10-09',1,'fixture')"
        )
        conn.execute(
            "INSERT INTO tracking_deliveries(item_id,recorded_for,kind,slot_utc,state,claimed_at) VALUES(1,'2026-10-10','scheduled','2026-10-10T00:00:00Z','unknown','2026-10-10T00:00:00Z')"
        )
        conn.execute("CREATE TABLE local_settings(name TEXT PRIMARY KEY,value TEXT)")
        conn.execute("INSERT INTO local_settings VALUES('fixture','preserve')")
        for identifier, state in [("ack", "sent"), ("uncertain", "unknown")]:
            conn.execute(
                "INSERT INTO news_deliveries(delivery_id,target,kst_date,slot,created_at,updated_at,state,generation_started) VALUES(?,'fixture','2026-10-10',?,1,1,?,1)",
                (identifier, identifier, state),
            )
            conn.execute(
                "INSERT INTO news_delivery_parts(delivery_id,part_no,text,hash,state,attempts,message_id,ack_at) VALUES(?,0,'fixture','hash',?,1,?,?)",
                (
                    identifier,
                    state,
                    123 if state == "sent" else None,
                    1 if state == "sent" else None,
                ),
            )
            conn.execute(
                "INSERT INTO news_delivery_articles VALUES(?,?,1)",
                (identifier, "https://fixture/" + identifier),
            )
            conn.execute(
                "INSERT INTO news_delivery_attempts(attempt_id,delivery_id,created_at,updated_at,outcome) VALUES(?,?,1,1,?)",
                (identifier, identifier, state),
            )
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        before = {t: [tuple(r) for r in conn.execute("SELECT * FROM " + t)] for t in tables}
    storage.initialize()
    storage.initialize()

    def fail(conn):
        conn.execute("UPDATE watch_notification_settings SET enabled=0")
        conn.execute("CREATE TABLE new_fixture(value TEXT)")
        raise RuntimeError("fixture migration failure")

    from msalt.watch import notification_store

    monkeypatch.setattr(notification_store, "migrate_notifications", fail)
    with pytest.raises(RuntimeError):
        storage.initialize()
    with storage._connect() as conn:
        after = {t: [tuple(r) for r in conn.execute("SELECT * FROM " + t)] for t in tables}
        assert before == after
        assert (
            conn.execute("SELECT name FROM sqlite_master WHERE name='new_fixture'").fetchall() == []
        )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_large_backlog_bounds_materialized_article_snapshots(setup, monkeypatch):
    storage, _, _ = setup
    candidates(storage)
    # Seed real persisted evaluation snapshots; no model/API calls needed for backlog.
    with storage._connect() as conn:
        original = dict(conn.execute("SELECT * FROM watch_evaluations").fetchone())
        for i in range(2, 202):
            conn.execute(
                "INSERT INTO news_articles(id,source,title,url) VALUES(?,?,?,?)",
                (i, "fixture", f"GPU {i}", f"https://backlog/{i}"),
            )
            snapshot = json.loads(original["input_snapshot"])
            snapshot["article"].update(id=i, title=f"GPU {i}", url=f"https://backlog/{i}")
            conn.execute(
                "INSERT INTO watch_evaluations(watch_id,revision,article_id,status,relevant,importance,reason,evidence,input_snapshot,input_hash,created_at,updated_at) VALUES(?,?,?,'relevant',1,'high','Changed','GPU',?,'fixture',1,1)",
                (original["watch_id"], original["revision"], i, json.dumps(snapshot)),
            )
    connect = storage._connect
    materialized = []

    class Cursor:
        def __init__(self, cursor, sql):
            self.cursor, self.sql = cursor, sql

        def fetchall(self):
            rows = self.cursor.fetchall()
            if "SELECT e.*" in self.sql:
                materialized.extend(rows)
            return rows

        def __getattr__(self, key):
            return getattr(self.cursor, key)

    class Connection:
        def __init__(self):
            self.conn = connect()

        def execute(self, sql, parameters=()):
            return Cursor(self.conn.execute(sql, parameters), sql)

        def __getattr__(self, key):
            return getattr(self.conn, key)

    store = api(storage)
    store.set_enabled(True, confirm=True)
    monkeypatch.setattr(storage, "_connect", Connection)
    prepared = store.prepare(TARGET, now=NOW)
    assert prepared["state"] == "pending"
    assert len(materialized) <= 60


def test_sending_commit_failure_rolls_back_attempt_and_post_zero(setup):
    storage, _, _ = setup
    candidates(storage)
    store, post = api(storage), Post()
    store.set_enabled(True, confirm=True)
    with storage._connect() as conn:
        conn.execute(
            "CREATE TRIGGER fail_start BEFORE INSERT ON watch_notification_attempts BEGIN SELECT RAISE(ABORT,'fixture'); END"
        )
    with pytest.raises(sqlite3.Error):
        send(store, post)
    assert post.payloads == []
    row = store.show(store.status()["deliveries"][0]["delivery_id"])
    assert row["state"] == "pending" and row["attempts"] == []
    with storage._connect() as conn:
        assert conn.execute("SELECT attempts FROM watch_notification_urls").fetchone()[0] == 0


def test_late_ack_after_recovery_and_after_manual_resolution_owner_fenced(setup):
    storage, _, _ = setup
    candidates(storage)
    store = api(storage)
    store.set_enabled(True, confirm=True)
    prepared = store.prepare(TARGET, now=NOW)
    token = store.start_sending(prepared["delivery_id"], now=NOW)
    store.recover()
    assert store.finish(prepared["delivery_id"], token, state="sent", message_id=99)
    assert store.show(prepared["delivery_id"])["state"] == "sent"
    candidates(storage, 2)
    prepared2 = store.prepare(TARGET, now=NOW + timedelta(hours=1))
    token2 = store.start_sending(prepared2["delivery_id"], now=NOW + timedelta(hours=1))
    store.recover()
    store.resolve(
        prepared2["delivery_id"], outcome="sent", confirm=True, evidence="received", message_id=77
    )
    assert not store.finish(prepared2["delivery_id"], token2, state="rejected")
    assert store.show(prepared2["delivery_id"])["ack_message_id"] == 77


def test_actual_process_crash_committed_sending_never_auto_reposts(setup):
    import os
    import subprocess
    import sys

    storage, _, _ = setup
    candidates(storage)
    store = api(storage)
    store.set_enabled(True, confirm=True)
    prepared = store.prepare(TARGET, now=NOW)
    script = "from msalt.storage import Storage; from msalt.watch.notification_store import NotificationStore; from datetime import datetime; import sys,os; s=NotificationStore(Storage(sys.argv[1])); assert s.start_sending(sys.argv[2],now=datetime.fromisoformat(sys.argv[3])); os._exit(73)"
    completed = subprocess.run(
        [sys.executable, "-c", script, storage.db_path, prepared["delivery_id"], NOW.isoformat()],
        env=dict(os.environ),
        capture_output=True,
        timeout=20,
    )
    assert completed.returncode == 73, completed.stderr
    assert store.show(prepared["delivery_id"])["state"] == "sending"
    post = Post()
    assert send(api(storage), post, NOW + timedelta(hours=1))["state"] == "empty"
    assert store.show(prepared["delivery_id"])["state"] == "unknown"
    assert post.payloads == []


def test_emoji_message_respects_telegram_units_without_trimming_urls(setup):
    storage, watches, _ = setup
    for i in range(18):
        item = watches.add(
            f"{i}" + "😀" * 70, description="fixture", keywords=[], excluded_keywords=[]
        )
        watches.resume(item.id, expected_revision=1)
    candidates(storage)
    Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="🚀" * 500, evidence="GPU"),
    ).run()
    with storage._connect() as conn:
        conn.execute("UPDATE watch_evaluations SET reason=?", ("🚀" * 500,))
    store, post = api(storage), Post()
    store.set_enabled(True, confirm=True)
    assert send(store, post)["state"] == "sent"
    text = post.payloads[0]["text"]
    assert len(text.encode("utf-16-le")) // 2 <= 3500
    assert text.endswith("https://fixture/1") and len(text) <= 3500


def test_upgrade_pre_notification_database_preserves_existing_watch_and_other_rows(setup):
    storage, _, _ = setup
    candidates(storage, 2)
    with storage._connect() as conn:
        for table in [
            "watch_notification_audit",
            "watch_notification_attempts",
            "watch_notification_candidates",
            "watch_notification_urls",
            "watch_notifications",
            "watch_notification_settings",
        ]:
            conn.execute("DROP TABLE " + table)
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        before = {t: [tuple(r) for r in conn.execute("SELECT * FROM " + t)] for t in tables}
    storage.initialize()
    with storage._connect() as conn:
        assert before == {t: [tuple(r) for r in conn.execute("SELECT * FROM " + t)] for t in tables}
        assert conn.execute("SELECT enabled FROM watch_notification_settings").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
