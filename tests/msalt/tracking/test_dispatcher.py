from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import pytest

from msalt.storage import Storage
from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager
from msalt.tracking.dispatcher import Dispatcher


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


# --- 기본 동작 ---


def test_no_items_no_messages(setup):
    _, items, records = setup
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=_kst(2026, 5, 2, 9, 0))
    assert msgs == []


def test_first_alert_when_schedule_slot_in_window(setup):
    """schedule_time이 [now-30, now] 윈도우에 들어오면 첫 알림 발송 + pending_since 세팅."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    msgs = d.run(now=_kst(2026, 5, 1, 22, 5))
    assert len(msgs) == 1
    assert msgs[0].item_name == "수면"
    assert send.call_count == 1
    item = s.get_tracked_item_by_name("수면")
    assert item["pending_since"] is not None
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


def test_batch_includes_first_alert_and_retry_in_same_tick(setup):
    """09:00에 첫 알림인 항목 + 09:00 retry 슬롯에 걸린 미답 항목이 한 메시지로 묶임."""
    s, items, records = setup
    items.add("아침메모", "freetext", None, "09:00")
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # 수면 첫 알림 → pending 세팅
    msgs = d.run(now=_kst(2026, 5, 2, 9, 5))
    # 아침메모는 첫 알림, 수면은 retry. 한 메시지에 둘 다 들어가야 함
    assert send.call_count == 2   # day1 첫 알림 + day2 batch
    sent_text = send.call_args.args[0]
    assert "아침메모" in sent_text
    assert "수면" in sent_text


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
