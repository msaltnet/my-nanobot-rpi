"""Issue #18: Telegram ACK is required before tracking delivery succeeds."""

from datetime import datetime
from io import StringIO
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from loguru import logger
from nanobot.agent.tools.context import RequestContext, request_context
from nanobot.agent.tools.message import capture_message_deliveries
from nanobot.session.manager import SessionManager

from msalt.storage import Storage
from msalt.tracking.cli import _make_telegram_sender
from msalt.tracking.delivery_errors import DeliveryRejected, DeliveryUnknown
from msalt.tracking.dispatcher import Dispatcher
from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager
from msalt.tracking.reply_tool import TrackingReplyTool


@pytest.fixture(autouse=True)
def telegram_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("TELEGRAM_USER_ID", "123")


def response(status, body):
    def parse():
        if isinstance(body, Exception):
            raise body
        return body

    return SimpleNamespace(status_code=status, json=parse)


@pytest.mark.parametrize(
    "status,body,classification",
    [
        (401, {"ok": False, "description": "secret-token"}, DeliveryRejected),
        (429, {"ok": False, "description": "secret-token"}, DeliveryRejected),
        (500, {"ok": False, "description": "secret-token"}, DeliveryRejected),
        (200, {"ok": False}, DeliveryRejected),
        (401, {"ok": True}, DeliveryUnknown),
        (429, {"ok": True}, DeliveryUnknown),
        (500, {"ok": True}, DeliveryUnknown),
        (401, {"error": "unauthorized"}, DeliveryUnknown),
        (429, ValueError("secret-token invalid JSON"), DeliveryUnknown),
        (500, ["ok", False], DeliveryUnknown),
        (200, {"ok": 1}, DeliveryUnknown),
        (200, {"ok": 0}, DeliveryUnknown),
        (200, {"ok": None}, DeliveryUnknown),
        (200, True, DeliveryUnknown),
        (200, ValueError("secret-token invalid JSON"), DeliveryUnknown),
    ],
)
def test_sender_requires_complete_ack(tmp_path, monkeypatch, status, body, classification):
    posted = []
    monkeypatch.setattr(
        httpx, "post",
        lambda *args, **kwargs: posted.append(1) or response(status, body),
    )
    with pytest.raises(classification) as failure:
        _make_telegram_sender(tmp_path)("question")
    assert "secret-token" not in str(failure.value)
    assert posted == [1]
    assert SessionManager(tmp_path).get_or_create("telegram:123").get_history() == []


@pytest.mark.parametrize("status", [200, 201])
def test_sender_records_only_confirmed_ack(tmp_path, monkeypatch, status):
    posted = []
    monkeypatch.setattr(
        httpx, "post",
        lambda *args, **kwargs: posted.append(1) or response(status, {"ok": True}),
    )
    _make_telegram_sender(tmp_path)("question")
    assert posted == [1]
    history = SessionManager(tmp_path).get_or_create("telegram:123").get_history()
    assert [turn["content"] for turn in history] == ["question"]


@pytest.mark.parametrize("exception", [
    httpx.TimeoutException("secret-token timeout"),
    httpx.ConnectError("secret-token connection"),
])
def test_sender_transport_error_is_unknown_and_secret_free(
    tmp_path, monkeypatch, exception
):
    def fail(*args, **kwargs):
        raise exception

    monkeypatch.setattr(httpx, "post", fail)
    with pytest.raises(DeliveryUnknown) as failure:
        _make_telegram_sender(tmp_path)("question")
    assert "secret-token" not in str(failure.value)
    assert SessionManager(tmp_path).get_or_create("telegram:123").get_history() == []


@pytest.mark.parametrize("status,body,classification", [
    (401, {"ok": False}, DeliveryRejected),
    (429, {"error": "rate limit"}, DeliveryUnknown),
    (500, ValueError("invalid JSON"), DeliveryUnknown),
])
def test_dispatcher_keeps_state_unset_without_ack(
    tmp_path, monkeypatch, status, body, classification
):
    db = tmp_path / "tracking.db"
    store = Storage(str(db))
    store.initialize()
    items = TrackedItemManager(store)
    items.add("운동", "boolean", None, "08:00")
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response(status, body))
    dispatcher = Dispatcher(items, RecordManager(store, items), _make_telegram_sender(tmp_path))
    with pytest.raises(classification):
        dispatcher.run(datetime(2026, 10, 9, 8, 0, tzinfo=ZoneInfo("Asia/Seoul")))
    item = store.get_tracked_item_by_name("운동")
    assert item["pending_since"] is None
    assert item["pending_recorded_for"] is None
    assert item["last_asked_at"] is None
    assert SessionManager(tmp_path).get_or_create("telegram:123").get_history() == []


def test_session_write_failure_does_not_reclassify_ack_or_log_secrets(
    tmp_path, monkeypatch
):
    posted = []
    monkeypatch.setattr(
        httpx, "post",
        lambda *args, **kwargs: posted.append(1) or response(200, {"ok": True}),
    )

    def fail_session(*args):
        raise RuntimeError("secret-token https://api.telegram.org/botsecret-token/sendMessage")

    monkeypatch.setattr("msalt.tracking.cli._record_outbound_in_session", fail_session)
    output = StringIO()
    sink = logger.add(output, format="{message}")
    try:
        assert _make_telegram_sender(tmp_path)("question") is None
    finally:
        logger.remove(sink)
    assert posted == [1]
    assert "session" in output.getvalue().lower()
    assert "secret-token" not in output.getvalue()
    assert "https://api.telegram.org" not in output.getvalue()


def test_dispatcher_marks_ack_delivered_when_session_write_fails(tmp_path, monkeypatch):
    db = tmp_path / "tracking.db"
    store = Storage(str(db))
    store.initialize()
    items = TrackedItemManager(store)
    items.add("운동", "boolean", None, "08:00")
    posted = []
    monkeypatch.setattr(
        httpx, "post",
        lambda *args, **kwargs: posted.append(1) or response(200, {"ok": True}),
    )

    def fail_session(*args):
        raise RuntimeError("secret-token session failure")

    monkeypatch.setattr("msalt.tracking.cli._record_outbound_in_session", fail_session)
    dispatcher = Dispatcher(items, RecordManager(store, items), _make_telegram_sender(tmp_path))
    messages = dispatcher.run(datetime(2026, 10, 9, 8, 0, tzinfo=ZoneInfo("Asia/Seoul")))
    item = store.get_tracked_item_by_name("운동")
    assert len(messages) == 1
    assert posted == [1]
    assert item["pending_recorded_for"] == "2026-10-09"
    assert item["last_asked_at"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body", [
    (401, {"ok": False}),
    (429, {"error": "rate limit"}),
    (500, ValueError("secret-token invalid JSON")),
    (200, {"ok": 1}),
    (200, ["ok", True]),
])
async def test_reply_tool_does_not_mark_delivery_without_ack(
    monkeypatch, status, body
):
    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, json):
            return response(status, body)

    monkeypatch.setattr("msalt.tracking.reply_tool.httpx.AsyncClient", Client)
    with request_context(RequestContext(channel="telegram", chat_id="123")):
        with capture_message_deliveries() as sends:
            result = await TrackingReplyTool().execute(content="question", reply_keyboard=[])
    assert result.is_error
    assert sends == set()
    assert "secret-token" not in str(result)
