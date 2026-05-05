"""Record 관리: upsert, 조회, schema별 통계 포맷."""
from __future__ import annotations

import json
from typing import Any

from msalt.storage import Storage
from msalt.tracking.items import TrackedItemManager


def _format_minutes(total: float) -> str:
    """duration: 분(float) → '7시간 30분'."""
    minutes = int(round(total))
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}시간 {m}분"
    if h:
        return f"{h}시간"
    return f"{m}분"


def _format_quantity(value: float, unit: str) -> str:
    return f"{value:g}{unit}"


def _format_amount(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{value:g}"
    return str(value)


def _json_dumps(value: Any | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _format_drink_detail(record: dict) -> str | None:
    data = _json_loads(record.get("value_json"))
    if not data:
        return None
    drink_type = data.get("drink_type")
    amount = data.get("amount")
    unit = data.get("unit")
    if drink_type and amount is not None and unit:
        return f"{drink_type} {_format_amount(amount)}{unit}"
    return None


class RecordManager:
    def __init__(self, storage: Storage, items: TrackedItemManager):
        self.storage = storage
        self.items = items

    def _resolve(self, name: str) -> dict:
        item = self.items.get(name)
        if item is None:
            raise KeyError(f"unknown tracked item: {name}")
        return item

    def upsert(self, name: str, recorded_for: str, *,
               raw_input: str,
               value_text: str | None = None,
               value_num: float | None = None,
               value_bool: bool | None = None,
               value_json: Any | None = None) -> None:
        item = self._resolve(name)
        self.storage.upsert_record(
            item["id"], recorded_for,
            value_text=value_text, value_num=value_num,
            value_bool=value_bool, value_json=_json_dumps(value_json),
            raw_input=raw_input,
        )

    def recent(self, name: str, days: int, ref_date: str) -> list[dict]:
        item = self._resolve(name)
        return self.storage.get_records_for_item(
            item["id"], days=days, ref_date=ref_date
        )

    def summarize(self, name: str, days: int, ref_date: str) -> str:
        item = self._resolve(name)
        recs = self.storage.get_records_for_item(
            item["id"], days=days, ref_date=ref_date
        )
        if not recs:
            return f"{name}: 최근 {days}일 기록 없음"

        schema = item["schema"]
        n = len(recs)

        if schema == "duration":
            total = sum(r["value_num"] or 0 for r in recs)
            avg = total / n
            return (f"{name}: 최근 {days}일 {n}회 기록, "
                    f"평균 {_format_minutes(avg)} (총 {_format_minutes(total)})")

        if schema == "quantity":
            unit = item["unit"] or ""
            total = sum(r["value_num"] or 0 for r in recs)
            avg = total / n
            summary = (f"{name}: 최근 {days}일 {n}회 기록, "
                       f"합계 {_format_quantity(total, unit)}, "
                       f"평균 {_format_quantity(avg, unit)}")
            if name == "음주":
                details = []
                for r in recs[:3]:
                    detail = _format_drink_detail(r)
                    if detail:
                        details.append(f"{r['recorded_for']} {detail}")
                if details:
                    summary += f" ({', '.join(details)})"
            return summary

        if schema == "boolean":
            done = sum(1 for r in recs if r["value_bool"])
            pct = done * 100 // n
            return f"{name}: 최근 {days}일 {done}/{n}회 수행 ({pct}%)"

        # freetext
        lines = [f"{name}: 최근 {days}일 {n}건"]
        for r in recs[:5]:
            lines.append(f"  {r['recorded_for']}: {r['value_text'] or r['raw_input']}")
        return "\n".join(lines)
