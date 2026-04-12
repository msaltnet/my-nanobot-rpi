import pytest

from msalt.storage import Storage
from msalt.lifestyle.tracker import LifeTracker


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    s = Storage(str(db_path))
    s.initialize()
    return s


def test_log_entry(storage):
    tracker = LifeTracker(storage)
    entry_id = tracker.log("오늘 5km 달림")
    assert entry_id is not None
    entries = storage.get_life_logs_since("2020-01-01")
    assert len(entries) == 1
    assert entries[0]["raw_text"] == "오늘 5km 달림"
    assert entries[0]["category"] == "exercise"


def test_log_multiple_categories(storage):
    tracker = LifeTracker(storage)
    tracker.log("5km 달림")
    tracker.log("커피 3잔")
    tracker.log("기분 좋음")

    entries = storage.get_life_logs_since("2020-01-01")
    categories = {e["category"] for e in entries}
    assert "exercise" in categories
    assert "food" in categories
    assert "mood" in categories


def test_get_summary_by_category(storage):
    tracker = LifeTracker(storage)
    tracker.log("5km 달림")
    tracker.log("3km 달림")
    tracker.log("커피 마심")

    summary = tracker.get_summary_by_category(days=7)
    assert summary["exercise"] == 2
    assert summary["food"] == 1
