"""Telegram tracking reply keyboard tool for upstream nanobot installations."""

from __future__ import annotations

import os
from typing import Any

import httpx
from nanobot.agent.tools.base import Tool, ToolResult, tool_parameters
from nanobot.agent.tools.context import ToolContext, current_request_context
from nanobot.agent.tools.message import _CURRENT_MESSAGE_SENDS
from nanobot.agent.tools.schema import ArraySchema, StringSchema, tool_parameters_schema

from msalt.tracking.cli import _make_reply_markup


@tool_parameters(
    tool_parameters_schema(
        content=StringSchema("Complete tracking record reply, including advice and follow-up question."),
        reply_keyboard=ArraySchema(
            ArraySchema(StringSchema("Telegram reply button label")),
            description="Telegram reply keyboard rows. Use [] to remove the current keyboard.",
        ),
        required=["content", "reply_keyboard"],
    )
)
class TrackingReplyTool(Tool):
    """Send one tracking record response to the current Telegram chat."""

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        return cls()

    @property
    def name(self) -> str:
        return "tracking_reply"

    @property
    def description(self) -> str:
        return (
            "Send the final tracking record response to the current Telegram chat "
            "with a persistent reply keyboard, or remove its keyboard. "
            "Use only after a successful my-nanobot-rpi tracking record command. "
            "After this tool succeeds, do not send another response."
        )

    async def execute(self, content: str, reply_keyboard: list[list[str]], **kwargs: Any) -> str:
        request = current_request_context()
        if request is None or request.channel != "telegram" or not request.chat_id.lstrip("-").isdigit():
            return ToolResult.error("Error: tracking_reply requires a current Telegram chat")
        if not isinstance(content, str) or not content.strip():
            return ToolResult.error("Error: content must be non-empty")
        if not isinstance(reply_keyboard, list) or any(
            not isinstance(row, list)
            or not row
            or any(not isinstance(label, str) or not label.strip() for label in row)
            for row in reply_keyboard
        ):
            return ToolResult.error("Error: reply_keyboard must be rows of button labels or []")
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return ToolResult.error("Error: Telegram bot token is not configured")

        payload: dict[str, Any] = {
            "chat_id": request.chat_id,
            "text": content,
            "reply_markup": _make_reply_markup(reply_keyboard),
        }
        if thread_id := request.metadata.get("message_thread_id"):
            payload["message_thread_id"] = thread_id
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage", json=payload,
                )
                response.raise_for_status()
                if response.json().get("ok") is not True:
                    return ToolResult.error("Error: Telegram rejected the tracking reply")
        except (httpx.HTTPError, ValueError) as exc:
            return ToolResult.error(f"Error: Telegram tracking reply failed: {type(exc).__name__}")

        # The upstream loop suppresses its normal reply when MessageTool records a
        # delivery to this turn's chat. Direct Bot API delivery needs the same mark.
        sends = _CURRENT_MESSAGE_SENDS.get()
        if sends is not None:
            sends.add((request.channel, request.chat_id))
        return "Tracking reply sent to current Telegram chat"
