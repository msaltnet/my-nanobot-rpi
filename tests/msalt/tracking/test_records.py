import pytest
from msalt.storage import Storage
from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager


@pytest.fixture
def setup(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    items = TrackedItemManager(s)
    records = RecordManager(s, items)
    return s, items, records


def test_upsert_freetext(setup):
    _, items, records = setup
    items.add("메모", "freetext", None, "23:00")
    records.upsert("메모", "2026-04-13", raw_input="기분 좋음",
                   value_text="기분 좋음")
    recs = records.recent("메모", days=1, ref_date="2026-04-13")
    assert len(recs) == 1
    assert recs[0]["value_text"] == "기분 좋음"


def test_upsert_unknown_item_raises(setup):
    _, _, records = setup
    with pytest.raises(KeyError):
        records.upsert("없음", "2026-04-13", raw_input="x")


def test_upsert_overwrites_same_date(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    records.upsert("수면", "2026-04-13", value_num=420, raw_input="7h")
    records.upsert("수면", "2026-04-13", value_num=480, raw_input="8h")
    recs = records.recent("수면", days=1, ref_date="2026-04-13")
    assert len(recs) == 1
    assert recs[0]["value_num"] == 480


def test_summarize_duration(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    records.upsert("수면", "2026-04-12", value_num=420, raw_input="7h")
    records.upsert("수면", "2026-04-13", value_num=480, raw_input="8h")
    summary = records.summarize("수면", days=7, ref_date="2026-04-13")
    assert "수면" in summary
    assert "2회" in summary
    assert "평균" in summary
    assert "450" in summary or "7시간 30분" in summary


def test_summarize_quantity(setup):
    _, items, records = setup
    items.add("음주", "quantity", "잔", "22:00")
    records.upsert("음주", "2026-04-12", value_num=2.0, raw_input="2잔")
    records.upsert("음주", "2026-04-13", value_num=4.0, raw_input="4잔")
    summary = records.summarize("음주", days=7, ref_date="2026-04-13")
    assert "음주" in summary
    assert "잔" in summary
    assert "6" in summary  # 합계 6잔
    assert "평균" in summary  # 평균 3잔


def test_summarize_boolean(setup):
    _, items, records = setup
    items.add("운동", "boolean", None, "20:00")
    records.upsert("운동", "2026-04-12", value_bool=True, raw_input="함")
    records.upsert("운동", "2026-04-13", value_bool=False, raw_input="안함")
    summary = records.summarize("운동", days=7, ref_date="2026-04-13")
    assert "운동" in summary
    assert "1/2" in summary or "50%" in summary


def test_summarize_freetext_lists_recent(setup):
    _, items, records = setup
    items.add("메모", "freetext", None, "23:00")
    records.upsert("메모", "2026-04-12", value_text="피곤",
                   raw_input="피곤")
    records.upsert("메모", "2026-04-13", value_text="좋음",
                   raw_input="좋음")
    summary = records.summarize("메모", days=7, ref_date="2026-04-13")
    assert "피곤" in summary
    assert "좋음" in summary


def test_summarize_no_records(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    summary = records.summarize("수면", days=7, ref_date="2026-04-13")
    assert "기록 없음" in summary or "없" in summary


def test_recent_returns_empty_for_unknown_item(setup):
    _, _, records = setup
    with pytest.raises(KeyError):
        records.recent("없음", days=7, ref_date="2026-04-13")
