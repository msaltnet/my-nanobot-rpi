from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from msalt.storage import Storage
from msalt.tracking.dispatcher import Dispatcher, build_missing_follow_up
from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager

KST = ZoneInfo("Asia/Seoul")


@pytest.fixture
def setup(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    items = TrackedItemManager(s)
    records = RecordManager(s, items)
    return s, items, records


def _kst(y, m, d, h, mi):
    return datetime(y, m, d, h, mi, tzinfo=KST)


def test_build_missing_follow_up_uses_boolean_question_and_keyboard():
    """A boolean follow-up must offer date-qualified yes/no answers."""
    item = {"name": "영어공부", "schema": "boolean", "unit": None}

    question, keyboard = build_missing_follow_up(item, "2026-08-29")

    assert "영어공부" in question
    assert "2026-08-29" in question
    assert "비어 있어" in question
    assert keyboard == [[
        "영어공부 2026-08-29 했어",
        "영어공부 2026-08-29 안 했어",
    ]]


# --- 기본 동작 ---


def test_no_items_no_messages(setup):
    _, items, records = setup
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=_kst(2026, 5, 2, 9, 0))
    assert msgs == []


def test_first_alert_when_schedule_slot_in_window(setup):
    """schedule_time이 [now-30, now] 윈도우에 들어오면 대상 날짜를 명시하고 pending을 세팅한다."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    msgs = d.run(now=_kst(2026, 5, 1, 22, 5))
    assert len(msgs) == 1
    assert msgs[0].item_name == "수면"
    assert msgs[0].recorded_for == "2026-05-01"
    assert "2026-05-01" in msgs[0].text
    assert "2026-05-01" in send.call_args.args[0]
    assert send.call_count == 1
    item = s.get_tracked_item_by_name("수면")
    assert item["pending_since"] is not None
    assert item["pending_recorded_for"] == "2026-05-01"
    assert item["last_asked_at"] is not None


def test_no_double_fire_at_plus_30(setup):
    """첫 알림 30분 뒤에는 schedule_slot이 윈도우 밖 → 추가 알림 없음 (현행 +30 noise 제거)."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # 첫 알림
    msgs2 = d.run(now=_kst(2026, 5, 1, 22, 35))   # +30
    assert msgs2 == []
    assert send.call_count == 1


def test_record_arrived_clears_pending(setup):
    """첫 알림 후 사용자가 record를 입력하면 다음 tick에서 pending이 클리어된다."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))
    records.upsert("수면", "2026-05-01", value_num=480, raw_input="8h")
    # 다음날 09:00 retry 슬롯 → record가 있으니 fire 안 함
    msgs = d.run(now=_kst(2026, 5, 2, 9, 5))
    assert msgs == []
    item = s.get_tracked_item_by_name("수면")
    assert item["pending_since"] is None
    assert item["pending_recorded_for"] is None


def test_record_for_other_date_does_not_clear_pending(setup):
    """대상 날짜가 아닌 기록은 pending을 지우지 않아야 재질문 대상이 흐려지지 않는다."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))
    records.upsert("수면", "2026-05-02", value_num=480, raw_input="다른 날짜")
    msgs = d.run(now=_kst(2026, 5, 2, 9, 5))
    assert len(msgs) == 1
    assert msgs[0].kind == "retry"
    assert msgs[0].recorded_for == "2026-05-01"
    item = s.get_tracked_item_by_name("수면")
    assert item["pending_recorded_for"] == "2026-05-01"


# --- retry chain ---


def test_retry_at_09_when_pending(setup):
    """첫 알림 후 답이 없으면 다음날 09:00 retry 슬롯에서 재질문."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # 첫 알림
    msgs = d.run(now=_kst(2026, 5, 2, 9, 5))
    assert len(msgs) == 1
    assert msgs[0].item_name == "수면"
    assert msgs[0].recorded_for == "2026-05-01"
    assert "2026-05-01" in msgs[0].text
    assert "2026-05-01" in send.call_args.args[0]
    assert send.call_count == 2


def test_retry_chain_09_14_20(setup):
    """답이 없으면 09 → 14 → 20 모두 retry."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # 첫 알림
    d.run(now=_kst(2026, 5, 2, 9, 5))
    d.run(now=_kst(2026, 5, 2, 14, 5))
    d.run(now=_kst(2026, 5, 2, 20, 5))
    assert send.call_count == 4


def test_retry_does_not_fire_without_pending(setup):
    """pending_since가 없으면 retry 슬롯에서도 fire 안 함."""
    _, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    msgs = d.run(now=_kst(2026, 5, 1, 9, 5))   # 22:00 슬롯 도래 전
    assert msgs == []
    assert send.call_count == 0


def test_retry_slot_no_double_fire_in_same_window(setup):
    """같은 retry 슬롯 윈도우에서 두 번 tick해도 한 번만 fire."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # 첫 알림
    d.run(now=_kst(2026, 5, 2, 9, 5))    # retry 1
    msgs = d.run(now=_kst(2026, 5, 2, 9, 25))   # 같은 09:00 슬롯, 다른 tick
    assert msgs == []
    assert send.call_count == 2


def test_next_schedule_slot_clears_stale_pending(setup):
    """다음날 22:00 schedule_slot 도달 시 어제 pending은 폐기되고 새 알림이 fire된다."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # day1 첫 알림
    msgs = d.run(now=_kst(2026, 5, 2, 22, 5))   # day2 첫 알림 (day1 pending은 폐기)
    assert len(msgs) == 1
    item = s.get_tracked_item_by_name("수면")
    # pending_since는 day2 알림 시각
    assert item["pending_since"] is not None
    assert item["pending_recorded_for"] == "2026-05-02"
    # day2 첫 알림이 day1 알림(13:00 UTC) 이후
    assert item["pending_since"] > "2026-05-01 13:00:00"


# --- batch ---


def test_multiple_items_batched_into_one_message(setup):
    """같은 tick에 두 항목이 fire되면 한 메시지로 묶임."""
    _, items, records = setup
    items.add("수면", "duration", None, "22:00")
    items.add("음주", "quantity", "잔", "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    msgs = d.run(now=_kst(2026, 5, 1, 22, 5))
    assert len(msgs) == 2   # DispatchMessage 자체는 항목별로 2개
    assert send.call_count == 1   # 그러나 텔레그램 send는 1번
    sent_text = send.call_args.args[0]
    assert "수면" in sent_text
    assert "음주" in sent_text
    assert "2026-05-01" in sent_text


def test_single_item_uses_solo_format(setup):
    """단일 항목은 기존 솔로 포맷 (번호 리스트 아님)."""
    _, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))
    sent_text = send.call_args.args[0]
    assert "기록할 항목" not in sent_text   # batch 헤더 아님
    assert "수면" in sent_text


def test_single_item_sends_schema_keyboard(setup):
    """단일 항목도 schema에 맞는 reply keyboard를 함께 보낸다."""
    _, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    msgs = d.run(now=_kst(2026, 5, 1, 22, 5))
    keyboard = send.call_args.args[1]
    assert ["수면 2026-05-01 6시간", "수면 2026-05-01 7시간"] in keyboard
    assert ["수면 2026-05-01 8시간", "수면 2026-05-01 9시간"] in keyboard
    assert msgs[0].reply_keyboard == keyboard


def test_batch_keyboard_includes_item_names(setup):
    """묶음 알림 버튼은 누른 텍스트만으로도 항목과 대상 날짜를 매칭할 수 있어야 한다."""
    _, items, records = setup
    items.add("수면", "duration", None, "22:00")
    items.add("음주", "quantity", "g", "22:00")
    items.add("영어공부", "boolean", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))
    keyboard = send.call_args.args[1]
    flat = [button for row in keyboard for button in row]
    assert "수면 2026-05-01 7시간" in flat
    assert "음주 2026-05-01 안 마심" in flat
    assert "음주 2026-05-01 맥주 1캔" in flat
    assert "영어공부 2026-05-01 했어" in flat
    assert "영어공부 2026-05-01 안 했어" in flat


def test_batch_includes_first_alert_and_retry_in_same_tick(setup):
    """09:00에 첫 알림인 항목 + 09:00 retry 슬롯에 걸린 미답 항목이 한 메시지로 묶임."""
    s, items, records = setup
    items.add("아침메모", "freetext", None, "09:00")
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # 수면 첫 알림 → pending 세팅
    d.run(now=_kst(2026, 5, 2, 9, 5))
    # 아침메모는 첫 알림, 수면은 retry. 한 메시지에 둘 다 들어가야 함
    assert send.call_count == 2   # day1 첫 알림 + day2 batch
    sent_text = send.call_args.args[0]
    assert "아침메모 (2026-05-02 기록)" in sent_text
    assert "수면 (2026-05-01 기록)" in sent_text


# --- 24h 내 record 있으면 첫 알림 skip ---


def test_first_alert_skipped_if_recent_record(setup):
    """schedule_slot 도래해도 24시간 내 record가 있으면 첫 알림 skip."""
    _, items, records = setup
    items.add("수면", "duration", None, "22:00")
    records.upsert("수면", "2026-05-01", value_num=480, raw_input="이미 입력")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    msgs = d.run(now=_kst(2026, 5, 1, 22, 5))
    assert msgs == []
    assert send.call_count == 0
