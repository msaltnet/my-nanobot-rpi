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


def test_drinking_record_keeps_structured_detail(setup):
    _, items, records = setup
    items.add("음주", "quantity", "g", "22:00")
    records.upsert(
        "음주",
        "2026-04-13",
        value_num=48.3,
        value_json={
            "drink_type": "소주",
            "amount": 1,
            "unit": "병",
            "serving_ml": 360,
            "abv_percent": 17,
            "alcohol_g": 48.3,
        },
        raw_input="소주 1병",
    )
    recs = records.recent("음주", days=1, ref_date="2026-04-13")
    assert '"drink_type": "소주"' in recs[0]["value_json"]
    assert recs[0]["value_num"] == 48.3
    summary = records.summarize("음주", days=7, ref_date="2026-04-13")
    assert "48.3g" in summary
    assert "소주 1병" in summary


def test_drinking_none_records_zero_alcohol(setup):
    _, items, records = setup
    items.add("음주", "quantity", "g", "22:00")
    records.upsert(
        "음주",
        "2026-04-13",
        value_num=0,
        value_json={
            "drink_type": None,
            "amount": 0,
            "unit": "잔",
            "serving_ml": None,
            "abv_percent": None,
            "alcohol_g": 0,
        },
        raw_input="안 마심",
    )
    summary = records.summarize("음주", days=7, ref_date="2026-04-13")
    assert "0g" in summary


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


def test_advice_after_record_mentions_frequent_drinking_and_stale_boolean(setup):
    _, items, records = setup
    items.add("음주", "quantity", "g", "22:00")
    items.add("영어공부", "boolean", None, "22:00")
    records.upsert("음주", "2026-04-08", value_num=20, raw_input="맥주")
    records.upsert("음주", "2026-04-10", value_num=30, raw_input="와인")
    records.upsert("음주", "2026-04-13", value_num=48.3, raw_input="소주")

    advice = records.advice_after_record("음주", "2026-04-13")

    assert "최근 7일 음주 3일" in advice
    assert "최근 30일 음주 3일" in advice
    assert "횟수와 양을 조금 줄이는 방향" in advice
    assert "영어공부는 최근 7일과 최근 30일 모두 실천 기록이 없네" in advice


def test_advice_after_record_mentions_boolean_not_done(setup):
    _, items, records = setup
    items.add("영어공부", "boolean", None, "22:00")
    records.upsert("영어공부", "2026-04-13", value_bool=False,
                   raw_input="영어공부 안함")

    advice = records.advice_after_record("영어공부", "2026-04-13")

    assert "영어공부는 최근 7일과 최근 30일 모두 실천 기록이 없네" in advice


def test_advice_after_record_encourages_boolean_with_monthly_history(setup):
    _, items, records = setup
    items.add("음주", "quantity", "g", "22:00")
    items.add("영어공부", "boolean", None, "22:00")
    records.upsert("음주", "2026-04-13", value_num=10, raw_input="맥주")
    records.upsert("영어공부", "2026-03-25", value_bool=True,
                   raw_input="영어공부 함")

    advice = records.advice_after_record("음주", "2026-04-13")

    assert "영어공부는 최근 7일 실천 기록은 없지만" in advice
    assert "최근 30일에는 1번 했네" in advice
    assert "오늘 10분만 다시 이어보자" in advice


def test_advice_after_other_record_mentions_healthy_sleep_range(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    items.add("음주", "quantity", "g", "22:00")
    records.upsert("수면", "2026-04-11", value_num=450,
                   raw_input="7시간 30분")
    records.upsert("수면", "2026-04-12", value_num=480,
                   raw_input="8시간")
    records.upsert("음주", "2026-04-13", value_num=10,
                   raw_input="맥주")

    advice = records.advice_after_record("음주", "2026-04-13")

    assert "수면은 최근 7일 평균" in advice
    assert "적정 수면시간인 7~9시간 흐름을 계속 유지해보자" in advice


def test_advice_after_record_guides_short_sleep_toward_healthy_range(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    records.upsert("수면", "2026-04-12", value_num=330,
                   raw_input="5시간 30분")
    records.upsert("수면", "2026-04-13", value_num=360,
                   raw_input="6시간")

    advice = records.advice_after_record("수면", "2026-04-13")

    assert "적정 수면시간인 7~9시간에 가까워지도록" in advice
    assert "잠을 조금 더 확보해보자" in advice


def test_recent_returns_empty_for_unknown_item(setup):
    _, _, records = setup
    with pytest.raises(KeyError):
        records.recent("없음", days=7, ref_date="2026-04-13")


def test_find_recent_missing_prefers_latest_date_and_item_order(setup):
    """A newer missing response must win over older empty dates."""
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    items.add("영어공부", "boolean", None, "22:00")
    records.upsert("수면", "2026-08-29", value_num=420, raw_input="7시간")

    item, recorded_for = records.find_recent_missing("2026-08-30")

    assert recorded_for == "2026-08-29"
    assert item["name"] == "영어공부"


def test_find_recent_missing_excludes_reference_date_and_stops_after_seven_days(setup):
    """Today and dates older than seven days must not become follow-ups."""
    _, items, records = setup
    items.add("영어공부", "boolean", None, "22:00")
    for day in range(23, 30):
        records.upsert(
            "영어공부", f"2026-08-{day}", value_bool=False, raw_input="안 했어"
        )

    assert records.find_recent_missing("2026-08-30") is None


def test_find_recent_missing_treats_zero_as_recorded(setup):
    """A stored zero is an answer, not an empty record."""
    _, items, records = setup
    items.add("물", "quantity", "잔", "22:00")
    for day in range(23, 30):
        records.upsert("물", f"2026-08-{day}", value_num=0, raw_input="0잔")

    assert records.find_recent_missing("2026-08-30") is None
