"""One external POST after a durable sending fence; uncertainty never retries."""

from __future__ import annotations

import asyncio
import json

from msalt.news.sender import BotAPI  # Shared one-POST transport and credential log filter.

__all__ = ["BotAPI", "NotificationSender", "classify"]


def classify(status, body):
    if isinstance(body, dict) and body.get("ok") is False:
        return "rejected", None, "api_rejected"
    if (
        isinstance(status, int)
        and 200 <= status < 300
        and isinstance(body, dict)
        and body.get("ok") is True
    ):
        result = body.get("result")
        identifier = result.get("message_id") if isinstance(result, dict) else None
        if type(identifier) is int and 0 < identifier <= 2**63 - 1:
            return "sent", identifier, None
        return "unknown", None, "missing_message_id"
    return "unknown", None, "ambiguous_response"


class NotificationSender:
    def __init__(self, store, *, post):
        self.store, self.post = store, post

    def _uncertain(self, identifier, token, code):
        try:
            self.store.finish(identifier, token, state="unknown", error_code=code)
        except Exception:
            # Durable sending+URL claims remain indefinitely; never release/re-POST.
            pass

    async def send(self, identifier, *, now=None):
        row = self.store.show(identifier)
        # Read/parse before fencing: a pre-POST storage failure cannot call transport.
        payload = json.loads(row["payload"])
        token = self.store.start_sending(identifier, now=now)
        if token is None:
            return self.store.show(identifier)["state"]
        try:
            async with asyncio.timeout(20):
                status, body = await self.post(payload)
            state, message_id, code = classify(status, body)
        except asyncio.CancelledError:
            self._uncertain(identifier, token, "post_cancelled")
            raise
        except Exception:
            state, message_id, code = "unknown", None, "post_uncertain"
        try:
            self.store.finish(
                identifier, token, state=state, message_id=message_id, error_code=code
            )
        except Exception:
            self._uncertain(identifier, token, "ack_storage_failed")
        return self.store.show(identifier)["state"]
