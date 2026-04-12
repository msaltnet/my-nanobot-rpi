from unittest.mock import patch, MagicMock

import pytest

from msalt.lifestyle.cli import run_sleep_record, run_sleep_stats, run_todo_add, run_todo_list, run_log


@patch("msalt.lifestyle.cli.Storage")
def test_run_sleep_record(MockStorage):
    mock_storage = MockStorage.return_value
    result = run_sleep_record("2026-04-11", "23:00", "06:30", 450)
    assert "수면 기록 완료" in result


@patch("msalt.lifestyle.cli.Storage")
def test_run_todo_add(MockStorage):
    mock_storage = MockStorage.return_value
    mock_storage.insert_todo.return_value = 1
    result = run_todo_add("장보기")
    assert "추가" in result


@patch("msalt.lifestyle.cli.Storage")
def test_run_log(MockStorage):
    mock_storage = MockStorage.return_value
    mock_storage.insert_life_log.return_value = 1
    result = run_log("오늘 5km 달림")
    assert "기록 완료" in result
