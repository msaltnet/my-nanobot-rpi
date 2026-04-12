import pytest

from msalt.lifestyle.classifier import classify_text


def test_classify_exercise():
    result = classify_text("오늘 5km 달림")
    assert result["category"] == "exercise"
    assert "5km" in result["parsed_data"]["detail"]


def test_classify_food():
    result = classify_text("커피 3잔 마심")
    assert result["category"] == "food"


def test_classify_health():
    result = classify_text("두통약 먹음")
    assert result["category"] == "health"


def test_classify_mood():
    result = classify_text("기분 좋음")
    assert result["category"] == "mood"


def test_classify_unknown():
    result = classify_text("아무 의미 없는 텍스트 qlwkejr")
    assert result["category"] == "other"
