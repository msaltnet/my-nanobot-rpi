import pytest

from msalt.storage import Storage
from msalt.lifestyle.sleep import SleepTracker


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    s = Storage(str(db_path))
    s.initialize()
    return s


def test_record_sleep(storage):
    tracker = SleepTracker(storage)
    tracker.record("2026-04-11", bedtime="23:00", wakeup="06:30", duration_min=450)
    log = storage.get_sleep_log("2026-04-11")
    assert log is not None
    assert log["bedtime"] == "23:00"
    assert log["wakeup"] == "06:30"
    assert log["duration_min"] == 450


def test_record_sleep_overwrites_same_date(storage):
    tracker = SleepTracker(storage)
    tracker.record("2026-04-11", bedtime="23:00", wakeup="06:30", duration_min=450)
    tracker.record("2026-04-11", bedtime="00:00", wakeup="07:00", duration_min=420)
    log = storage.get_sleep_log("2026-04-11")
    assert log["bedtime"] == "00:00"


def test_get_weekly_stats(storage):
    tracker = SleepTracker(storage)
    tracker.record("2026-04-07", bedtime="23:00", wakeup="06:00", duration_min=420)
    tracker.record("2026-04-08", bedtime="23:30", wakeup="06:30", duration_min=420)
    tracker.record("2026-04-09", bedtime="22:00", wakeup="06:00", duration_min=480)

    stats = tracker.get_stats(days=7)
    assert stats["count"] == 3
    assert stats["avg_duration_min"] == 440
    assert stats["min_duration_min"] == 420
    assert stats["max_duration_min"] == 480
