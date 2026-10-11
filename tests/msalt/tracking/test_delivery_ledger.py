import multiprocessing
import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from msalt.storage import Storage
from msalt.tracking import cli
from msalt.tracking.delivery_errors import DeliveryRejected, DeliveryUnknown
from msalt.tracking.delivery_store import DeliveryCandidate, DeliveryStore
from msalt.tracking.dispatcher import Dispatcher
from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager

KST = ZoneInfo('Asia/Seoul')


def fixture(db):
    storage = Storage(str(db))
    storage.initialize()
    items = TrackedItemManager(storage)
    return storage, items, RecordManager(storage, items)


@pytest.mark.parametrize('session_failure', [False, True])
@pytest.mark.parametrize('reopen', [False, True])
def test_production_ack_repeated_window_posts_once(tmp_path, monkeypatch, session_failure, reopen):
    db = tmp_path / 'ledger.db'
    storage, items, records = fixture(db)
    items.add('exercise', 'boolean', None, '08:00')
    posts = []
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'synthetic')
    monkeypatch.setenv('TELEGRAM_USER_ID', 'synthetic')
    def post(*args, **kwargs):
        posts.append(kwargs['json'])
        return SimpleNamespace(status_code=200, json=lambda: {'ok': True})
    def session(*args):
        if session_failure:
            raise OSError('synthetic session failure')
    monkeypatch.setattr(cli.httpx, 'post', post)
    monkeypatch.setattr(cli, '_record_outbound_in_session', session)
    sender = cli._make_telegram_sender(workspace=tmp_path)
    Dispatcher(items, records, sender).run(datetime(2026, 10, 9, 8, 0, tzinfo=KST))
    if reopen:
        storage, items, records = fixture(db)
    Dispatcher(items, records, sender).run(datetime(2026, 10, 9, 8, 5, tzinfo=KST))
    assert len(posts) == 1
    assert storage.get_tracked_item_by_name('exercise')['pending_recorded_for'] == '2026-10-09'




def tick(hour=8, minute=0, day=9):
    return datetime(2026, 10, day, hour, minute, tzinfo=KST)


def ledger(storage):
    with storage._connect() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM tracking_deliveries ORDER BY id')]


@pytest.mark.parametrize('error', [DeliveryUnknown('unknown'), TimeoutError('timeout')])
def test_unknown_blocks_reopen_same_slot_and_future_retries(tmp_path, error):
    db = tmp_path / 'unknown.db'
    storage, items, records = fixture(db)
    items.add('exercise', 'boolean', None, '08:00')
    posts = []
    def send(text):
        posts.append(text)
        raise error
    with pytest.raises(type(error)):
        Dispatcher(items, records, send).run(tick())
    storage, items, records = fixture(db)
    for now in [tick(8, 5), tick(9), tick(14), tick(20)]:
        assert Dispatcher(items, records, posts.append).run(now) == []
    assert len(posts) == 1
    assert ledger(storage)[0]['state'] == 'unknown'
    assert storage.get_tracked_item_by_name('exercise')['last_asked_at'] is None


def test_rejected_retains_target_and_allows_only_next_retry(tmp_path):
    storage, items, records = fixture(tmp_path / 'reject.db')
    items.add('exercise', 'boolean', None, '08:00')
    def reject(text):
        raise DeliveryRejected('rejected')
    with pytest.raises(DeliveryRejected):
        Dispatcher(items, records, reject).run(tick())
    item = items.get('exercise')
    assert item['pending_recorded_for'] == '2026-10-09'
    assert item['pending_since'] == '2026-10-08 23:00:00'
    assert item['last_asked_at'] is None
    sent = []
    assert Dispatcher(items, records, sent.append).run(tick(8, 5)) == []
    assert len(Dispatcher(items, records, sent.append).run(tick(9))) == 1
    assert Dispatcher(items, records, sent.append).run(tick(9, 5)) == []
    assert len(sent) == 1
    assert [r['state'] for r in ledger(storage)] == ['rejected', 'sent']


def test_claim_database_failure_never_posts(tmp_path):
    storage, items, records = fixture(tmp_path / 'claim.db')
    items.add('first', 'boolean', None, '08:00')
    items.add('second', 'boolean', None, '08:00')
    with storage._connect() as conn:
        conn.execute("CREATE TRIGGER fail_second BEFORE INSERT ON tracking_deliveries "
                     "WHEN NEW.item_id = 2 BEGIN SELECT RAISE(ABORT, 'claim failure'); END")
    sent = []
    with pytest.raises(sqlite3.IntegrityError, match='claim failure'):
        Dispatcher(items, records, sent.append).run(tick())
    assert sent == []
    assert ledger(storage) == []


@pytest.mark.parametrize('failure_point', ['after_claim', 'post_before_ack', 'ack_database'])
def test_crash_or_ack_database_failure_keeps_claim_and_blocks_resend(tmp_path, failure_point):
    db = tmp_path / 'crash.db'
    storage, items, records = fixture(db)
    items.add('exercise', 'boolean', None, '08:00')
    posts = []
    def send(text):
        # A second writer inside the sender proves claim was committed and its transaction closed.
        with storage._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS external_boundary (value INTEGER)")
        if failure_point != 'after_claim':
            posts.append(text)
        if failure_point in ('after_claim', 'post_before_ack'):
            raise SystemExit('synthetic crash')
        with storage._connect() as conn:
            conn.execute("CREATE TRIGGER fail_ack BEFORE UPDATE OF last_asked_at ON tracked_items "
                         "BEGIN SELECT RAISE(ABORT, 'ACK state failure'); END")
    expected = SystemExit if failure_point != 'ack_database' else sqlite3.IntegrityError
    with pytest.raises(expected):
        Dispatcher(items, records, send).run(tick())
    storage, items, records = fixture(db)
    for now in [tick(8, 5), tick(9), tick(14), tick(20)]:
        assert Dispatcher(items, records, posts.append).run(now) == []
    assert len(posts) == (0 if failure_point == 'after_claim' else 1)
    assert ledger(storage)[0]['state'] == 'claimed'
    assert items.get('exercise')['pending_since'] is None
    assert items.get('exercise')['last_asked_at'] is None


def test_ack_batch_pending_and_last_asked_are_one_transaction(tmp_path):
    storage, items, records = fixture(tmp_path / 'atomic.db')
    items.add('first', 'boolean', None, '08:00')
    items.add('second', 'boolean', None, '08:00')
    with storage._connect() as conn:
        conn.execute("CREATE TRIGGER fail_second_ack BEFORE UPDATE OF last_asked_at ON tracked_items "
                     "WHEN NEW.id = 2 BEGIN SELECT RAISE(ABORT, 'ACK state failure'); END")
    posts = []
    with pytest.raises(sqlite3.IntegrityError):
        Dispatcher(items, records, posts.append).run(tick())
    assert len(posts) == 1
    assert [r['state'] for r in ledger(storage)] == ['claimed', 'claimed']
    assert all(i['pending_since'] is None and i['last_asked_at'] is None for i in items.list_all())


def test_partial_batch_conflict_only_sends_unclaimed_item(tmp_path):
    storage, items, records = fixture(tmp_path / 'partial.db')
    items.add('first', 'boolean', None, '08:00')
    posts = []
    Dispatcher(items, records, posts.append).run(tick())
    items.add('second', 'boolean', None, '08:00')
    messages = Dispatcher(items, records, posts.append).run(tick(8, 5))
    assert [m.item_name for m in messages] == ['second']
    assert 'first' not in posts[1] and 'second' in posts[1]
    assert len(ledger(storage)) == 2


def test_next_day_and_existing_retry_slots_are_independent(tmp_path):
    storage, items, records = fixture(tmp_path / 'slots.db')
    items.add('exercise', 'boolean', None, '08:00')
    posts = []
    for now in [tick(), tick(9), tick(14), tick(20), tick(day=10)]:
        Dispatcher(items, records, posts.append).run(now)
    assert len(posts) == 5
    rows = ledger(storage)
    assert rows[0]['slot_utc'] == '2026-10-08T23:00:00+00:00'
    assert rows[1]['slot_utc'] == '2026-10-09T00:00:00+00:00'
    assert rows[-1]['recorded_for'] == '2026-10-10'


def test_response_during_post_does_not_restore_resolved_pending(tmp_path):
    storage, items, records = fixture(tmp_path / 'response.db')
    items.add('exercise', 'boolean', None, '08:00')
    def send(text):
        records.upsert('exercise', '2026-10-09', raw_input='synthetic', value_bool=True)
    Dispatcher(items, records, send).run(tick())
    assert items.get('exercise')['pending_since'] is None
    assert ledger(storage)[0]['state'] == 'sent'
    assert Dispatcher(items, records, lambda text: pytest.fail('resent')).run(tick(9)) == []


def test_delete_cascades_ledger_and_new_item_has_independent_id(tmp_path):
    storage, items, records = fixture(tmp_path / 'delete.db')
    old_id = items.add('exercise', 'boolean', None, '08:00')
    posts = []
    Dispatcher(items, records, posts.append).run(tick())
    old_id = items.get('exercise')['id']
    items.delete('exercise')
    assert ledger(storage) == []
    items.add('exercise', 'boolean', None, '08:00')
    assert items.get('exercise')['id'] > old_id
    Dispatcher(items, records, posts.append).run(tick(8, 5))
    assert len(posts) == 2


def test_cli_status_and_confirmed_release_keep_same_slot_tombstone(tmp_path, capsys, monkeypatch):
    storage, items, records = fixture(tmp_path / 'release.db')
    items.add('private-item-marker', 'boolean', None, '08:00')
    def unknown(text):
        raise DeliveryUnknown('private-error-marker')
    with pytest.raises(DeliveryUnknown):
        Dispatcher(items, records, unknown).run(tick())
    delivery_id = ledger(storage)[0]['id']
    db = storage.db_path
    assert cli.run_command(['delivery-status'], db_path=db) == 0
    output = capsys.readouterr().out
    assert str(delivery_id) in output and 'unknown' in output
    assert 'private-item-marker' not in output and 'private-error-marker' not in output
    assert cli.run_command(['delivery-release', str(delivery_id)], db_path=db) == 2
    assert ledger(storage)[0]['resolved_at'] is None
    freeze_release_clock(monkeypatch, tick(8, 5))
    assert cli.run_command(['delivery-release', str(delivery_id), '--confirm-received'], db_path=db) == 0
    assert ledger(storage)[0]['state'] == 'unknown'
    assert ledger(storage)[0]['resolved_at'] is not None
    posts = []
    assert Dispatcher(items, records, posts.append).run(tick(8, 5)) == []
    assert len(Dispatcher(items, records, posts.append).run(tick(9))) == 1
    assert len(posts) == 1
    assert cli.run_command(['delivery-release', str(delivery_id), '--confirm-received'], db_path=db) == 2
    assert cli.run_command(['delivery-release', '99999', '--confirm-received'], db_path=db) == 2


def _worker(db, start, ready, posts, session_failure):
    # Each spawn opens real SQLite independently and invokes the production ACK sender.
    import os

    from msalt.tracking import cli as worker_cli
    storage = Storage(db)
    items = TrackedItemManager(storage)
    records = RecordManager(storage, items)
    os.environ['TELEGRAM_BOT_TOKEN'] = 'synthetic'
    os.environ['TELEGRAM_USER_ID'] = 'synthetic'
    def post(*args, **kwargs):
        with open(posts, 'a', encoding='utf8') as output:
            output.write('POST\n')
        return SimpleNamespace(status_code=200, json=lambda: {'ok': True})
    def session(*args):
        if session_failure:
            raise OSError('synthetic session failure')
    worker_cli.httpx.post = post
    worker_cli._record_outbound_in_session = session
    ready.put(True)
    if not start.wait(15):
        raise RuntimeError('start timeout')
    Dispatcher(items, records, worker_cli._make_telegram_sender()).run(tick())


@pytest.mark.parametrize('session_failure', [False, True])
def test_two_actual_processes_production_ack_posts_once(tmp_path, monkeypatch, session_failure):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    db = tmp_path / 'concurrent.db'
    storage, items, _ = fixture(db)
    items.add('exercise', 'boolean', None, '08:00')
    ctx = multiprocessing.get_context('spawn')
    start, ready = ctx.Event(), ctx.Queue()
    posts = tmp_path / 'posts.txt'
    processes = [ctx.Process(target=_worker, args=(str(db), start, ready, str(posts), session_failure))
                 for _ in range(2)]
    try:
        for process in processes:
            process.start()
        assert ready.get(timeout=15) is True
        assert ready.get(timeout=15) is True
        start.set()
        for process in processes:
            process.join(20)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(5)
        ready.close()
        ready.join_thread()
    assert posts.read_text(encoding='utf8').splitlines() == ['POST']
    assert len(ledger(storage)) == 1



def test_equivalent_utc_offsets_claim_same_slot(tmp_path):
    storage, items, _ = fixture(tmp_path / 'utc.db')
    item_id = items.add('exercise', 'boolean', None, '08:00')
    store = DeliveryStore(storage)
    claims = store.claim([DeliveryCandidate(item_id, '2026-10-09', 'scheduled',
                                            '2026-10-09T08:00:00+09:00')],
                         '2026-10-08 23:00:00')
    store.finish([claims[0]['id']], 'sent', '2026-10-08 23:00:00')
    assert store.claim([DeliveryCandidate(item_id, '2026-10-09', 'scheduled',
                                         '2026-10-08T23:00:00Z')],
                      '2026-10-08 23:05:00') == []
    with pytest.raises(ValueError, match='timezone'):
        store.claim([DeliveryCandidate(item_id, '2026-10-09', 'scheduled',
                                       '2026-10-09T08:00:00')], '2026-10-08 23:00:00')
    assert len(ledger(storage)) == 1


def test_unknown_retry_keeps_original_pending_and_blocks_later_slots(tmp_path, monkeypatch):
    storage, items, records = fixture(tmp_path / 'retry-unknown.db')
    items.add('exercise', 'boolean', None, '08:00')
    sent = []
    Dispatcher(items, records, sent.append).run(tick())
    def unknown(text):
        sent.append(text)
        raise DeliveryUnknown('unknown')
    with pytest.raises(DeliveryUnknown):
        Dispatcher(items, records, unknown).run(tick(9))
    item = items.get('exercise')
    assert item['pending_recorded_for'] == '2026-10-09'
    assert item['last_asked_at'] == '2026-10-08 23:00:00'
    assert Dispatcher(items, records, sent.append).run(tick(14)) == []
    assert len(sent) == 2
    freeze_release_clock(monkeypatch, tick(14, 5))
    DeliveryStore(storage).release(ledger(storage)[1]['id'], confirmed_received=True)
    assert Dispatcher(items, records, sent.append).run(tick(14, 20)) == []
    assert len(Dispatcher(items, records, sent.append).run(tick(20))) == 1


def test_unresolved_prior_date_does_not_block_next_date(tmp_path):
    storage, items, records = fixture(tmp_path / 'independent-date.db')
    items.add('exercise', 'boolean', None, '08:00')
    def unknown(text):
        raise DeliveryUnknown('unknown')
    with pytest.raises(DeliveryUnknown):
        Dispatcher(items, records, unknown).run(tick())
    assert len(Dispatcher(items, records, lambda text: None).run(tick(day=10))) == 1
    assert [r['state'] for r in ledger(storage)] == ['unknown', 'sent']


def test_release_claimed_with_record_keeps_pending_resolved(tmp_path):
    storage, items, records = fixture(tmp_path / 'resolve-record.db')
    item_id = items.add('exercise', 'boolean', None, '08:00')
    claim = DeliveryStore(storage).claim([
        DeliveryCandidate(item_id, '2026-10-09', 'scheduled', '2026-10-09T08:00:00+09:00')
    ], '2026-10-08 23:00:00')[0]
    records.upsert('exercise', '2026-10-09', raw_input='yes', value_bool=True)
    DeliveryStore(storage).release(claim['id'], confirmed_received=True)
    assert items.get('exercise')['pending_since'] is None
    assert ledger(storage)[0]['state'] == 'claimed'
    assert Dispatcher(items, records, lambda text: pytest.fail('resent')).run(tick(9)) == []


def test_stale_pending_cleanup_does_not_clear_other_process_new_pending(tmp_path, monkeypatch):
    db = tmp_path / 'stale.db'
    storage, items, records = fixture(db)
    items.add('exercise', 'boolean', None, '08:00')
    Dispatcher(items, records, lambda text: None).run(tick())
    original_clear = storage.clear_pending
    triggered = []
    def interleave(item_id, **kwargs):
        if not triggered:
            triggered.append(True)
            other_storage, other_items, other_records = fixture(db)
            Dispatcher(other_items, other_records, lambda text: None).run(tick(day=10))
        original_clear(item_id, **kwargs)
    monkeypatch.setattr(storage, 'clear_pending', interleave)
    assert Dispatcher(items, records, lambda text: pytest.fail('duplicate')).run(tick(day=10)) == []
    assert items.get('exercise')['pending_recorded_for'] == '2026-10-10'
    assert items.get('exercise')['last_asked_at'] == '2026-10-09 23:00:00'


def test_repeated_additive_migration_preserves_legacy_news_records_and_settings(tmp_path):
    storage, items, records = fixture(tmp_path / 'migration.db')
    items.add('exercise', 'boolean', None, '08:00')
    records.upsert('exercise', '2026-10-08', raw_input='legacy', value_bool=False)
    storage.insert_article('synthetic', 'title', 'https://example.invalid/a', 'summary', 'test')
    storage.mark_articles_briefed(['https://example.invalid/a'], 'legacy')
    with storage._connect() as conn:
        conn.execute('DROP TABLE tracking_deliveries')
        conn.execute('CREATE TABLE private_settings (name TEXT PRIMARY KEY, value TEXT)')
        conn.execute("INSERT INTO private_settings VALUES ('synthetic', 'keep')")
        for state in ['acked', 'unknown']:
            conn.execute('INSERT INTO news_deliveries '
                         '(delivery_id,target,kst_date,slot,created_at,updated_at,state,'
                         'generation_started) VALUES (?,?,?,?,?,?,?,?)',
                         (state, 'synthetic', '2026-10-09', state, 1, 1, state, 1))
            conn.execute('INSERT INTO news_delivery_parts '
                         '(delivery_id,part_no,text,hash,state,message_id,ack_at) '
                         'VALUES (?,?,?,?,?,?,?)', (state, 1, 'keep', 'hash', state, 42, 1))
    tables = ['tracked_items', 'records', 'news_articles', 'news_briefed_articles',
              'news_deliveries', 'news_delivery_parts', 'private_settings']
    def snapshot():
        with storage._connect() as conn:
            return {table: [tuple(r) for r in conn.execute(f'SELECT * FROM {table}')]
                    for table in tables}
    before = snapshot()
    storage.initialize()
    storage.initialize()
    assert snapshot() == before
    assert ledger(storage) == []
    # An old reader still selects its original columns from the upgraded DB.
    with sqlite3.connect(storage.db_path) as conn:
        assert conn.execute('SELECT name,schema,schedule_time FROM tracked_items').fetchall() == [
            ('exercise', 'boolean', '08:00')]
        assert conn.execute('SELECT raw_input,value_bool FROM records').fetchall() == [('legacy', 0)]


def test_migration_helper_does_not_commit_and_initialize_failure_rolls_back(tmp_path, monkeypatch):
    from msalt.tracking import delivery_schema
    db = tmp_path / 'migration-rollback.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE tracked_items '
                     '(id INTEGER PRIMARY KEY, name TEXT, schema TEXT, unit TEXT, '
                     'schedule_time TEXT, frequency TEXT, created_at TEXT)')
        conn.execute("INSERT INTO tracked_items VALUES (1,'legacy','boolean',NULL,'08:00','daily','old')")
    original = delivery_schema.migrate
    def fail(conn):
        assert conn.in_transaction
        original(conn)
        assert conn.in_transaction
        raise RuntimeError('migration failure')
    monkeypatch.setattr(delivery_schema, 'migrate', fail)
    with pytest.raises(RuntimeError, match='migration failure'):
        Storage(str(db)).initialize()
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
            ('tracked_items',)]
        assert conn.execute('SELECT name FROM tracked_items').fetchall() == [('legacy',)]
    monkeypatch.setattr(delivery_schema, 'migrate', original)
    Storage(str(db)).initialize()
    with sqlite3.connect(db) as conn:
        conn.execute('BEGIN IMMEDIATE')
        original(conn)
        assert conn.in_transaction
        conn.rollback()


def freeze_release_clock(monkeypatch, when):
    from msalt.tracking import delivery_store
    class ReleaseClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return when.astimezone(tz)
    monkeypatch.setattr(delivery_store, 'datetime', ReleaseClock)


def test_rejection_after_retry_slot_waits_for_next_future_slot(tmp_path):
    storage, items, records = fixture(tmp_path / 'delayed-rejection.db')
    items.add('exercise', 'boolean', None, '08:45')
    def reject(text):
        raise DeliveryRejected('rejected')
    with pytest.raises(DeliveryRejected):
        Dispatcher(items, records, reject).run(tick(9, 5))
    item = items.get('exercise')
    assert item['pending_since'] == '2026-10-09 00:05:00'
    assert item['pending_recorded_for'] == '2026-10-09'
    assert item['last_asked_at'] is None
    posts = []
    assert Dispatcher(items, records, posts.append).run(tick(9, 20)) == []
    assert posts == []
    assert len(Dispatcher(items, records, posts.append).run(tick(14))) == 1
    assert Dispatcher(items, records, posts.append).run(tick(14, 5)) == []
    assert len(posts) == 1
    assert [r['slot_utc'] for r in ledger(storage)] == [
        '2026-10-08T23:45:00+00:00', '2026-10-09T05:00:00+00:00']


def test_release_after_retry_slot_waits_for_next_future_slot(tmp_path, monkeypatch):
    storage, items, records = fixture(tmp_path / 'delayed-release.db')
    items.add('exercise', 'boolean', None, '08:00')
    def unknown(text):
        raise DeliveryUnknown('unknown')
    with pytest.raises(DeliveryUnknown):
        Dispatcher(items, records, unknown).run(tick())
    freeze_release_clock(monkeypatch, tick(9, 5))
    DeliveryStore(storage).release(ledger(storage)[0]['id'], confirmed_received=True)
    assert ledger(storage)[0]['resolved_at'] == '2026-10-09T00:05:00+00:00'
    assert items.get('exercise')['last_asked_at'] is None
    posts = []
    assert Dispatcher(items, records, posts.append).run(tick(9, 20)) == []
    assert posts == []
    assert len(Dispatcher(items, records, posts.append).run(tick(14))) == 1
    assert len(posts) == 1
    assert ledger(storage)[0]['state'] == 'unknown'
    assert ledger(storage)[1]['slot_utc'] == '2026-10-09T05:00:00+00:00'


@pytest.mark.parametrize('outcome', ['rejected', 'released'])
def test_claim_rechecks_persisted_boundary_for_stale_candidate_and_equal_slot(
    tmp_path, monkeypatch, outcome
):
    storage, items, _ = fixture(tmp_path / 'stale-candidate.db')
    item_id = items.add('exercise', 'boolean', None, '08:00')
    store = DeliveryStore(storage)
    claim = store.claim([
        DeliveryCandidate(item_id, '2026-10-09', 'scheduled', '2026-10-09T08:00:00+09:00')
    ], '2026-10-08 23:00:00')[0]
    candidate = DeliveryCandidate(item_id, '2026-10-09', 'retry', '2026-10-09T09:00:00+09:00')
    # The retry candidate existed before another SQLite connection finalized its boundary.
    other = DeliveryStore(Storage(storage.db_path))
    if outcome == 'rejected':
        other.finish([claim['id']], 'rejected', '2026-10-09 00:00:00')
    else:
        other.finish([claim['id']], 'unknown', '2026-10-08 23:00:00')
        freeze_release_clock(monkeypatch, tick(9))
        other.release(claim['id'], confirmed_received=True)
    assert store.claim([candidate], '2026-10-09 00:20:00') == []
    assert len(ledger(storage)) == 1
    assert len(store.claim([
        DeliveryCandidate(item_id, '2026-10-09', 'retry', '2026-10-09T14:00:00+09:00')
    ], '2026-10-09 05:00:00')) == 1


def test_legacy_pending_without_delivery_boundary_preserves_existing_retry(tmp_path):
    storage, items, records = fixture(tmp_path / 'legacy-retry.db')
    item_id = items.add('exercise', 'boolean', None, '08:00')
    storage.set_pending_since(item_id, '2026-10-09 00:05:00', '2026-10-09')
    posts = []
    assert len(Dispatcher(items, records, posts.append).run(tick(9, 20))) == 1
    assert len(posts) == 1
    assert ledger(storage)[0]['slot_utc'] == '2026-10-09T00:00:00+00:00'
