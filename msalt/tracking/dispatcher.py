"""디스패처: 시각 도래 / 누락 항목 검출 후 Telegram 메시지 발송."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal
from zoneinfo import ZoneInfo

from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager


KST = ZoneInfo("Asia/Seoul")
WINDOW_MINUTES = 30
RECENT_HOURS = 24


@dataclass
class DispatchMessage:
    kind: Literal["scheduled", "missed"]
    item_name: str
    text: str


def _parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _question_text(item: dict) -> str:
    name = item["name"]
    schema = item["schema"]
    unit = item.get("unit") or ""
    if schema == "duration":
        return f"⏰ '{name}' 기록할 시간이야. 얼마나 했는지 알려줘."
    if schema == "quantity":
        return f"⏰ '{name}' 기록할 시간이야. 몇 {unit}인지 알려줘."
    if schema == "boolean":
        return f"⏰ '{name}' 했어?"
    return f"⏰ '{name}' 한 줄 메모 남겨줘."


def _missed_text(item: dict, recorded_for: str) -> str:
    return f"📝 {recorded_for} '{item['name']}' 기록이 비어있어. 지금 입력할래?"


class Dispatcher:
    def __init__(self, items: TrackedItemManager, records: RecordManager,
                 telegram_send: Callable[[str], None]):
        self.items = items
        self.records = records
        self.send = telegram_send

    def run(self, now: datetime) -> list[DispatchMessage]:
        if now.tzinfo is None:
            now = now.replace(tzinfo=KST)
        else:
            now = now.astimezone(KST)

        all_items = self.items.list_all()
        if not all_items:
            return []

        # 윈도우: [now - WINDOW, now]
        window_start = now - timedelta(minutes=WINDOW_MINUTES)
        today_str = now.date().isoformat()
        # recorded_at은 sqlite datetime('now') = UTC. 24h 이전 시점도 UTC ISO로.
        recent_since_utc = (
            now.astimezone(timezone.utc) - timedelta(hours=RECENT_HOURS)
        ).strftime("%Y-%m-%d %H:%M:%S")

        scheduled: list[DispatchMessage] = []
        scheduled_names: set[str] = set()
        for it in all_items:
            h, m = _parse_hhmm(it["schedule_time"])
            slot_today = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if window_start < slot_today <= now:
                scheduled.append(DispatchMessage(
                    kind="scheduled", item_name=it["name"],
                    text=_question_text(it),
                ))
                scheduled_names.add(it["name"])

        missed: list[DispatchMessage] = []
        for it in all_items:
            if it["name"] in scheduled_names:
                continue
            h, m = _parse_hhmm(it["schedule_time"])
            slot_today = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if slot_today > now:
                continue  # 오늘 슬롯이 아직 안 옴
            if self.records.storage.has_record_since(it["id"], recent_since_utc):
                continue
            missed.append(DispatchMessage(
                kind="missed", item_name=it["name"],
                text=_missed_text(it, today_str),
            ))

        messages = scheduled + missed
        for msg in messages:
            self.send(msg.text)
        return messages
