"""LLM 기반 자연어 파서: 기록 입력 / 항목 추가 의도."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedRecord:
    item_name: str | None
    recorded_for: str
    value_text: str | None
    value_num: float | None
    value_bool: bool | None
    confidence: float


@dataclass
class ParsedItemIntent:
    name: str
    schema: str  # 'freetext'|'duration'|'quantity'|'boolean'
    unit: str | None
    schedule_time: str  # 'HH:MM'


_RECORD_SYSTEM = """\
사용자가 일상 기록(수면·음주·운동 등)을 자연어로 입력했다.
주어진 known_items 중 하나에 매칭되는지 판단하고, 해당하는 시점·값을 추출하라.
응답은 반드시 다음 JSON 한 줄만 출력:
{"item_name": str|null, "recorded_for": "YYYY-MM-DD", "value_text": str|null,
 "value_num": number|null, "value_bool": bool|null, "confidence": 0~1}

규칙:
- "어제"/"지난주 화요일" 등 상대 시점은 now 기준으로 절대 날짜 변환.
- duration schema → value_num은 분 단위 정수.
- quantity schema → value_num은 숫자, 단위는 item의 unit 사용.
- boolean schema → value_bool.
- freetext schema → value_text에 원문 핵심.
- 매칭 없거나 모호하면 item_name=null, confidence=0.
"""

_ITEM_INTENT_SYSTEM = """\
사용자가 새로 추적할 항목을 자연어로 제안했다.
다음 JSON 한 줄만 출력:
{"name": str, "schema": "freetext"|"duration"|"quantity"|"boolean",
 "unit": str|null, "schedule_time": "HH:MM"}

규칙:
- name은 한국어 짧은 명사 (예: "독서", "물 섭취").
- 시간을 측정 → duration. 횟수·양 → quantity (unit 필수, 예: "잔", "회").
- 했음/안함만 → boolean. 자유 메모 → freetext.
- schedule_time은 사용자 의도 기반 24시간 HH:MM (아침=08:00, 자기 전=22:00 등).
"""


class NaturalLanguageParser:
    def __init__(self, client: Any, model: str):
        self.client = client
        self.model = model

    def _chat(self, system: str, user: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content or ""

    def parse_record(self, text: str, known_items: list[dict],
                     now: str) -> ParsedRecord:
        items_view = [
            {"name": i["name"], "schema": i["schema"], "unit": i.get("unit")}
            for i in known_items
        ]
        user = json.dumps({
            "now": now,
            "known_items": items_view,
            "input": text,
        }, ensure_ascii=False)
        raw = self._chat(_RECORD_SYSTEM, user)
        try:
            data = json.loads(raw)
            return ParsedRecord(
                item_name=data.get("item_name"),
                recorded_for=data.get("recorded_for") or now[:10],
                value_text=data.get("value_text"),
                value_num=data.get("value_num"),
                value_bool=data.get("value_bool"),
                confidence=float(data.get("confidence", 0)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return ParsedRecord(
                item_name=None, recorded_for=now[:10],
                value_text=None, value_num=None, value_bool=None,
                confidence=0.0,
            )

    def parse_item_intent(self, text: str) -> ParsedItemIntent:
        raw = self._chat(_ITEM_INTENT_SYSTEM, text)
        try:
            data = json.loads(raw)
            return ParsedItemIntent(
                name=data["name"],
                schema=data["schema"],
                unit=data.get("unit"),
                schedule_time=data["schedule_time"],
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise ValueError(f"failed to parse item intent: {raw!r}") from e
