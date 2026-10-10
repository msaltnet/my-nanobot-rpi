"""Bot API sender. Only explicit API Message IDs acknowledge delivery."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass

import httpx

from msalt.news.delivery import RUN_SECONDS


class ProvenNoSendError(Exception):
    """Transport evidence proves no HTTP request headers/body were started."""


@dataclass(frozen=True)
class Outcome:
    kind: str
    error: str = ""
    message_id: int | None = None
    retry_after: float | None = None


def classify(status, body):
    if status >= 500 or not isinstance(body, dict):
        return Outcome("unknown", "ambiguous_response")
    if 200 <= status < 300 and body.get("ok") is True:
        result = body.get("result")
        ident = result.get("message_id") if isinstance(result, dict) else None
        if isinstance(ident, int) and not isinstance(ident, bool) and ident > 0:
            return Outcome("ack", message_id=ident)
        return Outcome("unknown", "missing_message_id")
    code = body.get("error_code")
    if status >= 400 and code != status:
        return Outcome("unknown", "inconsistent_response")
    if body.get("ok") is False and isinstance(code, int) and not isinstance(code, bool):
        if code == 429:
            params = body.get("parameters")
            delay = params.get("retry_after") if isinstance(params, dict) else None
            if delay is not None and (
                isinstance(delay, bool)
                or not isinstance(delay, (int, float))
                or delay < 0
                or not math.isfinite(delay)
            ):
                return Outcome("failed", "invalid_retry_after")
            return Outcome("retry", "api_rate_limit", retry_after=delay)
        if 400 <= code < 500:
            return Outcome("failed", "api_rejected")
    return Outcome("unknown", "ambiguous_response")


class _TelegramLogFilter(logging.Filter):
    def filter(self, record):
        # HTTPX INFO records otherwise expose Telegram's credential-bearing URL.
        if "api.telegram.org/bot" in record.getMessage():
            record.msg = "Telegram API request (redacted)"
            record.args = ()
        return True


logging.getLogger("httpx").addFilter(_TelegramLogFilter())


class BotAPI:
    """One POST only; httpcore trace qualifies pre-connect failures conservatively."""

    def __init__(self, token):
        if not token or not token.strip():
            raise ValueError("Telegram token not configured")
        self.token = token

    async def __call__(self, payload):
        evidence = {"connect_started": False, "request_started": False}

        async def trace(name, info):
            if name.endswith("connect_tcp.started") or name.endswith("connect_unix_socket.started"):
                evidence["connect_started"] = True
            if "send_request_" in name:
                evidence["request_started"] = True

        # No SDK or transport retries, no redirects, no environment proxy forwarding.
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(retries=0),
            timeout=10,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            try:
                response = await client.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json=payload,
                    extensions={"trace": trace},
                )
            except (httpx.ConnectError, httpx.ConnectTimeout):
                if evidence["connect_started"] and not evidence["request_started"]:
                    raise ProvenNoSendError() from None
                raise
            return response.status_code, response.json()


class DeliverySender:
    def __init__(self, ledger, *, post, sleep=asyncio.sleep, monotonic=time.monotonic):
        self.ledger = ledger
        self.post = post
        self.sleep = sleep
        self.monotonic = monotonic

    async def send(self, ident, *, manual=False, confirm_uncertain=False, deadline=None):
        owner = self.ledger.claim_send(ident, manual=manual, confirm_uncertain=confirm_uncertain)
        if owner is None:
            return self.ledger.show(ident)["state"]
        deadline = deadline if deadline is not None else self.monotonic() + RUN_SECONDS
        attempted = False
        try:
            row = self.ledger.validate_snapshot(ident)
            any_ack = any(p["message_id"] is not None for p in row["parts"])
            for part in row["parts"]:
                if part["message_id"] is not None:
                    continue
                payload = {"chat_id": row["target"], "text": part["text"]}
                if row["thread"]:
                    payload["message_thread_id"] = int(row["thread"])
                while True:
                    if self.monotonic() >= deadline:
                        self.ledger.finish_failure(ident, owner, "run_deadline")
                        return self.ledger.show(ident)["state"]
                    attempt = self.ledger.claim_part(ident, owner, part["part_no"])
                    remaining = deadline - self.monotonic()
                    if remaining <= 0:
                        self.ledger.reject(ident, owner, part["part_no"], attempt, "run_deadline")
                        self.ledger.finish_failure(ident, owner, "run_deadline")
                        return self.ledger.show(ident)["state"]
                    attempted = True
                    try:
                        async with asyncio.timeout(max(0, deadline - self.monotonic())):
                            status, body = await self.post(payload)
                        outcome = classify(status, body)
                    except ProvenNoSendError:
                        outcome = Outcome("retry", "proven_preconnect_failure")
                    except asyncio.CancelledError:
                        self._uncertain(ident, owner, "post_cancelled")
                        raise
                    except Exception:
                        # No exception string/token/API URL is persisted or logged.
                        outcome = Outcome("unknown", "post_result_uncertain")
                    if outcome.kind == "ack":
                        self.ledger.ack(ident, owner, part["part_no"], attempt, outcome.message_id)
                        any_ack = True
                        if self.monotonic() >= deadline:
                            self.ledger.finish_failure(ident, owner, "late_api_ack", unknown=True)
                            return self.ledger.show(ident)["state"]
                        break
                    self.ledger.reject(
                        ident,
                        owner,
                        part["part_no"],
                        attempt,
                        outcome.error,
                        unknown=outcome.kind == "unknown",
                    )
                    detail = self.ledger.show(ident)
                    current = next(p for p in detail["parts"] if p["part_no"] == part["part_no"])
                    delay = (
                        outcome.retry_after
                        if outcome.retry_after is not None
                        else current["attempts"]
                    )
                    may_retry = (
                        outcome.kind == "retry"
                        and not any_ack
                        and not manual
                        and current["attempts"] < 3
                        and self.monotonic() + delay < deadline
                    )
                    if not may_retry:
                        self.ledger.finish_failure(
                            ident, owner, outcome.error, unknown=outcome.kind == "unknown"
                        )
                        return self.ledger.show(ident)["state"]
                    await self.sleep(delay)
            self.ledger.finish(ident, owner)
            return self.ledger.show(ident)["state"]
        except asyncio.CancelledError:
            self._uncertain(ident, owner, "send_cancelled")
            raise
        except Exception:
            # ACK persistence/final commit failures must never restart sending.
            self.ledger.finish_failure(ident, owner, "storage_or_claim_failure", unknown=attempted)
            return self.ledger.show(ident)["state"]

    def _uncertain(self, ident, owner, error):
        try:
            self.ledger.finish_failure(ident, owner, error, unknown=True)
        except Exception:
            # Durable sending claim survives; expired ownership recovers to unknown.
            pass
