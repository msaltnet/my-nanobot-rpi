from datetime import datetime, time
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import pytest

from msalt.storage import Storage
from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager
from msalt.tracking.dispatcher import Dispatcher, DispatchMessage


KST = ZoneInfo("Asia/Seoul")


@pytest.fixture
def setup(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    items = TrackedItemManager(s)
    records = RecordManager(s, items)
    return s, items, records


def test_no_items_no_messages(setup):
    _, items, records = setup
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 8, 0, tzinfo=KST))
    assert msgs == []


def test_scheduled_item_within_window_triggers_question(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 8, 5, tzinfo=KST))
    assert len(msgs) == 1
    assert msgs[0].kind == "scheduled"
    assert msgs[0].item_name == "수면"


def test_outside_window_no_scheduled_message(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 7, 30, tzinfo=KST))
    # 7:30 → 다음 슬롯은 7:30, 윈도우는 [7:30, 8:00). 8:00은 미포함.
    assert all(m.item_name != "수면" for m in msgs if m.kind == "scheduled")


def test_missed_item_after_schedule_triggers_alert(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 12, 0, tzinfo=KST))
    assert len(msgs) == 1
    assert msgs[0].kind == "missed"
    assert msgs[0].item_name == "수면"


def test_recorded_item_no_missed_alert(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    records.upsert("수면", "2026-04-14", value_num=480, raw_input="8h")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 12, 0, tzinfo=KST))
    assert msgs == []


def test_overnight_recorded_for_yesterday_skips_missed(setup):
    """오버나잇 항목(수면 08:00)을 오늘 아침에 어제 날짜로 기록해도
    오늘의 미기록 알림은 더 이상 뜨지 않아야 한다 (최근 24h 내 입력)."""
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    # 어제 날짜로 기록 (recorded_at은 자동으로 지금 시각 = 2026-04-14 근방)
    records.upsert("수면", "2026-04-13", value_num=480, raw_input="8h")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 12, 0, tzinfo=KST))
    assert msgs == []


def test_scheduled_takes_priority_over_missed(setup):
    """같은 회차에 scheduled로 잡히면 missed에서 제외."""
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 8, 15, tzinfo=KST))
    kinds = {m.kind for m in msgs if m.item_name == "수면"}
    assert kinds == {"scheduled"}


def test_missed_alert_sent_only_once_per_day(setup):
    """같은 날 두 번 tick해도 missed 알림은 1회만."""
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    msgs1 = d.run(now=datetime(2026, 4, 14, 12, 0, tzinfo=KST))
    msgs2 = d.run(now=datetime(2026, 4, 14, 14, 30, tzinfo=KST))
    assert len(msgs1) == 1 and msgs1[0].kind == "missed"
    assert msgs2 == []
    assert send.call_count == 1


def test_missed_alert_resets_next_day(setup):
    """다음 날 슬롯이 다시 도래하면 missed 알림이 다시 발송된다."""
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    d.run(now=datetime(2026, 4, 14, 12, 0, tzinfo=KST))
    msgs_next_day = d.run(now=datetime(2026, 4, 15, 12, 0, tzinfo=KST))
    assert len(msgs_next_day) == 1
    assert msgs_next_day[0].kind == "missed"


def test_run_calls_telegram_send_for_each_message(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    items.add("음주", "quantity", "잔", "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=datetime(2026, 4, 14, 23, 0, tzinfo=KST))
    # 22:00 이후이므로 음주는 missed
    assert send.call_count >= 1
