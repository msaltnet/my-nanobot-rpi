import pytest
from msalt.storage import Storage
from msalt.tracking.items import (
    TrackedItemManager, ItemAlreadyExists, ItemNotFound, DEFAULT_SEEDS,
)


@pytest.fixture
def storage(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    return s


def test_add_and_get_item(storage):
    mgr = TrackedItemManager(storage)
    mgr.add("수면", "duration", None, "08:00")
    item = mgr.get("수면")
    assert item is not None
    assert item["schema"] == "duration"


def test_add_duplicate_raises(storage):
    mgr = TrackedItemManager(storage)
    mgr.add("수면", "duration", None, "08:00")
    with pytest.raises(ItemAlreadyExists):
        mgr.add("수면", "duration", None, "09:00")


def test_invalid_schema_rejected(storage):
    mgr = TrackedItemManager(storage)
    with pytest.raises(ValueError):
        mgr.add("x", "invalid", None, "08:00")


def test_invalid_schedule_time_rejected(storage):
    mgr = TrackedItemManager(storage)
    with pytest.raises(ValueError):
        mgr.add("x", "duration", None, "25:00")
    with pytest.raises(ValueError):
        mgr.add("x", "duration", None, "08:99")
    with pytest.raises(ValueError):
        mgr.add("x", "duration", None, "8:00")  # 두 자리 강제


def test_quantity_requires_unit(storage):
    mgr = TrackedItemManager(storage)
    with pytest.raises(ValueError):
        mgr.add("음주", "quantity", None, "22:00")


def test_non_quantity_unit_must_be_none(storage):
    mgr = TrackedItemManager(storage)
    with pytest.raises(ValueError):
        mgr.add("수면", "duration", "분", "08:00")


def test_list_all_returns_sorted(storage):
    mgr = TrackedItemManager(storage)
    mgr.add("b", "boolean", None, "10:00")
    mgr.add("a", "boolean", None, "11:00")
    items = mgr.list_all()
    assert [i["name"] for i in items] == ["a", "b"]


def test_delete_removes_item(storage):
    mgr = TrackedItemManager(storage)
    mgr.add("수면", "duration", None, "08:00")
    mgr.delete("수면")
    assert mgr.get("수면") is None


def test_delete_nonexistent_raises(storage):
    mgr = TrackedItemManager(storage)
    with pytest.raises(ItemNotFound):
        mgr.delete("없음")


def test_seed_defaults_when_empty(storage):
    mgr = TrackedItemManager(storage)
    mgr.seed_defaults()
    items = mgr.list_all()
    names = {i["name"] for i in items}
    assert names == {s["name"] for s in DEFAULT_SEEDS}


def test_seed_defaults_no_op_when_not_empty(storage):
    mgr = TrackedItemManager(storage)
    mgr.add("기존", "boolean", None, "12:00")
    mgr.seed_defaults()
    items = mgr.list_all()
    assert [i["name"] for i in items] == ["기존"]
