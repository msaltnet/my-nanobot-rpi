import importlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from msalt.storage import Storage


@pytest.fixture
def store(tmp_path):
    storage = Storage(str(tmp_path / "watch.db"))
    storage.initialize()
    module = importlib.import_module("msalt.watch.store")
    return module.WatchStore(storage)


def add(store, name="AI", **kwargs):
    return store.add(name, description="Original Description", keywords=["ＡＩ", "GPU"],
                     excluded_keywords=["rumor"], **kwargs)


def article(store, suffix):
    store.storage.insert_article("fixture", "title", "https://fixture/" + str(suffix),
                                 "summary", "test")
    with store.storage._connect() as conn:
        return conn.execute("SELECT MAX(id) FROM news_articles").fetchone()[0]


def test_revision_watermark_restart_and_soft_delete(store):
    first = article(store, 1)
    item = add(store)
    assert (item.active, item.revision, item.start_article_id) == (False, 1, 0)
    assert item.name == "AI" and item.description == "Original Description"
    assert store.pause(item.id, expected_revision=1) == item
    with pytest.raises(ValueError):
        store.resume(item.id, expected_revision=2)
    active = store.resume(item.id, expected_revision=1)
    assert (active.active, active.revision, active.start_article_id) == (True, 2, first)
    article(store, 2)
    assert store.resume(item.id, expected_revision=2) == active
    paused = store.pause(item.id, expected_revision=2)
    assert (paused.active, paused.revision, paused.start_article_id) == (False, 3, first)
    latest = article(store, 3)
    updated = store.update(item.id, expected_revision=3, description="New description")
    assert (updated.active, updated.revision, updated.start_article_id) == (False, 4, latest)
    assert store.update(item.id, expected_revision=4, description="New description") == updated
    with pytest.raises(ValueError):
        store.update(item.id, expected_revision=3, name="Old revision")
    restarted = type(store)(Storage(store.storage.db_path))
    assert restarted.show(item.id) == updated
    resumed = restarted.resume(item.id, expected_revision=4)
    assert resumed.revision == 5
    deleted = restarted.delete(item.id, expected_revision=5)
    assert (deleted.active, deleted.revision, deleted.start_article_id) == (False, 6, latest)
    assert deleted.deleted_at is not None
    assert restarted.list() == []
    assert restarted.list(include_deleted=True) == [deleted]
    assert restarted.show(item.id) == deleted
    for operation in (restarted.pause, restarted.resume, restarted.delete, restarted.update):
        with pytest.raises(ValueError):
            operation(item.id, expected_revision=6)
    with pytest.raises(ValueError):
        add(restarted, "ＡＩ")


@pytest.mark.parametrize("field,value", [
    ("name", ""), ("name", "  "), ("name", "x" * 81), ("name", 1),
    ("name", None), ("description", ""), ("description", "\t"),
    ("description", "x" * 2001), ("description", []),
    ("keywords", "AI"), ("keywords", ("AI",)), ("keywords", None),
    ("keywords", [""]), ("keywords", [" "]), ("keywords", [1]),
    ("keywords", ["x" * 101]), ("keywords", ["x"] * 21),
    ("excluded_keywords", ["x"] * 21), ("excluded_keywords", {}),
    ("excluded_keywords", [False]),
])
def test_bad_fields_never_write(store, field, value):
    values = dict(name="valid", description="valid", keywords=[], excluded_keywords=[])
    values[field] = value
    with pytest.raises(ValueError):
        store.add(**values)
    assert store.list() == []
    item = add(store)
    with pytest.raises(ValueError):
        store.update(item.id, expected_revision=1, **{field: value})
    assert store.show(item.id) == item


def test_exact_field_boundaries_preserve_original_and_copy_lists(store):
    keys = ["k" * 100] * 20
    item = store.add("n" * 80, description="d" * 2000, keywords=keys,
                     excluded_keywords=["e" * 100] * 20)
    keys.clear()
    assert len(store.show(item.id).keywords) == 20
    assert item.name == "n" * 80 and len(item.description) == 2000
    empty = store.add("empty filter", description="all", keywords=[], excluded_keywords=[])
    assert empty.keywords == []


@pytest.mark.parametrize("identifier", [0, -1, True, "1", None, 999, 2**63])
def test_bad_ids_rejected(store, identifier):
    add(store)
    for operation in (store.show, store.pause, store.resume, store.delete, store.update):
        with pytest.raises(ValueError):
            if operation == store.show:
                operation(identifier)
            else:
                operation(identifier, expected_revision=1)


@pytest.mark.parametrize("revision", [0, -1, True, "1", None, 2, 2**63])
def test_invalid_expected_revision_even_for_noop(store, revision):
    item = add(store)
    for operation in (store.pause, store.resume, store.update, store.delete):
        with pytest.raises(ValueError):
            operation(item.id, expected_revision=revision)
    assert store.show(item.id) == item


def compete(actions):
    barrier = Barrier(len(actions))
    def run(action):
        barrier.wait(timeout=10)
        try:
            return action()
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))


def test_concurrent_normalized_duplicates_enforced_by_sqlite(store):
    names = ["Straße", "STRASSE", "ＳＴＲＡＳＳＥ"]
    results = compete([lambda name=name: add(type(store)(Storage(store.storage.db_path)), name)
                       for name in names])
    assert sum(result is not None for result in results) == 1
    assert len(store.list()) == 1
    with store.storage._connect() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO watch_conditions (name, normalized_name, description, "
                         "keywords_json, excluded_keywords_json, active, revision, start_article_id, "
                         "created_at, updated_at) SELECT 'other', normalized_name, description, "
                         "keywords_json, excluded_keywords_json, active, revision, start_article_id, "
                         "created_at, updated_at FROM watch_conditions")


def test_concurrent_revision_only_one_update_wins(store):
    item = add(store)
    results = compete([lambda n=n: type(store)(Storage(store.storage.db_path)).update(
        item.id, expected_revision=1, description="change " + str(n)) for n in range(2)])
    assert sum(result is not None for result in results) == 1
    assert store.show(item.id).revision == 2


def test_concurrent_active_cap_and_pause_releases_capacity(store):
    items = [add(store, str(n)) for n in range(22)]
    for item in items[:19]:
        store.resume(item.id, expected_revision=1)
    results = compete([lambda item=item: type(store)(Storage(store.storage.db_path)).resume(
        item.id, expected_revision=1) for item in items[19:]])
    assert sum(result is not None for result in results) == 1
    assert sum(item.active for item in store.list()) == 20
    store.pause(items[0].id, expected_revision=2)
    spare = next(item for item in store.list() if not item.active and item.id != items[0].id)
    assert store.resume(spare.id, expected_revision=1).active


def test_concurrent_total_cap_and_deleted_capacity(store):
    items = [add(store, str(n)) for n in range(99)]
    results = compete([lambda n=n: add(type(store)(Storage(store.storage.db_path)), str(n))
                       for n in range(99, 102)])
    assert sum(result is not None for result in results) == 1
    assert len(store.list()) == 100
    store.delete(items[0].id, expected_revision=1)
    assert add(store, "replacement").revision == 1
    assert len(store.list(include_deleted=True)) == 101
    with pytest.raises(ValueError):
        add(store, "0")


def test_initialization_adds_condition_management_table(tmp_path):
    storage = Storage(str(tmp_path / "management.db"))
    storage.initialize()
    with storage._connect() as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='watch_conditions'").fetchone() is not None


def test_duplicate_update_rolls_back_revision_fields_and_watermark(store):
    original = add(store, "Original")
    add(store, "Straße")
    article(store, "new")
    with pytest.raises(ValueError):
        store.update(original.id, expected_revision=1, name="ＳＴＲＡＳＳＥ", description="changed")
    assert store.show(original.id) == original


def test_resume_waits_for_article_transaction_and_captures_committed_max(store):
    item = add(store)
    began = Event()
    other_storage = Storage(store.storage.db_path)
    connect = other_storage._connect
    def observed_connect():
        conn = connect()
        conn.set_trace_callback(lambda sql: began.set() if sql == "BEGIN IMMEDIATE" else None)
        return conn
    other_storage._connect = observed_connect
    writer = store.storage._connect()
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO news_articles(source, title, url) VALUES ('fixture', 'new', 'https://fixture/locked')")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(type(store)(other_storage).resume, item.id, expected_revision=1)
            assert began.wait(timeout=10)
            assert not future.done()
            writer.commit()
            result = future.result(timeout=10)
        assert result.start_article_id == 1
    finally:
        writer.rollback()
        writer.close()
