"""The shipped Luna configuration must keep tool calls on Responses."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nanobot.config.loader import load_config
from nanobot.providers.factory import make_provider


@pytest.mark.asyncio
async def test_seeded_luna_does_not_fall_back_to_chat_completions(tmp_path):
    config_path = Path(__file__).resolve().parents[2] / "msalt" / "nanobot-config.example.json"
    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    config_data["providers"]["openai"]["apiKey"] = "test-key"
    seeded_config = tmp_path / "config.json"
    seeded_config.write_text(json.dumps(config_data), encoding="utf-8")
    config = load_config(seeded_config)
    provider = make_provider(config)

    class ResponsesUnavailableError(Exception):
        status_code = 404
        body = "Responses API unsupported"

    responses_create = AsyncMock(side_effect=ResponsesUnavailableError())
    chat_create = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="unexpected chat fallback", tool_calls=None),
            finish_reason="stop",
        )],
        usage=None,
    ))
    provider._client = SimpleNamespace(
        responses=SimpleNamespace(create=responses_create),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
    )

    result = await provider.chat(
        messages=[{"role": "user", "content": "record sleep"}],
        tools=[{
            "type": "function",
            "function": {
                "name": "record",
                "description": "Record a value",
                "parameters": {"type": "object", "properties": {}},
            },
        }],
        reasoning_effort="medium",
    )

    assert result.finish_reason == "error"
    responses_create.assert_awaited_once()
    chat_create.assert_not_awaited()
