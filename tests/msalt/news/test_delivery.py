"""Durable delivery contracts, using real temporary SQLite only."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from msalt.news.briefing import BriefingGenerator
from msalt.storage import Storage


@pytest.fixture(autouse=True)
async def no_network(monkeypatch):
    import socket

    def blocked(*args, **kwargs):
        raise AssertionError("external network forbidden")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture
def storage(tmp_path):
    s = Storage(str(tmp_path / "ledger.db"))
    s.initialize()
    return s


@pytest.mark.parametrize("legacy_argument", [False, True])
def test_preview_never_marks_even_legacy_keyword(storage, legacy_argument):
    storage.insert_article(
        "test", "title", "https://example.test/one", "summary", "domestic", "2099-01-01 10:00:00"
    )
    text = BriefingGenerator(storage, use_llm=False).format_briefing(
        "morning", mark_as_briefed=legacy_argument
    )
    assert "https://example.test/one" in text
    assert storage.get_briefed_article_urls(["https://example.test/one"]) == set()


def ledger(storage):
    from msalt.news.delivery import DeliveryLedger

    return DeliveryLedger(storage.db_path, clock=lambda: 1000.0)


def prepare(storage, slot="morning", urls=("https://example.test/one",), text="briefing"):
    ledger_instance = ledger(storage)
    row, owned = ledger_instance.begin("123", "", "2026-10-09", slot)
    assert owned
    assert ledger_instance.reserve(row["delivery_id"], row["owner"], list(urls)) == list(urls)
    from msalt.news.briefing import GeneratedBriefing

    text = text + ("\n" + "\n".join(urls) if urls else "")
    ledger_instance.prepare(row["delivery_id"], row["owner"], GeneratedBriefing(text, tuple(urls)))
    return ledger_instance, row


def test_migration_is_additive_and_idempotent(storage):
    storage.insert_article("source", "title", "https://legacy.test", "old", "domestic")
    storage.mark_articles_briefed(["https://legacy.test"], "legacy")
    item = storage.insert_tracked_item("sleep", "duration", "hours", "07:00")
    storage.upsert_record(item, "2026-10-08", value_num=7.5, raw_input="7.5")

    def snapshot():
        with sqlite3.connect(storage.db_path) as c:
            return {
                t: c.execute("SELECT * FROM " + t).fetchall()
                for t in ["news_articles", "news_briefed_articles", "tracked_items", "records"]
            }

    before = snapshot()
    storage.initialize()
    storage.initialize()
    assert snapshot() == before
    with sqlite3.connect(storage.db_path) as c:
        assert c.execute("SELECT COUNT(*) FROM news_deliveries").fetchone()[0] == 0


def test_one_delivery_per_slot_and_active_article_reservation(storage):
    ledger_instance, first = prepare(storage)
    duplicate, owned = ledger_instance.begin("123", "", "2026-10-09", "morning")
    assert not owned and duplicate["delivery_id"] == first["delivery_id"]
    second, owned = ledger_instance.begin("123", "", "2026-10-09", "afternoon")
    assert owned
    assert ledger_instance.reserve(
        second["delivery_id"],
        second["owner"],
        ["https://example.test/one", "https://example.test/two"],
    ) == ["https://example.test/two"]


def test_concurrent_claim_has_one_winner(storage):
    ledger_instance, row = prepare(storage)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: ledger(storage).claim_send(row["delivery_id"]), range(2)))
    assert sum(result is not None for result in results) == 1


def test_expired_send_becomes_unknown_and_keeps_reservation(storage):
    ledger_instance, row = prepare(storage)
    owner = ledger_instance.claim_send(row["delivery_id"])
    ledger_instance.claim_part(row["delivery_id"], owner, 1)
    from msalt.news.delivery import DeliveryLedger

    recovered = DeliveryLedger(storage.db_path, clock=lambda: 2000.0)
    recovered.recover()
    assert recovered.show(row["delivery_id"])["state"] == "unknown"
    assert recovered.claim_send(row["delivery_id"]) is None
    assert recovered.reserved_urls() == {"https://example.test/one"}


def test_generation_lease_fences_stale_worker(storage):
    ledger_instance = ledger(storage)
    row, _ = ledger_instance.begin("123", "", "2026-10-09", "morning")
    from msalt.news.delivery import DeliveryLedger

    newer = DeliveryLedger(storage.db_path, clock=lambda: 2000.0)
    newer.recover()
    assert newer.show(row["delivery_id"])["state"] == "failed"
    with pytest.raises(ValueError):
        ledger_instance.prepare(row["delivery_id"], row["owner"], "stale")


def test_generation_quota_is_persistent_atomic(storage):
    ledger_instance = ledger(storage)
    for day in range(1, 25):
        ledger_instance.begin("123", "", f"2026-10-{day:02}", "morning")
    with pytest.raises(ValueError, match="quota"):
        ledger(storage).begin("123", "", "2026-10-25", "morning")


def test_readonly_missing_database_does_not_create(tmp_path):
    from msalt.news.delivery import DeliveryLedger

    path = tmp_path / "missing.db"
    assert DeliveryLedger(str(path)).list() == []
    assert not path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,expected",
    [
        ({"ok": True, "result": {"message_id": 123}}, "sent"),
        ({"ok": True, "result": {}}, "unknown"),
        ({"ok": False, "error_code": 401}, "failed"),
        ({"ok": False, "error_code": 500}, "unknown"),
    ],
)
async def test_sender_ack_requires_valid_api_message_id(storage, response, expected):
    from msalt.news.sender import DeliverySender

    ledger_instance, row = prepare(storage)
    requests = []

    async def post(payload):
        requests.append(payload)
        return 200, response

    state = await DeliverySender(ledger_instance, post=post).send(row["delivery_id"])
    assert state == expected
    assert len(requests) == 1
    assert storage.get_briefed_article_urls(["https://example.test/one"]) == (
        {"https://example.test/one"} if expected == "sent" else set()
    )


@pytest.mark.asyncio
async def test_known_preconnect_failure_retries_three_then_saved_manual_retry(storage):
    from msalt.news.sender import DeliverySender, ProvenNoSendError

    ledger_instance, row = prepare(storage)
    calls = []
    sleeps = []

    async def post(payload):
        calls.append(payload.copy())
        if len(calls) <= 3:
            raise ProvenNoSendError()
        return 200, {"ok": True, "result": {"message_id": 7}}

    async def sleep(delay):
        sleeps.append(delay)

    assert (
        await DeliverySender(ledger_instance, post=post, sleep=sleep).send(row["delivery_id"])
        == "failed"
    )
    assert len(calls) == 3 and sleeps == [1, 2]
    assert (
        await DeliverySender(ledger(storage), post=post, sleep=sleep).send(row["delivery_id"])
        == "failed"
    )
    assert len(calls) == 3
    assert (
        await DeliverySender(ledger(storage), post=post, sleep=sleep).send(
            row["delivery_id"], manual=True
        )
        == "sent"
    )
    assert len(calls) == 4 and all(p["text"] == "briefing\nhttps://example.test/one" for p in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["timeout", "cancel", "parse", "http5xx", "429long"])
async def test_ambiguous_or_out_of_deadline_failure_never_auto_resends(storage, kind):
    import asyncio

    import httpx

    from msalt.news.sender import DeliverySender

    ledger_instance, row = prepare(storage)
    calls = []

    async def post(payload):
        calls.append(payload)
        if kind == "timeout":
            raise httpx.ReadTimeout("private/token")
        if kind == "cancel":
            raise asyncio.CancelledError()
        if kind == "parse":
            raise ValueError("private payload")
        if kind == "http5xx":
            return 503, {"ok": False, "error_code": 503}
        return 429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 500}}

    if kind == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await DeliverySender(ledger_instance, post=post).send(row["delivery_id"])
    else:
        await DeliverySender(ledger_instance, post=post).send(row["delivery_id"])
    assert ledger_instance.show(row["delivery_id"])["state"] == (
        "failed" if kind == "429long" else "unknown"
    )
    await DeliverySender(ledger(storage), post=post).send(row["delivery_id"])
    assert len(calls) == 1
    assert "private" not in str(ledger_instance.show(row["delivery_id"]))


@pytest.mark.asyncio
async def test_partial_ack_stops_even_known_rejection_and_manual_skips_success(storage):
    from msalt.news.sender import DeliverySender

    text = ("a" * 1700 + "\n") * 3
    ledger_instance, row = prepare(storage, text=text)
    calls = []

    async def post(payload):
        calls.append(payload["text"])
        if len(calls) == 2:
            return 429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 1}}
        return 200, {"ok": True, "result": {"message_id": len(calls)}}

    assert await DeliverySender(ledger_instance, post=post).send(row["delivery_id"]) == "unknown"
    assert len(calls) == 2
    with pytest.raises(ValueError, match="confirm-uncertain"):
        await DeliverySender(ledger_instance, post=post).send(row["delivery_id"], manual=True)
    assert (
        await DeliverySender(ledger_instance, post=post).send(
            row["delivery_id"], manual=True, confirm_uncertain=True
        )
        == "sent"
    )
    assert len(calls) == 3 and calls[2] == calls[1] and calls[0] != calls[2]


@pytest.mark.asyncio
async def test_final_commit_failure_retains_ack_and_unknown_without_mark(storage, monkeypatch):
    from msalt.news.sender import DeliverySender

    ledger_instance, row = prepare(storage)

    async def post(payload):
        return 200, {"ok": True, "result": {"message_id": 33}}

    def fail(*args):
        raise sqlite3.OperationalError("synthetic")

    monkeypatch.setattr(ledger_instance, "finish", fail)
    assert await DeliverySender(ledger_instance, post=post).send(row["delivery_id"]) == "unknown"
    assert ledger_instance.show(row["delivery_id"])["parts"][0]["message_id"] == 33
    assert not storage.get_briefed_article_urls(["https://example.test/one"])


def test_split_preserves_unicode_links_and_rejects_overflow():
    from msalt.news.delivery import split_payload

    text = "한😀 https://example.test/full\n" * 180
    parts = split_payload(text)
    assert all(len(p) <= 3500 for p in parts)
    assert "".join(p.split("\n", 1)[1] for p in parts) == text
    with pytest.raises(ValueError):
        split_payload(("z" * 3400 + "\n") * 5)


def test_received_resolution_is_human_evidence_not_api_ack(storage):
    ledger_instance, row = prepare(storage)
    ledger_instance.resolve(row["delivery_id"], received=True)
    detail = ledger_instance.show(row["delivery_id"])
    assert detail["state"] == "received"
    assert detail["parts"][0]["message_id"] is None
    assert detail["attempt_log"][-1]["outcome"] == "human_received" or any(
        a["outcome"] == "human_received" for a in detail["attempt_log"]
    )
    assert ledger_instance.reserved_urls() == {"https://example.test/one"}


def test_regeneration_reuses_own_reservations(storage):
    ledger_instance = ledger(storage)
    row, _ = ledger_instance.begin("123", "", "2026-10-09", "morning")
    ident = row["delivery_id"]
    assert ledger_instance.reserve(ident, row["owner"], ["https://example.test/a"])
    ledger_instance.fail_generation(ident, row["owner"])
    newer = ledger_instance.regenerate(ident)
    assert ledger_instance.reserve(ident, newer["owner"], ["https://example.test/a"]) == [
        "https://example.test/a"
    ]
    before = ledger_instance.show(ident)
    with pytest.raises(ValueError):
        ledger_instance.fail_generation(ident, row["owner"])
    assert ledger_instance.show(ident) == before


@pytest.mark.parametrize("operation", ["ack", "reject"])
def test_attempt_identity_is_atomic(storage, operation):
    ledger_instance, row = prepare(storage)
    ident = row["delivery_id"]
    owner = ledger_instance.claim_send(ident)
    ledger_instance.claim_part(ident, owner, 1)
    before = ledger_instance.show(ident)
    with pytest.raises(ValueError):
        if operation == "ack":
            ledger_instance.ack(ident, owner, 1, "wrong-attempt", 7)
        else:
            ledger_instance.reject(ident, owner, 1, "wrong-attempt", "api_rejected")
    assert ledger_instance.show(ident) == before


@pytest.mark.asyncio
async def test_corrupt_snapshot_sends_nothing(storage):
    from msalt.news.sender import DeliverySender

    ledger_instance, row = prepare(storage)
    with sqlite3.connect(storage.db_path) as c:
        c.execute("UPDATE news_delivery_parts SET text='corrupt'")
    calls = []

    async def post(payload):
        calls.append(payload)
        return 200, {"ok": True, "result": {"message_id": 7}}

    assert await DeliverySender(ledger_instance, post=post).send(row["delivery_id"]) == "failed"
    assert calls == []
    assert not storage.get_briefed_article_urls(["https://example.test/one"])


@pytest.mark.asyncio
async def test_empty_remains_empty_after_notice_ack(storage):
    from msalt.news.sender import DeliverySender

    ledger_instance, row = prepare(storage, urls=(), text="수집된 뉴스가 없습니다.")
    calls = []

    async def post(payload):
        calls.append(payload)
        return 200, {"ok": True, "result": {"message_id": 7}}

    sender = DeliverySender(ledger_instance, post=post)
    assert await sender.send(row["delivery_id"]) == "empty"
    assert ledger_instance.show(row["delivery_id"])["parts"][0]["message_id"] == 7
    assert await sender.send(row["delivery_id"]) == "empty"
    assert len(calls) == 1


def test_show_missing_or_legacy_db_is_readonly(tmp_path):
    from msalt.news.delivery import DeliveryLedger

    path = tmp_path / "한 글.db"
    with pytest.raises(ValueError, match="not found"):
        DeliveryLedger(path).show("absent")
    assert not path.exists()
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE legacy (id INTEGER)")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="not found"):
        DeliveryLedger(path).show("absent")
    assert path.read_bytes() == before


def test_nonfinite_retry_after_is_rejected():
    from msalt.news.sender import classify

    assert (
        classify(
            429, {"ok": False, "error_code": 429, "parameters": {"retry_after": float("inf")}}
        ).kind
        == "failed"
    )


def test_incompatible_existing_ledger_rolls_back_legacy_migration(tmp_path):
    from msalt.storage import Storage

    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE news_deliveries (delivery_id TEXT PRIMARY KEY)")
        c.execute("INSERT INTO news_deliveries VALUES ('preserved')")
    with pytest.raises(ValueError, match="schema"):
        Storage(str(path)).initialize()
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
            ("news_deliveries",)
        ]
        assert c.execute("SELECT * FROM news_deliveries").fetchall() == [("preserved",)]


@pytest.mark.asyncio
async def test_final_transaction_trigger_failure_then_manual_finalize_no_repost(storage):
    from msalt.news.sender import DeliverySender

    ledger_instance, row = prepare(
        storage, urls=("https://example.test/one", "https://example.test/two")
    )
    ident = row["delivery_id"]
    with sqlite3.connect(storage.db_path) as c:
        c.execute("""CREATE TRIGGER reject_second BEFORE INSERT ON news_briefed_articles
        WHEN NEW.article_url='https://example.test/two' BEGIN SELECT RAISE(ABORT,'fault'); END""")
    calls = []

    async def post(payload):
        calls.append(payload)
        return 200, {"ok": True, "result": {"message_id": 7}}

    sender = DeliverySender(ledger_instance, post=post)
    assert await sender.send(ident) == "unknown"
    assert not storage.get_briefed_article_urls(
        ["https://example.test/one", "https://example.test/two"]
    )
    receipt = ledger_instance.show(ident)["parts"][0]
    with sqlite3.connect(storage.db_path) as c:
        c.execute("DROP TRIGGER reject_second")
    assert await sender.send(ident, manual=True, confirm_uncertain=True) == "sent"
    assert len(calls) == 1
    assert ledger_instance.show(ident)["parts"][0] == receipt


@pytest.mark.asyncio
async def test_post_quota_exhaustion_is_known_no_send(storage):
    from msalt.news.sender import DeliverySender

    ledger_instance, row = prepare(storage)
    with sqlite3.connect(storage.db_path) as c:
        c.execute("INSERT INTO news_delivery_budget VALUES ('posts',300)")
    calls = []

    async def post(payload):
        calls.append(payload)

    assert await DeliverySender(ledger_instance, post=post).send(row["delivery_id"]) == "failed"
    assert calls == []


def test_long_plain_line_split_without_breaking_url():
    from msalt.news.delivery import split_payload

    text = "a" * 4000 + "\nhttps://example.test/full\n"
    parts = split_payload(text)
    assert len(parts) == 2
    assert all(len(part) <= 3500 for part in parts)
    assert "".join(part.split("\n", 1)[1] for part in parts) == text
    assert parts[-1].endswith("https://example.test/full\n")
