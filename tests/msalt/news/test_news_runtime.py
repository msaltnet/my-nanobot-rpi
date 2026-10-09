"""Actual installed root tool, AgentLoop and bound cron with external fakes only."""

import asyncio
import json
import socket
from unittest.mock import MagicMock

import httpx
import pytest
from nanobot.agent.loop import AgentLoop
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import GenerationSettings, LLMResponse, ToolCallRequest

from msalt.news import reply_tool
from msalt.news.briefing import GeneratedBriefing
from msalt.news.coordinator import generate_snapshot
from msalt.news.delivery import DeliveryLedger
from msalt.storage import Storage


@pytest.fixture(autouse=True)
async def offline(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setenv("TELEGRAM_USER_ID", "123")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "synthetic")
    monkeypatch.setattr(reply_tool, "telegram_settings", lambda: ("synthetic", ["123"]))


def make_loop(tmp_path, outcome):
    storage = Storage(str(tmp_path / "msalt.db"))
    storage.initialize()
    if outcome != "empty":
        storage.insert_article(
            "test",
            "title",
            "https://example.test/article",
            "summary",
            "domestic",
            "2099-01-01 00:00:00",
        )
    collections, posts, requests, sent = [], [], [], []
    ledger = DeliveryLedger(storage.db_path)

    async def generation(**kwargs):
        class Collector:
            def collect(self):
                collections.append(1)

        if outcome == "generation_failure":
            raise RuntimeError("private exception")
        if outcome == "cancel":
            raise asyncio.CancelledError()
        if outcome == "partial":
            ledger.reserve(kwargs["ident"], kwargs["owner"], ["https://example.test/article"])
            ledger.prepare(
                kwargs["ident"],
                kwargs["owner"],
                GeneratedBriefing(
                    ("a" * 2000 + "\n") * 2 + "https://example.test/article",
                    ("https://example.test/article",),
                ),
            )
        else:
            generate_snapshot(**kwargs, collector=Collector(), use_llm=False)

    async def post(payload):
        posts.append(payload)
        if outcome == "unknown":
            raise httpx.ReadTimeout("private exception")
        if outcome == "failed":
            return 401, {"ok": False, "error_code": 401}
        if outcome == "partial" and len(posts) == 2:
            return 429, {"ok": False, "error_code": 429}
        return 200, {"ok": True, "result": {"message_id": len(posts)}}

    tool = reply_tool.NewsBriefingTool(
        tmp_path, generation=generation, post=post, db_path=storage.db_path
    )
    provider = MagicMock()
    provider.get_default_model.return_value = "offline"
    provider.generation = GenerationSettings()

    async def model(**kwargs):
        requests.append(1)
        assert len(requests) == 1, "hidden finalization/model retry"
        return LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest(
                    id="news", name="news_briefing", arguments={"time_of_day": "morning"}
                ),
                ToolCallRequest(
                    id="copy", name="message", arguments={"content": "COPY SAVED NEWS"}
                ),
            ],
        )

    provider.chat_stream_with_retry = model
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, model="offline")
    loop.tools.register(tool)

    async def send(message):
        sent.append(message)

    loop.tools.get("message").set_send_callback(send)
    return loop, ledger, collections, posts, requests, sent


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("sent", "sent"),
        ("failed", "failed"),
        ("unknown", "unknown"),
        ("partial", "unknown"),
        ("empty", "empty"),
        ("generation_failure", "failed"),
        ("cancel", "failed"),
    ],
)
@pytest.mark.parametrize("route", ["user", "cron"])
async def test_root_outcomes_never_emit_copied_generic_response(tmp_path, outcome, expected, route):
    loop, ledger, collections, posts, requests, sent = make_loop(tmp_path, outcome)
    if route == "user":
        result = await loop._process_message(
            InboundMessage(
                channel="telegram",
                sender_id="123",
                chat_id="123",
                content="news",
                metadata={"message_thread_id": 7},
            ),
            ephemeral=True,
        )
        assert result is None
    else:
        from nanobot.cron.bound_runner import run_bound_cron_job
        from nanobot.cron.types import CronJob, CronPayload

        records = []
        recorder = MagicMock()
        recorder.write_run_record.side_effect = lambda run_id, record: records.append(record)
        job = CronJob(
            id="news",
            name="news",
            payload=CronPayload(
                message="news",
                session_key="telegram:123",
                origin_channel="telegram",
                origin_chat_id="123",
                origin_metadata={"message_thread_id": 7},
            ),
        )
        result = await run_bound_cron_job(job, agent=loop, cron=recorder)
        assert result.response == "" and records[-1]["delivery"] == "owned"
    assert len(requests) == 1 and sent == []
    assert ledger.list()[0]["state"] == expected
    assert len(collections) <= 1
    assert "private" not in str(ledger.list())


@pytest.mark.parametrize(
    "sender,target,allowed,token",
    [
        ("999", "123", ["123"], "synthetic"),
        ("123", "999", ["123"], "synthetic"),
        ("123", "123", [], "synthetic"),
        ("123", "123", ["*"], "synthetic"),
        ("123", "123", ["123"], ""),
    ],
)
async def test_unauthorized_context_claims_but_does_no_external_work(
    tmp_path, monkeypatch, sender, target, allowed, token
):
    loop, ledger, collections, posts, requests, sent = make_loop(tmp_path, "sent")
    monkeypatch.setattr(reply_tool, "telegram_settings", lambda: (token, allowed))
    assert (
        await loop._process_message(
            InboundMessage(channel="telegram", sender_id=sender, chat_id=target, content="news"),
            ephemeral=True,
        )
        is None
    )
    assert collections == posts == sent == [] and ledger.list() == []
    assert len(requests) == 1


async def test_unsupported_old_runtime_registration_remains_safe(tmp_path, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "nanobot.agent.tools.delivery_control", None)
    tool = reply_tool.NewsBriefingTool(tmp_path, db_path=tmp_path / "absent.db")
    assert json.loads(await tool.execute("morning")) == {
        "status": "unsupported",
        "delivery_id": None,
    }
    assert not (tmp_path / "absent.db").exists()
