"""Compatibility for SDK field aliases in nanobot v0.3.5 Responses replay."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

_INSTALLED = False


def install_responses_compat() -> None:
    """Use wire aliases and repair old function-call state without editing upstream."""
    global _INSTALLED
    if _INSTALLED:
        return
    from nanobot.providers.openai_responses import parsing, state

    original_object = parsing._response_object
    original_replay = state._prepare_replayed_items

    def response_object(value: object) -> dict[str, Any] | None:
        if isinstance(value, BaseModel):
            return value.model_dump(by_alias=True, exclude_none=True)
        return original_object(value)

    def prepare_replayed_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        replayed = original_replay(items)
        for item in replayed:
            if item.get("type") == "function_call" and "async_" in item:
                async_value = item.pop("async_")
                if async_value is not None and "async" not in item:
                    item["async"] = async_value
        return replayed

    parsing._response_object = response_object
    state._prepare_replayed_items = prepare_replayed_items
    _INSTALLED = True
