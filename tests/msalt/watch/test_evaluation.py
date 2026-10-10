import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from msalt.storage import Storage
from msalt.watch.store import WatchStore


@pytest.fixture
def setup(tmp_path):
    storage = Storage(str(tmp_path / "evaluation.db"))
    storage.initialize()
    watches = WatchStore(storage)
    item = watches.add(
        "AI",
        description="GPU supply changes",
        keywords=["ＡＩ", "GPU"],
        excluded_keywords=["rumor"],
    )
    item = watches.resume(item.id, expected_revision=1)
    return storage, watches, item


def article(storage, number=1, title="GPU supply doubles", summary="AI factory opens"):
    storage.insert_article(
        "fixture", title, f"https://fixture/{number}", summary, "fixture", published_at="2000-01-01"
    )


def api(storage):
    store = importlib.import_module("msalt.watch.evaluation_store").EvaluationStore(storage)
    runner = importlib.import_module("msalt.watch.evaluation").Evaluator
    return store, runner


def good(snapshot):
    return dict(
        relevant=True,
        importance="high",
        reason="Concrete supply increase",
        evidence="supply doubles",
    )


def test_additive_evaluation_schema_exists(setup):
    storage, _, _ = setup
    with storage._connect() as conn:
        names = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"watch_evaluations", "watch_scan_cursors", "watch_evaluation_runs"} <= names


def test_watermark_dedup_multiple_conditions_and_old_publication(setup):
    storage, watches, item = setup
    article(storage, 1)
    second = watches.add("other", description="AI factories", keywords=[], excluded_keywords=[])
    second = watches.resume(second.id, expected_revision=1)
    article(storage, 2)
    assert not storage.insert_article("fixture", "duplicate", "https://fixture/2", "", "fixture")
    store, runner = api(storage)
    result = runner(store, good).run()
    rows = store.list()
    assert result["calls_reserved"] == 3
    assert [(r["watch_id"], r["article_id"]) for r in rows] == [
        (item.id, 1),
        (item.id, 2),
        (second.id, 2),
    ]
    assert all(r["article"]["published_at"] == "2000-01-01" for r in rows)
    assert runner(store, good).run()["calls_reserved"] == 0
    assert len(store.list()) == 3
    watches.pause(item.id, expected_revision=item.revision)
    watches.delete(second.id, expected_revision=second.revision)
    article(storage, 3)
    assert runner(store, good).run()["articles_processed"] == 0
    assert store.notification_candidates() == []


@pytest.mark.parametrize(
    "title,status,calls,rule",
    [
        ("ＧＰＵ supply doubles", "relevant", 1, None),
        ("GPU rumor supply doubles", "irrelevant", 0, "excluded_keyword"),
        ("Sports final", "irrelevant", 0, "keyword_mismatch"),
    ],
)
def test_literal_filter_normalizes_and_records_rule(setup, title, status, calls, rule):
    storage, _, _ = setup
    article(storage, title=title, summary="")
    store, runner = api(storage)
    result = runner(store, good).run()
    row = store.list()[0]
    assert (row["status"], result["calls_reserved"]) == (status, calls)
    assert row["filter_rule"] == rule
    assert row["attempts"] == calls
    assert len(row["input_hash"]) == 64
    if rule:
        assert row["reason"] and row["evidence"]


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        "{broken",
        {"relevant": 1, "importance": "high", "reason": "yes", "evidence": "GPU"},
        {"relevant": True, "importance": "critical", "reason": "yes", "evidence": "GPU"},
        {"relevant": True, "importance": "high", "reason": "", "evidence": "GPU"},
        {"relevant": True, "importance": "high", "reason": "x" * 501, "evidence": "GPU"},
        {"relevant": True, "importance": "high", "reason": "yes", "evidence": "invented"},
        {"relevant": True, "importance": "high", "reason": "yes", "evidence": "GPU\nAI"},
        {"relevant": False, "importance": "low", "reason": "no", "evidence": ""},
    ],
)
def test_invalid_outputs_are_error_not_irrelevant(setup, response):
    storage, _, _ = setup
    article(storage)
    store, runner = api(storage)
    runner(store, lambda snapshot: response).run()
    row = store.list()[0]
    assert row["status"] == "error"
    assert row["relevant"] is None
    assert row["error_code"] == "invalid_response"
    assert runner(store, good).run()["calls_reserved"] == 0


def test_irrelevant_and_timeout_explicit_retry_snapshot_and_three_reservations(setup):
    storage, _, _ = setup
    article(storage)
    store, runner = api(storage)
    seen = []

    def failing(snapshot):
        seen.append(snapshot)
        raise TimeoutError("private error")

    for retry in (False, True, True, True):
        runner(store, failing).run(retry_errors=retry)
    row = store.list()[0]
    assert row["attempts"] == 3 and row["error_code"] == "timeout"
    assert len(seen) == 3
    assert "private" not in json.dumps(row)
    # A saved snapshot survives mutable article source updates.
    with storage._connect() as conn:
        conn.execute("UPDATE news_articles SET title='changed'")
    assert all(s["article"]["title"] == "GPU supply doubles" for s in seen)
    article(storage, 2)
    runner(
        store, lambda s: dict(relevant=False, importance="low", reason="Unrelated", evidence="AI")
    ).run()
    assert store.list()[-1]["status"] == "irrelevant"


def test_run_caps_global_and_zero_calls_still_filters(setup):
    storage, watches, _ = setup
    second = watches.add("all", description="any", keywords=[], excluded_keywords=[])
    watches.resume(second.id, expected_revision=1)
    for i in range(1, 131):
        article(storage, i)
    store, runner = api(storage)
    result = runner(store, good).run(max_articles=100, max_calls=10)
    assert result["articles_processed"] <= 100
    assert result["calls_reserved"] == 10
    assert len(store.list(limit=1000)) <= 100
    for kwargs in (
        {"max_articles": 101},
        {"max_calls": 11},
        {"max_articles": 0},
        {"max_calls": -1},
        {"max_calls": True},
    ):
        with pytest.raises(ValueError):
            runner(store, good).run(**kwargs)


def test_cursor_batch_is_atomic_on_insert_failure(setup):
    storage, _, _ = setup
    article(storage, 1)
    article(storage, 2)
    store, _ = api(storage)
    with storage._connect() as conn:
        conn.execute(
            "CREATE TRIGGER reject_second BEFORE INSERT ON watch_evaluations WHEN NEW.article_id=2 BEGIN SELECT RAISE(ABORT,'fixture'); END"
        )
    with pytest.raises(Exception):
        store.enqueue(100)
    with storage._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM watch_evaluations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM watch_scan_cursors").fetchone()[0] == 0
        conn.execute("DROP TRIGGER reject_second")
    assert store.enqueue(100) == 2
    assert store.enqueue(100) == 0


def test_two_real_workers_claim_one_candidate(setup):
    storage, _, _ = setup
    article(storage)
    store, _ = api(storage)
    store.enqueue(100)
    barrier = Barrier(2)

    def worker(_):
        local, _ = api(Storage(storage.db_path))
        run_id = local.begin_run(100, 10)
        barrier.wait()
        return local.claim(run_id)

    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(worker, range(2)))
    assert sum(c is not None for c in claims) == 1
    assert store.list()[0]["attempts"] == 1
    winner = next(c for c in claims if c)
    assert not store.complete(winner["id"], "wrong-owner", good(winner["snapshot"]))
    assert store.complete(winner["id"], winner["owner_token"], good(winner["snapshot"]))
    assert store.list()[0]["status"] == "relevant"


def test_crash_reservation_lease_expiry_requires_explicit_retry(setup):
    storage, _, _ = setup
    article(storage)
    store, _ = api(storage)
    store.enqueue(100)
    run = store.begin_run(100, 1)
    claim = store.claim(run)
    assert store.run_summary(run)["calls_reserved"] == 1
    assert store.claim(run) is None
    with storage._connect() as conn:
        conn.execute("UPDATE watch_evaluations SET lease_until=0")
    no_retry = store.begin_run(100, 10)
    assert store.claim(no_retry) is None
    assert store.list()[0]["status"] == "error"
    assert store.list()[0]["error_code"] == "lease_expired"
    assert not store.complete(claim["id"], claim["owner_token"], good(claim["snapshot"]))
    retry = store.begin_run(100, 10, retry_errors=True)
    again = store.claim(retry)
    assert again["attempts"] == 2 and again["input_hash"] == claim["input_hash"]


@pytest.mark.parametrize("action", ["pause", "update", "delete"])
def test_condition_changes_during_call_preserve_stale_result(setup, action):
    storage, watches, item = setup
    article(storage)
    store, runner = api(storage)

    def changed(snapshot):
        kwargs = {"description": "new"} if action == "update" else {}
        getattr(watches, action)(item.id, expected_revision=item.revision, **kwargs)
        return good(snapshot)

    runner(store, changed).run()
    assert store.list()[0]["status"] == "relevant"
    assert store.list()[0]["stale"] is True
    assert store.notification_candidates() == []


def test_pause_after_claim_prevents_start_and_no_external_transaction(setup):
    storage, watches, item = setup
    article(storage)
    store, runner = api(storage)
    store.enqueue(100)
    run = store.begin_run(100, 10)
    claim = store.claim(run)
    watches.pause(item.id, expected_revision=item.revision)
    assert not store.authorize_call(claim["id"], claim["owner_token"])
    assert store.list()[0]["attempts"] == 1
    # An adapter can take a write lock, proving claim is committed before HTTP.
    item = watches.resume(item.id, expected_revision=item.revision + 1)
    article(storage, 2)

    def writer(snapshot):
        with storage._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE news_articles SET category='checked'")
        return good(snapshot)

    runner(store, writer).run()
    assert store.notification_candidates()[0]["article_id"] == 2


def test_retry_uses_original_snapshot_after_source_mutation(setup):
    storage, _, _ = setup
    article(storage)
    store, runner = api(storage)
    runner(store, lambda s: None).run()
    original = store.list()[0]
    with storage._connect() as conn:
        conn.execute("UPDATE news_articles SET title='new unrelated title',summary='updated'")
    seen = []

    def retry(snapshot):
        seen.append(snapshot)
        return good(snapshot)

    runner(store, retry).run(retry_errors=True)
    row = store.list()[0]
    assert seen[0]["article"]["title"] == "GPU supply doubles"
    assert row["status"] == "relevant" and row["attempts"] == 2
    assert row["input_hash"] == original["input_hash"]


def test_two_workers_share_one_run_call_cap_and_crash_never_refunds(setup):
    storage, _, _ = setup
    for i in range(1, 21):
        article(storage, i)
    store, _ = api(storage)
    store.enqueue(100)
    run = store.begin_run(100, 10)
    barrier = Barrier(2)

    def worker(_):
        local, _ = api(Storage(storage.db_path))
        barrier.wait()
        claims = []
        while (claim := local.claim(run)) is not None:
            claims.append(claim)
        return claims

    with ThreadPoolExecutor(2) as pool:
        groups = list(pool.map(worker, range(2)))
    assert sum(len(group) for group in groups) == 10
    assert store.run_summary(run)["calls_reserved"] == 10
    with storage._connect() as conn:
        conn.execute("UPDATE watch_evaluations SET lease_until=0")
    assert store.claim(run) is None
    assert store.run_summary(run)["calls_reserved"] == 10
    assert len(store.list(status="error")) == 10


def test_subprocess_crash_persists_reservation_and_expiry(setup):
    import os
    import subprocess
    import sys

    storage, _, _ = setup
    article(storage)
    store, _ = api(storage)
    store.enqueue(100)
    code = """import os,sys
from msalt.storage import Storage
from msalt.watch.evaluation_store import EvaluationStore
store=EvaluationStore(Storage(sys.argv[1]))
run=store.begin_run(100,1)
assert store.claim(run) is not None
os._exit(73)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, storage.db_path],
        env=os.environ.copy(),
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 73, result.stderr
    assert store.list()[0]["attempts"] == 1
    with storage._connect() as conn:
        assert conn.execute("SELECT calls_reserved FROM watch_evaluation_runs").fetchone()[0] == 1
        conn.execute("UPDATE watch_evaluations SET lease_until=0")
    assert store.claim(store.begin_run(100, 10)) is None
    assert store.list()[0]["error_code"] == "lease_expired"


def test_revision_update_and_resume_only_scan_after_new_watermark(setup):
    storage, watches, item = setup
    article(storage, 1)
    store, runner = api(storage)
    runner(store, good).run()
    article(storage, 2)
    item = watches.update(item.id, expected_revision=item.revision, description="updated condition")
    article(storage, 3)
    runner(store, good).run()
    item = watches.pause(item.id, expected_revision=item.revision)
    article(storage, 4)
    item = watches.resume(item.id, expected_revision=item.revision)
    article(storage, 5)
    runner(store, good).run()
    rows = store.list()
    assert [(r["revision"], r["article_id"]) for r in rows] == [(2, 1), (3, 3), (5, 5)]
    assert [r["article_id"] for r in store.notification_candidates()] == [5]


def test_repeated_and_failed_migration_preserves_evaluations_and_ledgers(setup, monkeypatch):
    storage, watches, item = setup
    article(storage)
    store, runner = api(storage)
    runner(store, good).run()
    tracked = storage.insert_tracked_item("count", "quantity", "units", "09:00")
    storage.upsert_record(tracked, "2026-10-10", value_num=7, raw_input="fixture")
    with storage._connect() as conn:
        conn.execute("CREATE TABLE evaluation_settings(name TEXT,value TEXT)")
        conn.execute("INSERT INTO evaluation_settings VALUES ('disabled','true')")
        conn.execute(
            "INSERT INTO tracking_deliveries(item_id,recorded_for,kind,slot_utc,state,claimed_at) VALUES (?,'2026-10-10','scheduled','2026-10-10T00:00:00Z','unknown','2026-10-10T00:00:00Z')",
            (tracked,),
        )
        conn.execute(
            "INSERT INTO news_deliveries(delivery_id,target,kst_date,slot,created_at,updated_at,state,generation_started) VALUES ('ack','fixture','2026-10-10','morning',1,1,'sent',1)"
        )
        conn.execute(
            "INSERT INTO news_delivery_parts(delivery_id,part_no,text,hash,state,attempts,message_id,ack_at) VALUES ('ack',0,'fixture','hash','sent',1,123,1)"
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
    with storage._connect() as conn:
        assert before == {t: [tuple(r) for r in conn.execute("SELECT * FROM " + t)] for t in tables}
    from msalt.watch import schema

    migrate = schema.migrate

    def broken(conn):
        migrate(conn)
        conn.execute("CREATE TABLE evaluation_partial(value TEXT)")
        conn.execute("DELETE FROM watch_evaluations")
        raise RuntimeError("fixture migration failure")

    monkeypatch.setattr(schema, "migrate", broken)
    with pytest.raises(RuntimeError):
        storage.initialize()
    with storage._connect() as conn:
        assert before == {t: [tuple(r) for r in conn.execute("SELECT * FROM " + t)] for t in tables}
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE name='evaluation_partial'"
            ).fetchone()
            is None
        )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_listing_same_shape_when_paused(setup):
    storage, watches, item = setup
    article(storage)
    store, runner = api(storage)
    runner(store, good).run()
    before = set(store.list()[0])
    watches.pause(item.id, expected_revision=item.revision)
    assert set(store.list()[0]) == before
