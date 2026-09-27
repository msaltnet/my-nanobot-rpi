"""Tracking replies use Telegram's persistent reply keyboard on nanobot v0.3.5."""

import pytest
from nanobot.agent.tools.context import RequestContext, request_context
from nanobot.agent.tools.loader import ToolLoader
from nanobot.agent.tools.message import capture_message_deliveries

from msalt.tracking.reply_tool import TrackingReplyTool


@pytest.mark.asyncio
async def test_tracking_reply_sends_keyboard_and_suppresses_duplicate(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    posted = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, json):
            posted.append((url, json))
            return Response()

    monkeypatch.setattr("msalt.tracking.reply_tool.httpx.AsyncClient", Client)
    tool = TrackingReplyTool()
    with request_context(RequestContext(channel="telegram", chat_id="123")):
        with capture_message_deliveries() as sends:
            result = await tool.execute(
                content="기록했어.\n\n다음 질문",
                reply_keyboard=[["영어공부 했어", "영어공부 안 했어"]],
            )

    assert "sent" in result.lower()
    assert sends == {("telegram", "123")}
    assert posted[0][0] == "https://api.telegram.org/bottest-token/sendMessage"
    assert posted[0][1]["reply_markup"]["keyboard"][0][0]["text"] == "영어공부 했어"


@pytest.mark.asyncio
async def test_tracking_reply_removes_keyboard(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    posted = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, json):
            posted.append(json)
            return Response()

    monkeypatch.setattr("msalt.tracking.reply_tool.httpx.AsyncClient", Client)
    with request_context(RequestContext(channel="telegram", chat_id="123")):
        await TrackingReplyTool().execute(content="모두 기록했어", reply_keyboard=[])
    assert posted[0]["reply_markup"] == {"remove_keyboard": True}


@pytest.mark.asyncio
async def test_tracking_reply_rejects_other_channels_without_sending(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    tool = TrackingReplyTool()
    with request_context(RequestContext(channel="cli", chat_id="direct")):
        with capture_message_deliveries() as sends:
            result = await tool.execute(content="hello", reply_keyboard=[])
    assert result.is_error
    assert sends == set()


@pytest.mark.asyncio
async def test_tracking_reply_failure_allows_normal_response(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": False}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, json):
            return Response()

    monkeypatch.setattr("msalt.tracking.reply_tool.httpx.AsyncClient", Client)
    with request_context(RequestContext(channel="telegram", chat_id="123")):
        with capture_message_deliveries() as sends:
            result = await TrackingReplyTool().execute(content="기록했어", reply_keyboard=[])
    assert result.is_error
    assert sends == set()


def test_tracking_reply_discovered_as_external_tool():
    plugins = ToolLoader()._discover_plugins()
    assert plugins["tracking_reply"] is TrackingReplyTool
