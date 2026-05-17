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


def _topic_particle(text: str) -> str:
    if not text:
        return "은"
    code = ord(text[-1])
    if not (0xAC00 <= code <= 0xD7A3):
        return "은"
    return "은" if (code - 0xAC00) % 28 else "는"


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

    def advice_after_record(self, recorded_name: str, ref_date: str,
                            days: int = 7, max_lines: int = 3) -> str:
        """기록 직후 보여줄 짧은 생활 패턴 코멘트."""
        advice: list[tuple[int, str]] = []
        for item in self.items.list_all():
            name = item["name"]
            schema = item["schema"]
            week_recs = self.storage.get_records_for_item(
                item["id"], days=days, ref_date=ref_date
            )
            month_recs = self.storage.get_records_for_item(
                item["id"], days=30, ref_date=ref_date
            )

            if name == "음주" and schema == "quantity":
                week_drinking_days = sum(
                    1 for r in week_recs if (r.get("value_num") or 0) > 0
                )
                month_drinking_days = sum(
                    1 for r in month_recs if (r.get("value_num") or 0) > 0
                )
                if week_drinking_days >= 3 or month_drinking_days >= 8:
                    advice.append((
                        10 if name == recorded_name else 30,
                        f"기록을 보니 최근 {days}일 음주 {week_drinking_days}일, "
                        f"최근 30일 음주 {month_drinking_days}일이네. "
                        "이번 주는 횟수와 양을 조금 줄이는 방향으로 가보자.",
                    ))
                elif (
                    name == recorded_name
                    and week_recs
                    and (week_recs[0].get("value_num") or 0) == 0
                ):
                    advice.append((
                        40,
                        "오늘 안 마신 기록 좋네. 이 흐름으로 음주량을 줄여가보자.",
                    ))
                continue

            if schema == "boolean":
                week_done = sum(1 for r in week_recs if r.get("value_bool"))
                month_done = sum(1 for r in month_recs if r.get("value_bool"))
                if week_done == 0:
                    topic = _topic_particle(name)
                    if month_done:
                        text = (
                            f"{name}{topic} 최근 {days}일 실천 기록은 없지만, "
                            f"최근 30일에는 {month_done}번 했네. "
                            "끊긴 흐름을 오늘 10분만 다시 이어보자."
                        )
                    else:
                        text = (
                            f"{name}{topic} 최근 {days}일과 최근 30일 모두 실천 기록이 없네. "
                            "부담 없이 10분만 다시 시작해보자."
                        )
                    advice.append((20 if name != recorded_name else 50, text))
                elif name == recorded_name:
                    advice.append((
                        45,
                        f"{name}{_topic_particle(name)} 최근 {days}일 {week_done}번, "
                        f"최근 30일 {month_done}번 했네. "
                        "좋아, 이 흐름을 짧게라도 계속 이어가보자.",
                    ))
                continue

            if schema == "duration" and week_recs:
                avg = sum(r.get("value_num") or 0 for r in week_recs) / len(week_recs)
                month_avg = None
                if month_recs:
                    month_avg = sum(r.get("value_num") or 0 for r in month_recs) / len(month_recs)
                month_part = (
                    f", 최근 30일 평균 {_format_minutes(month_avg)}"
                    if month_avg is not None else ""
                )
                if name == "수면" and avg < 420:
                    advice.append((
                        25,
                        f"수면은 최근 {days}일 평균 {_format_minutes(avg)}{month_part} 정도야. "
                        "적정 수면시간인 7~9시간에 가까워지도록 오늘은 잠을 조금 더 확보해보자.",
                    ))
                elif name == "수면" and avg <= 540:
                    advice.append((
                        60 if name == recorded_name else 35,
                        f"수면은 최근 {days}일 평균 {_format_minutes(avg)}{month_part} 정도야. "
                        "좋아, 적정 수면시간인 7~9시간 흐름을 계속 유지해보자.",
                    ))
                elif avg < 360:
                    advice.append((
                        25,
                        f"{name} 평균이 최근 {days}일 기준 {_format_minutes(avg)}{month_part} 정도야. "
                        "오늘은 회복 시간을 조금 더 확보해보자.",
                    ))
                elif avg > 540:
                    advice.append((
                        25,
                        f"{name} 평균이 최근 {days}일 기준 {_format_minutes(avg)}{month_part} 정도야. "
                        "컨디션이 무겁진 않은지도 같이 봐보자.",
                    ))

        if not advice:
            return (
                f"최근 {days}일과 최근 30일 기록도 같이 보고 있어. "
                "조금 더 쌓이면 패턴을 더 또렷하게 짚어줄게."
            )

        advice.sort(key=lambda x: x[0])
        return "\n".join(line for _, line in advice[:max_lines])
