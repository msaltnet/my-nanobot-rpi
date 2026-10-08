"""Offline delivery-boundary characterization, not Telegram receipt or exactly-once proof.

These tests pin the current nanobot behavior: a successful send call and a handled
send failure both return None. No Telegram plugin, gateway, or live cron runs.
"""

import asyncio
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
import pytest_asyncio
from nanobot.bus.events import OutboundMessage
from nanobot.channels.manager import ChannelManager
from nanobot.cron.service import _normalize_agent_turn_job
from nanobot.cron.session_turns import is_bound_cron_job
from nanobot.cron.types import CronJob


@pytest_asyncio.fixture(autouse=True)
async def block_external_network(monkeypatch):
    """Fail rather than contact any real recipient, API, or DNS service."""

    def blocked(*args, **kwargs):
        raise AssertionError("Network access is forbidden in offline delivery tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket.socket, "sendto", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    yield


@pytest.fixture
def delivery_boundary(monkeypatch):
    """Build only the retry boundary; never initialize channel plugins."""
    manager = object.__new__(ChannelManager)
    manager.config = SimpleNamespace(channels=SimpleNamespace(send_max_retries=3))
    channel = SimpleNamespace(send=AsyncMock(), should_retry_send_error=Mock(return_value=True))
    message = OutboundMessage(
        channel="telegram", chat_id="synthetic-offline-recipient", content="Synthetic briefing"
    )
    sleep = AsyncMock()
    monkeypatch.setattr("nanobot.channels.manager.asyncio.sleep", sleep)
    return manager, channel, message, sleep


async def test_retry_success_returns_none_without_proving_actual_receipt(delivery_boundary):
    """A fake send completion proves attempts, not Telegram receipt/exactly-once."""
    manager, channel, message, sleep = delivery_boundary
    first_error = TimeoutError("synthetic timeout")
    second_error = OSError("synthetic connection failure")
    channel.send.side_effect = [first_error, second_error, None]

    assert await manager._send_with_retry(channel, message) is None

    assert channel.send.await_args_list == [call(message)] * 3
    assert channel.should_retry_send_error.call_args_list == [call(first_error), call(second_error)]
    assert sleep.await_args_list == [call(1), call(2)]


async def test_retry_exhaustion_is_swallowed_and_returns_none(delivery_boundary):
    """Current exhaustion is handled locally; None cannot distinguish failed delivery."""
    manager, channel, message, sleep = delivery_boundary
    error = TimeoutError("synthetic repeated timeout")
    channel.send.side_effect = error

    assert await manager._send_with_retry(channel, message) is None

    assert channel.send.await_args_list == [call(message)] * 3
    assert channel.should_retry_send_error.call_args_list == [call(error)] * 3
    assert sleep.await_args_list == [call(1), call(2)]


async def test_nonretryable_failure_is_swallowed_without_second_send(delivery_boundary):
    """Current nonretryable failure returns None, not a receipt/failure result."""
    manager, channel, message, sleep = delivery_boundary
    error = ValueError("synthetic nonretryable payload")
    channel.send.side_effect = error
    channel.should_retry_send_error.return_value = False

    assert await manager._send_with_retry(channel, message) is None

    channel.send.assert_awaited_once_with(message)
    channel.should_retry_send_error.assert_called_once_with(error)
    sleep.assert_not_awaited()


@pytest.mark.parametrize("cancel_during", ["send", "backoff"])
async def test_cancellation_propagates_without_an_additional_send(delivery_boundary, cancel_during):
    """Cancellation remains visible at both send and backoff boundaries."""
    manager, channel, message, sleep = delivery_boundary
    if cancel_during == "send":
        channel.send.side_effect = asyncio.CancelledError()
    else:
        channel.send.side_effect = TimeoutError("synthetic timeout before cancellation")
        sleep.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await manager._send_with_retry(channel, message)

    channel.send.assert_awaited_once_with(message)
    if cancel_during == "send":
        channel.should_retry_send_error.assert_not_called()
        sleep.assert_not_awaited()
    else:
        channel.should_retry_send_error.assert_called_once()
        sleep.assert_awaited_once_with(1)


@pytest.mark.parametrize("expr", ["0 7 * * *", "0 14 * * *", "0 20 * * *"])
@pytest.mark.parametrize("enabled", [True, False])
def test_legacy_cron_normalization_preserves_route_enabled_and_kst(monkeypatch, expr, enabled):
    """Pure normalization characterizes config compatibility, not scheduled receipt."""
    monkeypatch.setattr("nanobot.cron.service._now_ms", lambda: 123456789)
    recipient = "synthetic-offline-recipient"
    job = CronJob.from_store_dict(
        {
            "id": "synthetic-news-job",
            "name": "Synthetic news briefing",
            "enabled": enabled,
            "schedule": {"kind": "cron", "expr": expr, "tz": "Asia/Seoul"},
            "payload": {
                "kind": "agent_turn",
                "message": "Generate a synthetic briefing",
                "deliver": True,
                "channel": "telegram",
                "to": recipient,
                "channelMeta": {"message_thread_id": 42},
            },
            "createdAtMs": 100,
            "updatedAtMs": 200,
        }
    )
    assert not is_bound_cron_job(job)

    assert _normalize_agent_turn_job(job) is True

    assert is_bound_cron_job(job)
    assert job.enabled is enabled
    assert (job.schedule.kind, job.schedule.expr, job.schedule.tz) == ("cron", expr, "Asia/Seoul")
    assert job.payload.session_key == f"telegram:{recipient}"
    assert job.payload.origin_channel == "telegram"
    assert job.payload.origin_chat_id == recipient
    assert job.payload.origin_metadata == {"message_thread_id": 42}
    assert job.payload.message == "Generate a synthetic briefing"
    assert job.payload.deliver is False
    assert (job.payload.channel, job.payload.to, job.payload.channel_meta) == (None, None, {})
    assert job.created_at_ms == 100
    assert job.updated_at_ms == 123456789
    assert _normalize_agent_turn_job(job) is False
    assert is_bound_cron_job(job)
