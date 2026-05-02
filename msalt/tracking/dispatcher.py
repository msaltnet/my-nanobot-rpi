"""디스패처: 시각 도래 / 누락 항목 검출 후 batch로 텔레그램 발송."""
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
GLOBAL_RETRY_SLOTS = ["09:00", "14:00", "20:00"]   # KST
UTC_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class DispatchMessage:
    kind: Literal["scheduled", "retry"]
    item_name: str
    text: str   # 항목 단독 톤 텍스트 (batch 합치기 전 단계)


def _parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _question_hint(item: dict) -> str:
    """schema별 짧은 힌트 — batch 라인에 들어감."""
    schema = item["schema"]
    unit = item.get("unit") or ""
    if schema == "duration":
        return "몇 시간/얼마나?"
    if schema == "quantity":
        return f"몇 {unit}?" if unit else "얼마나?"
    if schema == "boolean":
        return "했어?"
    return "한 줄 메모"


def _solo_text(item: dict) -> str:
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


def _format_batch(items: list[dict]) -> str:
    """단일 항목이면 솔로 톤, 복수면 번호 리스트."""
    if len(items) == 1:
        return _solo_text(items[0])
    lines = [f"📝 기록할 항목 {len(items)}개:"]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {it['name']} — {_question_hint(it)}")
    return "\n".join(lines)


def _next_schedule_slot_after(item: dict, after_utc: str) -> datetime:
    """item.schedule_time(KST)이 after_utc 시각보다 미래의 가장 가까운 KST datetime을 반환."""
    h, m = _parse_hhmm(item["schedule_time"])
    after_dt_utc = datetime.strptime(after_utc, UTC_TS_FORMAT).replace(tzinfo=timezone.utc)
    after_dt_kst = after_dt_utc.astimezone(KST)
    # 같은 날 슬롯
    candidate = after_dt_kst.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= after_dt_kst:
        candidate = candidate + timedelta(days=1)
    return candidate


def _retry_slot_in_window(now_kst: datetime, window_start_kst: datetime) -> datetime | None:
    """now_kst의 (window_start, now_kst] 윈도우 안에 들어오는 GLOBAL_RETRY_SLOTS 슬롯 KST datetime."""
    for hhmm in GLOBAL_RETRY_SLOTS:
        h, m = _parse_hhmm(hhmm)
        slot = now_kst.replace(hour=h, minute=m, second=0, microsecond=0)
        if window_start_kst < slot <= now_kst:
            return slot
    return None


class Dispatcher:
    def __init__(self, items: TrackedItemManager, records: RecordManager,
                 telegram_send: Callable[[str], None]):
        self.items = items
        self.records = records
        self.send = telegram_send

    def run(self, now: datetime) -> list[DispatchMessage]:
        if now.tzinfo is None:
            now = now.replace(tzinfo=KST)
        now_kst = now.astimezone(KST)
        now_utc = now.astimezone(timezone.utc)
        now_utc_str = now_utc.strftime(UTC_TS_FORMAT)

        all_items = self.items.list_all()
        if not all_items:
            return []

        window_start_kst = now_kst - timedelta(minutes=WINDOW_MINUTES)
        recent_since_utc = (
            now_utc - timedelta(hours=RECENT_HOURS)
        ).strftime(UTC_TS_FORMAT)

        storage = self.records.storage
        batch_items: list[dict] = []
        batch_messages: list[DispatchMessage] = []
        retry_slot_kst = _retry_slot_in_window(now_kst, window_start_kst)
        retry_slot_utc_str = (
            retry_slot_kst.astimezone(timezone.utc).strftime(UTC_TS_FORMAT)
            if retry_slot_kst else None
        )

        for it in all_items:
            # 1. record가 pending_since 이후로 들어왔으면 pending 클리어
            if it.get("pending_since"):
                if storage.has_record_since(it["id"], it["pending_since"]):
                    storage.clear_pending(it["id"])
                    it["pending_since"] = None

            # 2. 다음 schedule_slot 도래 시 stale pending 폐기
            if it.get("pending_since"):
                next_slot_kst = _next_schedule_slot_after(it, it["pending_since"])
                if now_kst >= next_slot_kst:
                    storage.clear_pending(it["id"])
                    it["pending_since"] = None

            # 3. 첫 알림 — schedule_time이 오늘의 [window_start, now] 윈도우 안
            h, m = _parse_hhmm(it["schedule_time"])
            slot_today_kst = now_kst.replace(hour=h, minute=m, second=0, microsecond=0)
            if window_start_kst < slot_today_kst <= now_kst:
                if not storage.has_record_since(it["id"], recent_since_utc):
                    batch_items.append(it)
                    batch_messages.append(DispatchMessage(
                        kind="scheduled", item_name=it["name"],
                        text=_solo_text(it),
                    ))
                continue

            # 4. retry — pending이고 글로벌 retry 슬롯이 윈도우 안
            if it.get("pending_since") and retry_slot_kst is not None:
                last_asked = it.get("last_asked_at")
                if last_asked is None or last_asked < retry_slot_utc_str:
                    batch_items.append(it)
                    batch_messages.append(DispatchMessage(
                        kind="retry", item_name=it["name"],
                        text=_solo_text(it),
                    ))

        # 5. 한 메시지로 묶어 발송
        if batch_items:
            self.send(_format_batch(batch_items))
            for it in batch_items:
                if not it.get("pending_since"):
                    storage.set_pending_since(it["id"], now_utc_str)
                storage.set_last_asked_at(it["id"], now_utc_str)

        return batch_messages
