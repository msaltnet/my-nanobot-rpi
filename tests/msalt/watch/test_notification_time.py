import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event

import pytest

from msalt.storage import Storage
from msalt.watch.evaluation import Evaluator
from msalt.watch.evaluation_store import EvaluationStore
from msalt.watch.notification_store import NotificationStore
from msalt.watch.sender import NotificationSender
from msalt.watch.store import WatchStore


@pytest.mark.parametrize("boundary_hour", [1, 12])
def test_sending_rechecks_clock_after_waiting_for_real_writer_lock(
    tmp_path, monkeypatch, boundary_hour
):
    storage = Storage(str(tmp_path / "boundary.db"))
    storage.initialize()
    watches = WatchStore(storage)
    item = watches.add("fixture", description="fixture", keywords=[], excluded_keywords=[])
    watches.resume(item.id, expected_revision=1)
    storage.insert_article("fixture", "GPU change", "https://fixture/1", "GPU", "fixture")
    Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="change", evidence="GPU"),
    ).run()
    store = NotificationStore(storage)
    store.set_enabled(True, confirm=True)
    after = datetime(2026, 10, 10, boundary_hour, 0, 1, tzinfo=timezone.utc)
    before = after - timedelta(seconds=2)
    prepared = store.prepare("123456", now=before)
    module = __import__("msalt.watch.notification_store", fromlist=["clock"])
    actual_clock = module.clock
    current_time = [before]
    monkeypatch.setattr(
        module, "clock", lambda now=None: actual_clock(now) if now is not None else current_time[0]
    )
    waiting = Event()
    original_connect = storage._connect

    def observed_connect():
        conn = original_connect()
        conn.set_trace_callback(lambda sql: waiting.set() if sql == "BEGIN IMMEDIATE" else None)
        return conn

    monkeypatch.setattr(storage, "_connect", observed_connect)
    writer = original_connect()
    writer.execute("BEGIN IMMEDIATE")
    posted_at = []

    async def post(payload):
        posted_at.append(current_time[0])
        return 200, {"ok": True, "result": {"message_id": 1}}

    def send():
        return asyncio.run(NotificationSender(store, post=post).send(prepared["delivery_id"]))

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(send)
            assert waiting.wait(5), "sender did not reach real SQLite write-lock wait"
            assert not future.done()
            current_time[0] = after
            writer.commit()
            result = future.result(timeout=5)
    finally:
        writer.rollback()
        writer.close()
    assert posted_at == [], (
        f"stale slot sent at {posted_at}; result={result}; reserved={prepared['slot_utc']}"
    )
    assert result == "cancelled"


@pytest.mark.parametrize("boundary_hour", [1, 12])
def test_prepare_rechecks_clock_after_final_claim_writer_wait(tmp_path, monkeypatch, boundary_hour):
    storage = Storage(str(tmp_path / "prepare-boundary.db"))
    storage.initialize()
    watches = WatchStore(storage)
    item = watches.add("fixture", description="fixture", keywords=[], excluded_keywords=[])
    watches.resume(item.id, expected_revision=1)
    storage.insert_article("fixture", "GPU change", "https://fixture/1", "GPU", "fixture")
    Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="change", evidence="GPU"),
    ).run()
    store = NotificationStore(storage)
    store.set_enabled(True, confirm=True)
    after = datetime(2026, 10, 10, boundary_hour, 0, 1, tzinfo=timezone.utc)
    before = after - timedelta(seconds=2)
    module = __import__("msalt.watch.notification_store", fromlist=["clock"])
    actual_clock = module.clock
    current_time = [before]
    monkeypatch.setattr(
        module, "clock", lambda now=None: actual_clock(now) if now is not None else current_time[0]
    )
    scanned, locked, waiting = Event(), Event(), Event()
    original_scan, original_connect = store._scan, storage._connect

    def scan(key):
        result = original_scan(key)
        scanned.set()
        assert locked.wait(5)
        return result

    def observed_connect():
        conn = original_connect()
        conn.set_trace_callback(
            lambda sql: waiting.set() if sql == "BEGIN IMMEDIATE" and locked.is_set() else None
        )
        return conn

    monkeypatch.setattr(store, "_scan", scan)
    monkeypatch.setattr(storage, "_connect", observed_connect)
    writer = original_connect()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(store.prepare, "123456")
            assert scanned.wait(5)
            writer.execute("BEGIN IMMEDIATE")
            locked.set()
            assert waiting.wait(5)
            assert not future.done()
            current_time[0] = after
            writer.commit()
            result = future.result(timeout=5)
    finally:
        writer.rollback()
        writer.close()
    if boundary_hour == 12:
        assert result["state"] == "quiet", result
        assert store.status()["deliveries"] == []
    else:
        assert result["slot_utc"] == after.replace(minute=0, second=0).isoformat(), result


@pytest.mark.parametrize("boundary_hour", [1, 12])
@pytest.mark.parametrize("diagnostic", [False, True])
def test_sending_commit_reader_wait_checks_reserved_window(
    tmp_path, monkeypatch, boundary_hour, diagnostic
):
    storage = Storage(str(tmp_path / "commit-boundary.db"))
    storage.initialize()
    watches = WatchStore(storage)
    item = watches.add("fixture", description="fixture", keywords=[], excluded_keywords=[])
    watches.resume(item.id, expected_revision=1)
    storage.insert_article("fixture", "GPU change", "https://fixture/1", "GPU", "fixture")
    Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="change", evidence="GPU"),
    ).run()
    store = NotificationStore(storage)
    store.set_enabled(True, confirm=True)
    after = datetime(2026, 10, 10, boundary_hour, 0, 1, tzinfo=timezone.utc)
    before = after - timedelta(seconds=2)
    prepared = store.prepare("123456", now=before)
    module = __import__("msalt.watch.notification_store", fromlist=["clock"])
    actual_clock = module.clock
    current_time = [before]
    monkeypatch.setattr(
        module, "clock", lambda now=None: actual_clock(now) if now is not None else current_time[0]
    )
    waiting = Event()
    original_connect = storage._connect

    def observed_connect():
        conn = original_connect()
        conn.set_trace_callback(lambda sql: waiting.set() if sql == "COMMIT" else None)
        return conn

    monkeypatch.setattr(storage, "_connect", observed_connect)
    reader = original_connect()
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM watch_notification_settings").fetchall()
    posted_at = []

    async def post(payload):
        posted_at.append(current_time[0])
        return 200, {"ok": True, "result": {"message_id": 1}}

    def send():
        return asyncio.run(
            NotificationSender(store, post=post).send(
                prepared["delivery_id"], now=before if diagnostic else None
            )
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(send)
            assert waiting.wait(5)
            assert not future.done()
            current_time[0] = after
            reader.rollback()
            result = future.result(timeout=5)
    finally:
        reader.rollback()
        reader.close()
    if diagnostic:
        assert posted_at == [after]
        assert result == "sent"
    else:
        assert posted_at == []
        assert result == "unknown"
        row = store.show(prepared["delivery_id"])
        assert row["error_code"] == "pre_post_window_missed"
        assert len(row["attempts"]) == 1
        assert row["attempts"][0]["error_code"] == "pre_post_window_missed"
        conn = original_connect()
        try:
            claim = conn.execute(
                "SELECT state,attempts,delivery_id FROM watch_notification_urls"
            ).fetchone()
            assert tuple(claim) == ("unknown", 1, prepared["delivery_id"])
        finally:
            conn.close()
        from msalt.watch.dispatcher import Dispatcher

        tomorrow = after + timedelta(days=1)
        assert asyncio.run(Dispatcher(store, post=post).run("123456", now=tomorrow))["state"] in (
            "empty",
            "quiet",
        )
        assert (
            asyncio.run(
                NotificationSender(store, post=post).send(prepared["delivery_id"], now=tomorrow)
            )
            == "unknown"
        )
        assert posted_at == []
        assert len(store.show(prepared["delivery_id"])["attempts"]) == 1
        assert store.show(prepared["delivery_id"])["error_code"] == "pre_post_window_missed"


def test_missed_post_windows_consume_day_capacity_without_retry(tmp_path, monkeypatch):
    from msalt.watch.dispatcher import Dispatcher

    storage = Storage(str(tmp_path / "capacity.db"))
    storage.initialize()
    watches = WatchStore(storage)
    item = watches.add("fixture", description="fixture", keywords=[], excluded_keywords=[])
    watches.resume(item.id, expected_revision=1)
    for i in range(19):
        storage.insert_article("fixture", "GPU change", f"https://fixture/{i}", "GPU", "fixture")
    evaluator = Evaluator(
        EvaluationStore(storage),
        lambda s: dict(relevant=True, importance="high", reason="change", evidence="GPU"),
    )
    evaluator.run()
    evaluator.run()
    store = NotificationStore(storage)
    store.set_enabled(True, confirm=True)
    module = __import__("msalt.watch.notification_store", fromlist=["clock"])
    current = [datetime(2026, 10, 10, 0, 59, 59, tzinfo=timezone.utc)]
    actual_clock = module.clock
    monkeypatch.setattr(
        module, "clock", lambda now=None: actual_clock(now) if now is not None else current[0]
    )
    original_start = store.start_sending

    def commit_then_advance(identifier, *, now=None):
        token = original_start(identifier, now=now)
        if token:
            current[0] += timedelta(seconds=2)
        return token

    monkeypatch.setattr(store, "start_sending", commit_then_advance)
    posts = []

    async def post(payload):
        posts.append(payload)
        return 200, {"ok": True, "result": {"message_id": 1}}

    for hour in range(6):
        current[0] = datetime(2026, 10, 10, hour, 59, 59, tzinfo=timezone.utc)
        result = asyncio.run(Dispatcher(store, post=post).run("123456"))
        assert result["state"] == "unknown"
        assert store.show(result["delivery_id"])["error_code"] == "pre_post_window_missed"
    current[0] = datetime(2026, 10, 10, 6, 5, tzinfo=timezone.utc)
    assert asyncio.run(Dispatcher(store, post=post).run("123456"))["state"] == "limited"
    assert posts == []
    assert len(store.status()["deliveries"]) == 6
    conn = storage._connect()
    try:
        claims = conn.execute("SELECT state,attempts FROM watch_notification_urls").fetchall()
        assert len(claims) == 18
        assert all(tuple(row) == ("unknown", 1) for row in claims)
        assert conn.execute("SELECT COUNT(*) FROM watch_notification_attempts").fetchone()[0] == 6
    finally:
        conn.close()
