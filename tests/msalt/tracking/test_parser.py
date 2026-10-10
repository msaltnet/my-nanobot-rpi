import json
from unittest.mock import MagicMock

import pytest

from msalt.tracking.parser import (
    NaturalLanguageParser,
    ParsedItemIntent,
    ParsedRecord,
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
        "value_json": None,
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
               "value_bool": None, "value_json": None, "confidence": 0.0}
    client = _mock_client_with(json.dumps(payload))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_record(
        "오늘 날씨 좋다",
        known_items=[{"name": "수면", "schema": "duration", "unit": None}],
        now="2026-04-14T08:30:00+09:00",
    )
    assert result.item_name is None


def test_parse_drinking_record_keeps_alcohol_detail():
    payload = {
        "item_name": "음주",
        "recorded_for": "2026-04-13",
        "value_num": 48.3,
        "value_text": None,
        "value_bool": None,
        "value_json": {
            "drink_type": "소주",
            "amount": 1,
            "unit": "병",
            "serving_ml": 360,
            "abv_percent": 17,
            "alcohol_g": 48.3,
        },
        "confidence": 0.92,
    }
    client = _mock_client_with(json.dumps(payload, ensure_ascii=False))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_record(
        "어제 소주 1병 마셨어",
        known_items=[{"name": "음주", "schema": "quantity", "unit": "g"}],
        now="2026-04-14T08:30:00+09:00",
    )
    assert result.item_name == "음주"
    assert result.value_num == 48.3
    assert result.value_json == payload["value_json"]


def test_parse_record_sends_alcohol_profiles_to_llm():
    payload = {
        "item_name": "음주",
        "recorded_for": "2026-04-13",
        "value_num": 19.7,
        "value_text": None,
        "value_bool": None,
        "value_json": {
            "drink_type": "맥주",
            "amount": 1,
            "unit": "캔",
            "serving_ml": 500,
            "abv_percent": 5,
            "alcohol_g": 19.7,
        },
        "confidence": 0.9,
    }
    client = _mock_client_with(json.dumps(payload, ensure_ascii=False))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    parser.parse_record(
        "맥주 1캔",
        known_items=[{"name": "음주", "schema": "quantity", "unit": "g"}],
        now="2026-04-14T08:30:00+09:00",
    )
    user_payload = json.loads(
        client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    )
    beer = next(
        p for p in user_payload["alcohol_profiles"]
        if p["drink_type"] == "맥주"
    )
    assert beer["unit"] == "캔"
    assert beer["serving_ml"] == 500
    assert beer["abv_percent"] == 5


def test_parse_record_system_prompt_prioritizes_explicit_date():
    client = _mock_client_with(json.dumps({
        "item_name": "수면",
        "recorded_for": "2026-05-01",
        "value_num": 420,
        "value_text": None,
        "value_bool": None,
        "value_json": None,
        "confidence": 0.9,
    }))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    parser.parse_record(
        "수면 2026-05-01 7시간",
        known_items=[{"name": "수면", "schema": "duration", "unit": None}],
        now="2026-05-02T09:05:00+09:00",
    )
    system_prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "명시된 YYYY-MM-DD" in system_prompt
    assert "recorded_for" in system_prompt


def test_parse_record_handles_invalid_json_gracefully():
    client = _mock_client_with("not json at all")
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_record(
        "x", known_items=[], now="2026-04-14T08:30:00+09:00"
    )
    assert result.item_name is None
    assert result.confidence == 0.0


@pytest.mark.parametrize("payload", [
    "[]", "null", '"record"', "42", "true", "not json at all",
])
def test_parse_record_rejects_non_object_response_with_exact_fallback(payload):
    parser = NaturalLanguageParser(_mock_client_with(payload), "synthetic-model")
    result = parser.parse_record("운동했어", [], "2026-10-09T08:00:00+09:00")
    assert result == ParsedRecord(None, "2026-10-09", None, None, None, None, 0.0)


@pytest.mark.parametrize("field,bad_value", [
    ("item_name", 7), ("item_name", True), ("item_name", {}),
    ("value_text", 7), ("value_text", False), ("value_text", []),
    ("value_num", "7"), ("value_num", True), ("value_num", []),
    ("value_num", float("nan")), ("value_num", float("inf")),
    ("value_num", float("-inf")),
    ("value_bool", 1), ("value_bool", "true"),
    ("value_json", []), ("value_json", "{}"),
    ("confidence", "0.9"), ("confidence", True),
    ("confidence", None), ("confidence", float("nan")),
    ("confidence", float("inf")), ("confidence", -0.01),
    ("confidence", 1.01),
    ("recorded_for", 20261009), ("recorded_for", True),
    ("recorded_for", "2026-02-30"), ("recorded_for", "2026-10-09T12:00:00"),
])
def test_parse_record_rejects_wrong_field_type_or_value(field, bad_value):
    payload = {"item_name": "운동", "recorded_for": "2026-10-09",
               "value_text": None, "value_num": 3, "value_bool": None,
               "value_json": None, "confidence": 0.9}
    payload[field] = bad_value
    parser = NaturalLanguageParser(_mock_client_with(json.dumps(payload)), "synthetic-model")
    result = parser.parse_record("운동했어", [], "2026-10-09T08:00:00+09:00")
    assert result == ParsedRecord(None, "2026-10-09", None, None, None, None, 0.0)


@pytest.mark.parametrize("date_field", [{}, {"recorded_for": None}, {"recorded_for": ""}])
def test_parse_record_missing_null_or_empty_date_uses_reference_date(date_field):
    payload = {"item_name": "운동", "confidence": 1, "value_num": 0}
    payload.update(date_field)
    parser = NaturalLanguageParser(_mock_client_with(json.dumps(payload)), "synthetic-model")
    result = parser.parse_record("운동했어", [], "2026-10-09T08:00:00+09:00")
    assert result == ParsedRecord("운동", "2026-10-09", None, 0, None, None, 1.0)


def test_parse_record_empty_object_uses_missing_field_defaults():
    parser = NaturalLanguageParser(_mock_client_with("{}"), "synthetic-model")
    result = parser.parse_record("운동했어", [], "2026-10-09T08:00:00+09:00")
    assert result == ParsedRecord(None, "2026-10-09", None, None, None, None, 0.0)


def test_parse_record_malformed_response_does_not_log_raw_content(capsys, caplog):
    marker = "secret-model-output-marker"
    parser = NaturalLanguageParser(
        _mock_client_with(json.dumps({"item_name": [marker]})), "synthetic-model"
    )
    result = parser.parse_record("운동했어", [], "2026-10-09T08:00:00+09:00")
    assert result.item_name is None
    captured = capsys.readouterr()
    assert marker not in captured.out + captured.err + caplog.text


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
