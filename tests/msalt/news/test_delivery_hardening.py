"""Fault, quota, transport and process-stop evidence; all data is temporary."""

import asyncio
import logging
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from msalt.news.briefing import GeneratedBriefing
from msalt.news.delivery import DeliveryLedger
from msalt.news.sender import BotAPI, DeliverySender, ProvenNoSendError, classify
from msalt.storage import Storage


@pytest.fixture(autouse=True)
async def offline(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture
def ledger(tmp_path):
    path = str(tmp_path / "ledger.db")
    Storage(path).initialize()
    return DeliveryLedger(path)


def prepared(ledger, text="one", urls=()):
    row, _ = ledger.begin("123", "7", "2026-10-09", "morning")
    ledger.reserve(row["delivery_id"], row["owner"], urls)
    ledger.prepare(row["delivery_id"], row["owner"], GeneratedBriefing(text, tuple(urls)))
    return row["delivery_id"]


@pytest.mark.parametrize(
    "name,limit",
    [("generations", 24), ("deliveries", 25), ("parts", 100), ("summaries", 72), ("posts", 300)],
)
def test_every_quota_atomic_race_and_restart(ledger, name, limit):
    from concurrent.futures import ThreadPoolExecutor

    with sqlite3.connect(ledger.db_path) as c:
        c.execute("INSERT INTO news_delivery_budget VALUES (?,?)", (name, limit - 1))

    def contender(_):
        other = DeliveryLedger(ledger.db_path)
        try:
            with other._tx() as c:
                other._budget(c, name)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(contender, range(2))) == [False, True]
    with sqlite3.connect(ledger.db_path) as c:
        assert (
            c.execute("SELECT used FROM news_delivery_budget WHERE name=?", (name,)).fetchone()[0]
            == limit
        )
    assert contender(0) is False


@pytest.mark.parametrize(
    "status,body,kind",
    [
        (200, {"ok": True, "result": {"message_id": True}}, "unknown"),
        (200, {"ok": True, "result": {"message_id": 0}}, "unknown"),
        (200, {"ok": True, "result": {"message_id": -1}}, "unknown"),
        (200, {"ok": True, "result": {"message_id": "7"}}, "unknown"),
        (200, {"ok": True, "result": []}, "unknown"),
        (200, [], "unknown"),
        (500, {"ok": True, "result": {"message_id": 7}}, "unknown"),
        (401, {"ok": False, "error_code": 401}, "failed"),
        (400, {"ok": False, "error_code": 400}, "failed"),
        (403, {"ok": False, "error_code": 403}, "failed"),
        (200, {"ok": False, "error_code": 400}, "failed"),
        (400, {"ok": False, "error_code": 429}, "unknown"),
        (429, {"ok": False, "error_code": 429}, "retry"),
        (
            429,
            {"ok": False, "error_code": 429, "parameters": {"retry_after": float("nan")}},
            "failed",
        ),
    ],
)
def test_response_classification(status, body, kind):
    assert classify(status, body).kind == kind


@pytest.mark.parametrize(
    "trace_names,error,known",
    [
        (["connection.connect_tcp.started"], httpx.ConnectTimeout, True),
        (
            ["connection.connect_tcp.started", "connection.start_tls.started"],
            httpx.ConnectError,
            True,
        ),
        ([], httpx.ConnectError, False),
        (
            ["connection.connect_tcp.started", "http11.send_request_headers.started"],
            httpx.ConnectError,
            False,
        ),
        ([], httpx.PoolTimeout, False),
        (["connection.connect_tcp.started"], httpx.WriteTimeout, False),
        (["connection.connect_tcp.started"], httpx.ReadTimeout, False),
    ],
)
async def test_real_bot_adapter_transport_evidence(monkeypatch, trace_names, error, known):
    options = []

    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            for name in trace_names:
                await request.extensions["trace"](name, {})
            raise error("synthetic")

    def transport(**kwargs):
        options.append(kwargs)
        return Transport()

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    with pytest.raises(ProvenNoSendError if known else error):
        await BotAPI("synthetic-token")({"chat_id": "123", "text": "hello", "message_thread_id": 7})
    assert options == [{"retries": 0}]


async def test_bot_token_never_logged_and_plain_thread_payload(monkeypatch, caplog):
    import json

    requests = []

    async def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kwargs: httpx.MockTransport(handle))
    with caplog.at_level(logging.DEBUG):
        assert await BotAPI("secret-credential")(
            {"chat_id": "123", "text": "plain", "message_thread_id": 7}
        ) == (200, {"ok": True, "result": {"message_id": 7}})
    assert "secret-credential" not in caplog.text
    assert requests == [{"chat_id": "123", "text": "plain", "message_thread_id": 7}]


@pytest.mark.parametrize(
    "phase", ["before_claim", "after_claim", "during_post", "after_api_ack", "after_some_acks"]
)
def test_abrupt_process_exit_never_automatically_reclaims_send(ledger, tmp_path, phase):
    urls = ("https://example.test/crash",)
    ident = prepared(ledger, text=("a" * 2000 + "\n") * 2 + urls[0], urls=urls)
    child = tmp_path / "crash.py"
    child.write_text(
        """import asyncio, os, socket, sys
from msalt.news.delivery import DeliveryLedger
from msalt.news.sender import DeliverySender
ledger=DeliveryLedger(sys.argv[1]); ident=sys.argv[2]; phase=sys.argv[3]
if phase=='before_claim': os._exit(73)
async def main():
    def blocked(*args, **kwargs): raise AssertionError('offline')
    socket.socket.connect=blocked
    socket.socket.connect_ex=blocked
    socket.getaddrinfo=blocked
    original_claim=ledger.claim_part
    original_ack=ledger.ack
    def claim(*args):
        attempt=original_claim(*args)
        if phase=='after_claim': os._exit(73)
        return attempt
    def ack(*args):
        if phase=='after_api_ack': os._exit(73)
        original_ack(*args)
    ledger.claim_part=claim
    ledger.ack=ack
    count=0
    async def post(payload):
        nonlocal count
        count+=1
        if phase=='during_post' or (phase=='after_some_acks' and count==2): os._exit(73)
        return 200, {'ok':True,'result':{'message_id':count}}
    await DeliverySender(ledger,post=post).send(ident)
asyncio.run(main())
""",
        encoding="utf-8",
    )
    run = subprocess.run(
        [sys.executable, str(child), ledger.db_path, ident, phase], capture_output=True, timeout=20
    )
    assert run.returncode == 73
    future = DeliveryLedger(ledger.db_path, clock=lambda: time.time() + 1000)
    future.recover()
    state = future.show(ident)["state"]
    assert state == ("prepared" if phase == "before_claim" else "unknown")
    assert future.reserved_urls() == set(urls)
    if phase != "before_claim":
        assert future.claim_send(ident) is None
    assert not Storage(ledger.db_path).get_briefed_article_urls(urls)


async def test_expired_generation_never_collects(ledger):
    from msalt.news.coordinator import generate_snapshot

    row, _ = ledger.begin("123", "", "2026-10-09", "morning")
    with sqlite3.connect(ledger.db_path) as c:
        c.execute("UPDATE news_deliveries SET generation_started=0")

    class Collector:
        def collect(self):
            pytest.fail("stale worker started external collection")

    with pytest.raises(ValueError):
        generate_snapshot(
            db_path=ledger.db_path,
            ident=row["delivery_id"],
            owner=row["owner"],
            slot="morning",
            collector=Collector(),
        )


def test_all_migration_statements_rollback_existing_data(tmp_path, monkeypatch):
    import msalt.news.delivery_schema as schema

    statements = [s for s in schema.SCHEMA.split(";") if s.strip()]
    for index in range(len(statements)):
        path = tmp_path / f"fault-{index}.db"
        with sqlite3.connect(path) as c:
            c.execute(
                "CREATE TABLE records (id INTEGER PRIMARY KEY, item_id INTEGER, recorded_for TEXT, value_num REAL)"
            )
            c.execute("INSERT INTO records VALUES (1,1,'2026-10-08',7.5)")
        original = sqlite3.connect

        class Connection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql.strip() == statements[index].strip():
                    raise sqlite3.OperationalError("migration fault")
                return super().execute(sql, parameters)

        monkeypatch.setattr(
            sqlite3,
            "connect",
            lambda *args, **kwargs: original(*args, **kwargs, factory=Connection),
        )
        with pytest.raises(sqlite3.OperationalError):
            Storage(str(path)).initialize()
        monkeypatch.setattr(sqlite3, "connect", original)
        with sqlite3.connect(path) as c:
            assert c.execute("SELECT * FROM records").fetchall() == [(1, 1, "2026-10-08", 7.5)]
            assert c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
                ("records",)
            ]


@pytest.mark.parametrize("damage", ["missing_index", "nonunique_index", "missing_slot_unique"])
def test_schema_refuses_missing_or_weakened_uniqueness(ledger, damage):
    with sqlite3.connect(ledger.db_path) as c:
        if damage == "missing_slot_unique":
            sql = c.execute(
                "SELECT sql FROM sqlite_master WHERE name='news_deliveries'"
            ).fetchone()[0]
            c.execute("DROP TABLE news_deliveries")
            c.execute(sql.replace(",\n UNIQUE(target, thread, kst_date, slot)", ""))
        else:
            c.execute("DROP INDEX news_delivery_active_url")
            if damage == "nonunique_index":
                c.execute(
                    "CREATE INDEX news_delivery_active_url ON news_delivery_articles(article_url) WHERE active=1"
                )
    before = Path(ledger.db_path).read_bytes()
    with pytest.raises(ValueError, match="schema"):
        Storage(ledger.db_path).initialize()
    assert Path(ledger.db_path).read_bytes() == before


async def test_deadline_expiring_inside_durable_claim_never_posts(ledger, monkeypatch):
    ident = prepared(ledger)
    clock = [0]
    original = ledger.claim_part

    def claim(*args):
        result = original(*args)
        clock[0] = 301
        return result

    monkeypatch.setattr(ledger, "claim_part", claim)
    calls = []

    async def post(payload):
        calls.append(payload)
        return 200, {"ok": True, "result": {"message_id": 7}}

    assert (
        await DeliverySender(ledger, post=post, monotonic=lambda: clock[0]).send(
            ident, deadline=300
        )
        == "failed"
    )
    assert calls == []


async def test_late_actual_ack_is_retained_but_does_not_finalize(ledger):
    ident = prepared(ledger)
    clock = [0]

    async def post(payload):
        clock[0] = 301
        return 200, {"ok": True, "result": {"message_id": 7}}

    assert (
        await DeliverySender(ledger, post=post, monotonic=lambda: clock[0]).send(
            ident, deadline=300
        )
        == "unknown"
    )
    assert ledger.show(ident)["parts"][0]["message_id"] == 7


async def test_bounded_generation_terminates_child_on_deadline(monkeypatch):
    import multiprocessing

    from msalt.news.coordinator import bounded_generation

    context = multiprocessing.get_context("spawn")
    children = []

    class Context:
        def Process(self, **kwargs):  # noqa: N802 - multiprocessing public interface
            process = context.Process(target=time.sleep, args=(60,))
            children.append(process)
            return process

    monkeypatch.setattr(multiprocessing, "get_context", lambda method: Context())
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await bounded_generation(deadline=started + 0.15)
    assert time.monotonic() - started < 5
    assert children[0] not in multiprocessing.active_children()
    with pytest.raises(ValueError, match="closed"):
        children[0].is_alive()


async def test_bounded_generation_terminates_child_on_cancel(monkeypatch):
    import multiprocessing

    from msalt.news.coordinator import bounded_generation

    context = multiprocessing.get_context("spawn")
    children = []

    class Context:
        def Process(self, **kwargs):  # noqa: N802 - multiprocessing public interface
            process = context.Process(target=time.sleep, args=(60,))
            children.append(process)
            return process

    monkeypatch.setattr(multiprocessing, "get_context", lambda method: Context())
    task = asyncio.create_task(bounded_generation(deadline=time.monotonic() + 300))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[0] not in multiprocessing.active_children()


def test_temporary_backup_and_code_rollback_preserve_new_tracking_record(ledger, tmp_path):
    storage = Storage(ledger.db_path)
    item = storage.insert_tracked_item("preserved", "number", "count", "08:00")
    storage.upsert_record(item, "2026-10-08", value_num=1, raw_input="one")
    backup = tmp_path / "backup.db"
    with sqlite3.connect(ledger.db_path) as c, sqlite3.connect(backup) as b:
        c.backup(b)
    storage.upsert_record(item, "2026-10-09", value_num=2, raw_input="two")
    prepared(ledger)
    # Old-code SELECT projection ignores additive tables, without replacing DB.
    with sqlite3.connect(ledger.db_path) as c:
        assert c.execute("SELECT value_num FROM records ORDER BY recorded_for").fetchall() == [
            (1.0,),
            (2.0,),
        ]
    restored = tmp_path / "restore-test.db"
    with sqlite3.connect(backup) as b, sqlite3.connect(restored) as r:
        b.backup(r)
    with sqlite3.connect(restored) as c:
        assert c.execute("SELECT value_num FROM records").fetchall() == [(1.0,)]
    assert Storage(ledger.db_path).get_records_for_item(item, 1, "2026-10-09")[0]["value_num"] == 2


async def test_snapshot_article_manifest_tampering_blocks_send(ledger):
    ident = prepared(ledger, text="https://example.test/a", urls=("https://example.test/a",))
    with sqlite3.connect(ledger.db_path) as c:
        c.execute("UPDATE news_deliveries SET snapshot_urls='[]'")
    calls = []

    async def post(payload):
        calls.append(payload)
        return 200, {"ok": True, "result": {"message_id": 7}}

    assert await DeliverySender(ledger, post=post).send(ident) == "failed"
    assert calls == []


def test_manual_retry_window_cap_survives_restart(ledger):
    ident = prepared(ledger)
    owner = ledger.claim_send(ident, manual=True)
    ledger.finish_failure(ident, owner, "operator_attempt_finished")
    restarted = DeliveryLedger(ledger.db_path)
    with pytest.raises(ValueError, match="quota"):
        restarted.claim_send(ident, manual=True)
    assert restarted.show(ident)["state"] == "failed"


async def test_corruption_after_post_cannot_finalize_changed_manifest(ledger):
    ident = prepared(ledger, text="https://example.test/a", urls=("https://example.test/a",))

    async def post(payload):
        with sqlite3.connect(ledger.db_path) as c:
            c.execute("UPDATE news_deliveries SET snapshot_urls='[]'")
        return 200, {"ok": True, "result": {"message_id": 7}}

    assert await DeliverySender(ledger, post=post).send(ident) == "unknown"
    assert ledger.show(ident)["parts"][0]["message_id"] == 7
    assert not Storage(ledger.db_path).get_briefed_article_urls(["https://example.test/a"])
