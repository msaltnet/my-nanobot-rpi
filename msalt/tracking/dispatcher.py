"""디스패처: schedule 슬롯 도래 + pending 항목 retry를 batch로 텔레그램 발송."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from inspect import Parameter, signature
from typing import Literal
from zoneinfo import ZoneInfo

from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager

KST = ZoneInfo("Asia/Seoul")
WINDOW_MINUTES = 30
RECENT_HOURS = 24
GLOBAL_RETRY_SLOTS = ["09:00", "14:00", "20:00"]   # KST
UTC_TS_FORMAT = "%Y-%m-%d %H:%M:%S"
ReplyKeyboard = list[list[str]]


@dataclass
class DispatchMessage:
    kind: Literal["scheduled", "retry"]
    item_name: str
    recorded_for: str
    text: str   # 항목 단독 톤 텍스트 (batch 합치기 전 단계)
    reply_keyboard: ReplyKeyboard | None = None


@dataclass
class DispatchTarget:
    kind: Literal["scheduled", "retry"]
    item: dict
    recorded_for: str


def _parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _question_hint(item: dict) -> str:
    """schema별 짧은 힌트 — batch 라인에 들어감."""
    name = item["name"]
    schema = item["schema"]
    unit = item.get("unit") or ""
    if schema == "duration":
        return "몇 시간/얼마나?"
    if schema == "quantity":
        if name == "음주":
            return "무슨 술, 얼마나?"
        return f"몇 {unit}?" if unit else "얼마나?"
    if schema == "boolean":
        return "했어?"
    return "한 줄 메모"


def _solo_text(target: DispatchTarget) -> str:
    item = target.item
    name = item["name"]
    schema = item["schema"]
    unit = item.get("unit") or ""
    prefix = (
        f"⏰ '{name}' {target.recorded_for} 기록이 아직 비어 있어."
        if target.kind == "retry"
        else f"⏰ '{name}' 기록할 시간이야. 대상 날짜: {target.recorded_for}."
    )
    if schema == "duration":
        return f"{prefix} 얼마나 했는지 알려줘."
    if schema == "quantity":
        if name == "음주":
            return f"{prefix} 무슨 술을 얼마나 마셨는지 알려줘."
        return f"{prefix} 몇 {unit}인지 알려줘."
    if schema == "boolean":
        return f"{prefix} 했어?"
    return f"{prefix} 한 줄 메모 남겨줘."


def _format_batch(targets: list[DispatchTarget]) -> str:
    """단일 항목이면 솔로 톤, 복수면 번호 리스트."""
    if len(targets) == 1:
        return _solo_text(targets[0])
    lines = [f"📝 기록할 항목 {len(targets)}개:"]
    for i, target in enumerate(targets, 1):
        it = target.item
        lines.append(
            f"{i}. {it['name']} ({target.recorded_for} 기록) — {_question_hint(it)}"
        )
    return "\n".join(lines)


def _prefixed(item: dict, recorded_for: str, answer: str) -> str:
    return f"{item['name']} {recorded_for} {answer}"


def _rows(
    item: dict, recorded_for: str, answers: list[str], columns: int = 2
) -> ReplyKeyboard:
    buttons = [_prefixed(item, recorded_for, answer) for answer in answers]
    return [buttons[i:i + columns] for i in range(0, len(buttons), columns)]


def _reply_keyboard_for_item(item: dict, recorded_for: str) -> ReplyKeyboard:
    """항목 schema에 맞춰, 누르면 그대로 기록 의도가 되는 버튼을 만든다."""
    name = item["name"]
    schema = item["schema"]

    if schema == "duration":
        answers = (
            ["6시간", "7시간", "8시간", "9시간"]
            if name == "수면"
            else ["30분", "1시간", "2시간", "3시간"]
        )
        return _rows(item, recorded_for, answers)

    if schema == "quantity":
        if name == "음주":
            return [
                [_prefixed(item, recorded_for, "안 마심")],
                [
                    _prefixed(item, recorded_for, "맥주 1캔"),
                    _prefixed(item, recorded_for, "소주 1병"),
                ],
                [
                    _prefixed(item, recorded_for, "와인 1잔"),
                    _prefixed(item, recorded_for, "하이볼 1잔"),
                ],
            ]
        unit = item.get("unit") or ""
        return _rows(
            item, recorded_for, [f"0{unit}", f"1{unit}", f"2{unit}", f"3{unit}"]
        )

    if schema == "boolean":
        return [[
            _prefixed(item, recorded_for, "했어"),
            _prefixed(item, recorded_for, "안 했어"),
        ]]

    return []


def _reply_keyboard_for_items(targets: list[DispatchTarget]) -> ReplyKeyboard | None:
    rows: ReplyKeyboard = []
    for target in targets:
        rows.extend(_reply_keyboard_for_item(target.item, target.recorded_for))
    return rows or None


def build_missing_follow_up(
    item: dict, recorded_for: str
) -> tuple[str, ReplyKeyboard]:
    """Build the existing retry question and keyboard for one missing record."""
    target = DispatchTarget(kind="retry", item=item, recorded_for=recorded_for)
    return _solo_text(target), _reply_keyboard_for_item(item, recorded_for)


def _sender_accepts_reply_keyboard(send: Callable[..., None]) -> bool:
    """테스트/기존 호출부의 1-인자 sender와 새 2-인자 sender를 모두 지원한다."""
    try:
        sig = signature(send)
    except (TypeError, ValueError):
        return True
    params = list(sig.parameters.values())
    if any(p.kind == Parameter.VAR_POSITIONAL for p in params):
        return True
    positional = [
        p for p in params
        if p.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) >= 2


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


def _fallback_recorded_for_from_pending(pending_since_utc: str) -> str:
    pending_dt_utc = datetime.strptime(
        pending_since_utc, UTC_TS_FORMAT
    ).replace(tzinfo=timezone.utc)
    return pending_dt_utc.astimezone(KST).date().isoformat()


def _message_for(target: DispatchTarget) -> DispatchMessage:
    return DispatchMessage(
        kind=target.kind,
        item_name=target.item["name"],
        recorded_for=target.recorded_for,
        text=_solo_text(target),
        reply_keyboard=_reply_keyboard_for_item(
            target.item, target.recorded_for
        ) or None,
    )


class Dispatcher:
    def __init__(self, items: TrackedItemManager, records: RecordManager,
                 telegram_send: Callable[..., None]):
        self.items = items
        self.records = records
        self.send = telegram_send

    def _send_batch(self, text: str, reply_keyboard: ReplyKeyboard | None) -> None:
        if _sender_accepts_reply_keyboard(self.send):
            self.send(text, reply_keyboard)
        else:
            self.send(text)

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
        batch_targets: list[DispatchTarget] = []
        batch_messages: list[DispatchMessage] = []
        retry_slot_kst = _retry_slot_in_window(now_kst, window_start_kst)
        retry_slot_utc_str = (
            retry_slot_kst.astimezone(timezone.utc).strftime(UTC_TS_FORMAT)
            if retry_slot_kst else None
        )

        for it in all_items:
            # 1. record가 pending_since 이후로 들어왔으면 pending 클리어
            if it.get("pending_since"):
                pending_recorded_for = it.get("pending_recorded_for")
                has_pending_record = (
                    storage.record_exists(it["id"], pending_recorded_for)
                    if pending_recorded_for
                    else storage.has_record_since(it["id"], it["pending_since"])
                )
                if has_pending_record:
                    storage.clear_pending(it["id"])
                    it["pending_since"] = None
                    it["pending_recorded_for"] = None

            # 2. 다음 schedule_slot 도래 시 stale pending 폐기
            if it.get("pending_since"):
                next_slot_kst = _next_schedule_slot_after(it, it["pending_since"])
                if now_kst >= next_slot_kst:
                    storage.clear_pending(it["id"])
                    it["pending_since"] = None
                    it["pending_recorded_for"] = None

            # 3. 첫 알림 — schedule_time이 오늘의 (window_start, now] 윈도우 안
            h, m = _parse_hhmm(it["schedule_time"])
            slot_today_kst = now_kst.replace(hour=h, minute=m, second=0, microsecond=0)
            if window_start_kst < slot_today_kst <= now_kst:
                if not storage.has_record_since(it["id"], recent_since_utc):
                    target = DispatchTarget(
                        kind="scheduled",
                        item=it,
                        recorded_for=slot_today_kst.date().isoformat(),
                    )
                    batch_targets.append(target)
                    batch_messages.append(_message_for(target))
                continue

            # 4. retry — pending이고 글로벌 retry 슬롯이 윈도우 안
            if it.get("pending_since") and retry_slot_kst is not None:
                last_asked = it.get("last_asked_at")
                if last_asked is None or last_asked < retry_slot_utc_str:
                    target = DispatchTarget(
                        kind="retry",
                        item=it,
                        recorded_for=it.get("pending_recorded_for")
                        or _fallback_recorded_for_from_pending(it["pending_since"]),
                    )
                    batch_targets.append(target)
                    batch_messages.append(_message_for(target))

        # 5. 한 메시지로 묶어 발송
        if batch_targets:
            self._send_batch(
                _format_batch(batch_targets),
                _reply_keyboard_for_items(batch_targets),
            )
            for target in batch_targets:
                it = target.item
                if not it.get("pending_since"):
                    storage.set_pending_since(
                        it["id"], now_utc_str, target.recorded_for
                    )
                storage.set_last_asked_at(it["id"], now_utc_str)

        return batch_messages
