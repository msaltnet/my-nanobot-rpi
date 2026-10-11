"""Real nanobot config boundary; synthetic credentials and blocked networking."""

import json
import socket

import pytest
from nanobot.agent.tools.context import RequestContext, request_context
from nanobot.agent.tools.delivery_control import delivery_control_scope, delivery_tool_dispatch
from nanobot.config import loader

from msalt.news.coordinator import generate_snapshot
from msalt.news.delivery import DeliveryLedger
from msalt.news.reply_tool import NewsBriefingTool, authorized_target, telegram_settings
from msalt.storage import Storage


@pytest.fixture
async def config_file(tmp_path, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setenv("TELEGRAM_USER_ID", "123")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("UNSET_NEWS_TEST_VAR", raising=False)
    path = tmp_path / "config.json"
    monkeypatch.setattr(loader, "_current_config_path", path)

    def write(telegram):
        # Unrelated missing provider references must not block this lazy boundary.
        path.write_text(
            json.dumps(
                {
                    "channels": {"telegram": telegram},
                    "providers": {"openai": {"apiKey": "${UNSET_NEWS_TEST_VAR}"}},
                }
            ),
            encoding="utf-8",
        )
        return path

    return write


@pytest.mark.parametrize("alias", ["allowFrom", "allow_from"])
@pytest.mark.parametrize("use_refs", [False, True])
def test_settings_resolve_real_channel_mapping(config_file, monkeypatch, alias, use_refs):
    monkeypatch.setenv("NEWS_TEST_TOKEN", "synthetic-config-token")
    path = config_file(
        {
            "token": "${NEWS_TEST_TOKEN}" if use_refs else "synthetic-config-token",
            alias: ["${TELEGRAM_USER_ID}" if use_refs else "123"],
        }
    )
    original = path.read_bytes()
    assert telegram_settings() == ("synthetic-config-token", ["123"])
    assert authorized_target("123", sender="123") == "synthetic-config-token"
    assert path.read_bytes() == original


def test_environment_token_overrides_config_fallback(config_file, monkeypatch):
    config_file({"token": "${UNSET_NEWS_TEST_VAR}", "allowFrom": ["123"]})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "  synthetic-env-token  ")
    assert telegram_settings() == ("synthetic-env-token", ["123"])


def test_blank_environment_token_uses_config(config_file, monkeypatch):
    config_file({"token": "synthetic-config-token", "allowFrom": ["123"]})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "  ")
    assert telegram_settings() == ("synthetic-config-token", ["123"])


@pytest.mark.parametrize(
    "telegram",
    [
        None,
        {},
        {"token": 123, "allowFrom": ["123"]},
        {"token": "", "allowFrom": ["123"]},
        {"token": "${UNSET_NEWS_TEST_VAR}", "allowFrom": ["123"]},
        {"token": "synthetic", "allowFrom": "123"},
        {"token": "synthetic", "allowFrom": [123]},
        {"token": "synthetic", "allowFrom": ["${UNSET_NEWS_TEST_VAR}"]},
        {"token": "synthetic", "allowFrom": [""]},
    ],
)
def test_settings_reject_invalid_or_unresolved_values(config_file, telegram):
    config_file(telegram)
    with pytest.raises(ValueError) as error:
        telegram_settings()
    assert "synthetic" not in str(error.value)
    assert "UNSET_NEWS_TEST_VAR" not in str(error.value)


@pytest.mark.parametrize(
    "target,sender,allowed,recipient",
    [
        ("999", "123", ["123"], "123"),
        ("123", "999", ["123"], "123"),
        ("123", "123", ["*"], "123"),
        ("123", "123", [], "123"),
        ("123", "123", ["123"], "username"),
    ],
)
def test_real_settings_preserve_target_authorization(
    config_file, monkeypatch, target, sender, allowed, recipient
):
    config_file({"token": "synthetic", "allowFrom": allowed})
    monkeypatch.setenv("TELEGRAM_USER_ID", recipient)
    with pytest.raises(ValueError):
        authorized_target(target, sender=sender)


@pytest.mark.parametrize(
    "case", ["literal", "refs", "wrong_target", "wrong_sender", "missing", "unresolved"]
)
async def test_news_tool_uses_real_settings_before_generation_and_delivery(
    tmp_path, config_file, monkeypatch, case
):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "synthetic")
    config_file({"allowFrom": ["${TELEGRAM_USER_ID}" if case == "refs" else "123"]})
    if case == "missing":
        config_file({})
    if case == "unresolved":
        config_file({"allowFrom": ["${UNSET_NEWS_TEST_VAR}"]})
    success = case in ("literal", "refs")
    db_path = tmp_path / "news.db"
    if success:
        storage = Storage(str(db_path))
        storage.initialize()
        storage.insert_article(
            "synthetic",
            "test title",
            "https://example.test/news",
            "summary",
            "domestic",
            "2099-01-01 00:00:00",
        )
    collected, posts = [], []

    class Collector:
        def collect(self):
            collected.append(1)

    async def generation(**kwargs):
        generate_snapshot(**kwargs, collector=Collector(), use_llm=False)

    async def post(payload):
        posts.append(payload)
        return 200, {"ok": True, "result": {"message_id": 9}}

    tool = NewsBriefingTool(tmp_path, generation=generation, post=post, db_path=db_path)
    target = "999" if case == "wrong_target" else "123"
    sender = "999" if case == "wrong_sender" else "123"
    request = RequestContext(
        channel="telegram", chat_id=target, sender_id=sender, workspace=tmp_path
    )
    with request_context(request), delivery_control_scope(request) as control:
        with delivery_tool_dispatch(tool.name, exclusive=True, read_only=False):
            result = json.loads(await tool.execute("morning"))
        assert control.ownership is not None
        assert not control.begin_generic_delivery(channel="telegram", chat_id=target)
    if success:
        assert result["status"] == "sent"
        assert collected == [1]
        assert len(posts) == 1 and posts[0]["chat_id"] == "123"
        assert DeliveryLedger(str(db_path)).list()[0]["state"] == "sent"
    else:
        assert result == {"status": "unavailable", "delivery_id": None}
        assert collected == posts == []
        assert not db_path.exists()


def test_camel_allowlist_takes_precedence_without_merging(config_file):
    config_file({"token": "synthetic", "allowFrom": ["999"], "allow_from": ["123"]})
    assert telegram_settings() == ("synthetic", ["999"])
    with pytest.raises(ValueError):
        authorized_target("123", sender="123")


def test_missing_channel_does_not_create_config(config_file):
    path = config_file({})
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        telegram_settings()
    assert path.read_text(encoding="utf-8") == "{}"
