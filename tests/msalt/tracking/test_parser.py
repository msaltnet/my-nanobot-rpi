import json
from unittest.mock import MagicMock
import pytest

from msalt.tracking.parser import (
    NaturalLanguageParser, ParsedRecord, ParsedItemIntent,
)


def _mock_client_with(content: str) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    client.chat.completions.create.return_value = response
    return client


def test_parse_record_extracts_fields():
    payload = {
        "item_name": "수면",
        "recorded_for": "2026-04-13",
        "value_num": 480,
        "value_text": None,
        "value_bool": None,
        "confidence": 0.9,
    }
    client = _mock_client_with(json.dumps(payload))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_record(
        "어제 11시에 자서 7시에 일어났어",
        known_items=[{"name": "수면", "schema": "duration", "unit": None}],
        now="2026-04-14T08:30:00+09:00",
    )
    assert isinstance(result, ParsedRecord)
    assert result.item_name == "수면"
    assert result.recorded_for == "2026-04-13"
    assert result.value_num == 480
    assert result.confidence == 0.9


def test_parse_record_returns_none_when_no_match():
    payload = {"item_name": None, "recorded_for": "2026-04-14",
               "value_num": None, "value_text": None,
               "value_bool": None, "confidence": 0.0}
    client = _mock_client_with(json.dumps(payload))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_record(
        "오늘 날씨 좋다",
        known_items=[{"name": "수면", "schema": "duration", "unit": None}],
        now="2026-04-14T08:30:00+09:00",
    )
    assert result.item_name is None


def test_parse_record_handles_invalid_json_gracefully():
    client = _mock_client_with("not json at all")
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_record(
        "x", known_items=[], now="2026-04-14T08:30:00+09:00"
    )
    assert result.item_name is None
    assert result.confidence == 0.0


def test_parse_item_intent_extracts_fields():
    payload = {
        "name": "독서",
        "schema": "duration",
        "unit": None,
        "schedule_time": "22:00",
    }
    client = _mock_client_with(json.dumps(payload))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_item_intent(
        "독서 시간도 매일 자기 전에 기록할래"
    )
    assert isinstance(result, ParsedItemIntent)
    assert result.name == "독서"
    assert result.schema == "duration"
    assert result.schedule_time == "22:00"


def test_parse_item_intent_quantity_with_unit():
    payload = {"name": "물", "schema": "quantity", "unit": "잔",
               "schedule_time": "22:00"}
    client = _mock_client_with(json.dumps(payload))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_item_intent("매일 물 몇 잔 마셨는지")
    assert result.unit == "잔"


def test_parse_item_intent_invalid_json():
    client = _mock_client_with("garbage")
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    with pytest.raises(ValueError):
        parser.parse_item_intent("x")
