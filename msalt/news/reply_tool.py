"""Exclusive news tool; the model cannot choose targets or authorize retries."""

from __future__ import annotations

import json
import os
from pathlib import Path

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.context import current_request_context
from nanobot.agent.tools.schema import StringSchema, tool_parameters_schema

from msalt.config import MsaltConfig
from msalt.news.briefing import BRIEFING_LABELS
from msalt.news.coordinator import NewsDeliveryCoordinator, bounded_generation
from msalt.news.sender import BotAPI
from msalt.storage import Storage


def telegram_settings():
    from nanobot.config.loader import load_config

    config = load_config()
    telegram = config.channels.telegram
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or telegram.token, list(
        telegram.allow_from
    )


def authorized_target(target, *, sender=None):
    token, allowed = telegram_settings()
    recipient = os.environ.get("TELEGRAM_USER_ID", "").strip()
    if (
        not token
        or not recipient.isdecimal()
        or target != recipient
        or recipient not in {str(value) for value in allowed}
    ):
        raise ValueError("news target unavailable")
    if sender is not None and sender not in (recipient, "cron"):
        raise ValueError("news sender unavailable")
    return token


@tool_parameters(
    tool_parameters_schema(
        time_of_day=StringSchema("morning, afternoon or evening"), required=["time_of_day"]
    )
)
class NewsBriefingTool(Tool):
    name = "news_briefing"
    description = "Collect and deliver the scheduled news briefing exactly once. Return status only; never copy or send its body. No retry authority."
    exclusive = True

    def __init__(self, workspace, *, generation=bounded_generation, post=None, db_path=None):
        self.workspace = Path(workspace)
        self.db_path = str(db_path if db_path is not None else MsaltConfig().db_path)
        self.generation = generation
        self.post = post

    @classmethod
    def create(cls, ctx):
        return cls(ctx.workspace)

    async def execute(self, time_of_day="morning", **kwargs):
        # Lazy negotiation keeps registration possible on an older installation.
        try:
            from nanobot.agent.tools.delivery_control import (
                DELIVERY_CONTROL_API_VERSION,
                DeliveryClaimError,
                current_turn_delivery_control,
            )
        except ImportError:
            return json.dumps({"status": "unsupported", "delivery_id": None})
        control = current_turn_delivery_control()
        if DELIVERY_CONTROL_API_VERSION != 1 or control is None or control.api_version != 1:
            return json.dumps({"status": "unsupported", "delivery_id": None})
        try:
            ownership = control.claim_current_target(owner_tool=self.name)
        except DeliveryClaimError:
            return json.dumps({"status": "denied", "delivery_id": None})
        # Ownership survives every validation/error outcome and is never an ACK.
        try:
            request = current_request_context()
            if (
                request is None
                or not request.sender_id
                or request.channel != "telegram"
                or time_of_day not in BRIEFING_LABELS
                or kwargs
            ):
                raise ValueError("invalid context")
            thread = request.metadata.get("message_thread_id", request.metadata.get("thread_id"))
            if thread is not None and (
                isinstance(thread, bool) or not str(thread).isdecimal() or int(thread) <= 0
            ):
                raise ValueError("invalid thread")
            if (ownership.channel, ownership.chat_id, ownership.thread_id) != (
                request.channel,
                request.chat_id,
                str(thread) if thread is not None else None,
            ):
                raise ValueError("context mismatch")
            if request.turn_id and request.turn_id != ownership.turn_id:
                raise ValueError("turn mismatch")
            if (
                request.workspace is not None
                and request.workspace.resolve() != self.workspace.resolve()
            ):
                raise ValueError("workspace mismatch")
            token = authorized_target(request.chat_id, sender=request.sender_id)
            # Preserve the established CLI/legacy DB location even when the agent
            # workspace is customized; no implicit migration or history reset.
            db_path = self.db_path
            Storage(str(db_path)).initialize()
            service = NewsDeliveryCoordinator(
                db_path, post=self.post or BotAPI(token), generation=self.generation
            )
            return json.dumps(
                await service.run(
                    request.chat_id, str(thread) if thread is not None else "", time_of_day
                )
            )
        except Exception:
            return json.dumps({"status": "unavailable", "delivery_id": None})
