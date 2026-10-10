"""Root delivery integration: real SQLite and runtime; external services are fake."""

import socket
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from msalt.news.delivery import DeliveryLedger
from msalt.storage import Storage


@pytest.fixture(autouse=True)
async def offline(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("external network forbidden")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture
def storage(tmp_path):
    s = Storage(str(tmp_path / "msalt.db"))
    s.initialize()
    return s


def seed(s, number=1):
    for i in range(number):
        s.insert_article(
            "test",
            f"Title {i}",
            f"https://example.test/{i}",
            "Summary",
            "domestic",
            "2099-01-01 00:00:00",
        )


def test_generated_snapshot_exact_urls_and_reservation_exclusion(storage):
    from msalt.news.briefing import BriefingGenerator, GeneratedBriefing

    seed(storage, 12)
    ledger_instance = DeliveryLedger(storage.db_path)
    row, _ = ledger_instance.begin("123", "", "2026-10-09", "morning")
    ident, owner = row["delivery_id"], row["owner"]
    ledger_instance.reserve(ident, owner, ["https://example.test/11"])
    generator = BriefingGenerator(storage, use_llm=False)
    assert "https://example.test/11" not in generator.format_briefing()
    selected = generator.get_articles_for_briefing(exclude_reserved=False)[:10]
    result = generator.render_articles(selected, "morning")
    assert isinstance(result, GeneratedBriefing)
    assert len(result.urls) == 10
    with pytest.raises(ValueError):
        ledger_instance.prepare(ident, owner, result)
    ledger_instance.reserve(ident, owner, result.urls)
    ledger_instance.prepare(ident, owner, result)
    assert ledger_instance.validate_snapshot(ident)["payload"] == result.text
    with sqlite3.connect(storage.db_path) as c:
        c.execute(
            "UPDATE news_delivery_articles SET article_url='https://example.test/tampered' WHERE article_url=?",
            (result.urls[0],),
        )
    with pytest.raises(ValueError):
        ledger_instance.validate_snapshot(ident)


@pytest.mark.parametrize("slot", ["morning", "afternoon", "evening"])
async def test_coordinator_one_collect_duplicate_no_work(storage, slot):
    from msalt.news.coordinator import NewsDeliveryCoordinator, generate_snapshot

    seed(storage, 2)
    collected = []

    class Collector:
        def collect(self):
            collected.append(1)

    async def generation(**kwargs):
        generate_snapshot(**kwargs, collector=Collector(), use_llm=False)

    posts = []

    async def post(payload):
        posts.append(payload)
        return 200, {"ok": True, "result": {"message_id": 5}}

    service = NewsDeliveryCoordinator(storage.db_path, post=post, generation=generation)
    first = await service.run("123", "", slot)
    second = await service.run("123", "", slot)
    assert first == second and first["status"] == "sent"
    assert len(collected) == 1 and len(posts) == 1
    assert storage.get_briefed_article_urls(
        ["https://example.test/0", "https://example.test/1"]
    ) == {"https://example.test/0", "https://example.test/1"}


async def test_summary_budget_reserved_before_model(storage, monkeypatch):
    from msalt.news.coordinator import generate_snapshot

    seed(storage)
    ledger_instance = DeliveryLedger(storage.db_path)
    row, _ = ledger_instance.begin("123", "", "2026-10-09", "morning")
    with sqlite3.connect(storage.db_path) as c:
        c.execute("INSERT INTO news_delivery_budget VALUES ('summaries',72)")
    calls = []
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(ValueError, match="quota"):
        generate_snapshot(
            db_path=storage.db_path,
            ident=row["delivery_id"],
            owner=row["owner"],
            slot="morning",
            collector=MagicMock(),
        )
    assert calls == []


async def test_tool_missing_runtime_or_scope_performs_no_work(tmp_path, monkeypatch):
    from msalt.news.reply_tool import NewsBriefingTool

    tool = NewsBriefingTool(tmp_path)
    assert "unsupported" in await tool.execute(time_of_day="morning")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("slot", ["morning", "afternoon", "evening"])
async def test_installed_tool_real_loop_claim_suppresses_copy(tmp_path, monkeypatch, slot):
    from importlib.metadata import entry_points

    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.events import InboundMessage
    from nanobot.bus.queue import MessageBus
    from nanobot.providers.base import GenerationSettings, LLMResponse, ToolCallRequest

    from msalt.news import reply_tool
    from msalt.news.coordinator import generate_snapshot

    eps = list(entry_points(group="nanobot.tools", name="news_briefing"))
    assert len(eps) == 1
    cls = eps[0].load()
    monkeypatch.setenv("TELEGRAM_USER_ID", "123")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "synthetic")
    monkeypatch.setattr(reply_tool, "telegram_settings", lambda: ("synthetic", ["123"]))
    s = Storage(str(tmp_path / "msalt.db"))
    s.initialize()
    seed(s)
    collections, posts = [], []

    class Collector:
        def collect(self):
            collections.append(1)

    async def generation(**kwargs):
        generate_snapshot(**kwargs, collector=Collector(), use_llm=False)

    async def post(payload):
        posts.append(payload)
        return 200, {"ok": True, "result": {"message_id": 9}}

    tool = cls(tmp_path, generation=generation, post=post, db_path=s.db_path)
    provider = MagicMock()
    provider.get_default_model.return_value = "offline"
    provider.generation = GenerationSettings()
    import json
    import re

    skill = (Path(__file__).resolve().parents[3] / "msalt/skills/news-briefing/SKILL.md").read_text(
        encoding="utf-8"
    )
    requests = []

    async def model(**kwargs):
        requests.append(1)
        assert len(requests) == 1
        examples = [json.loads(block) for block in re.findall(r"```json\s*\n(.*?)```", skill, re.S)]
        chosen = next(item for item in examples if item["arguments"]["time_of_day"] == slot)
        return LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest(id="news", name=chosen["name"], arguments=chosen["arguments"]),
                ToolCallRequest(id="copy", name="message", arguments={"content": "COPY"}),
            ],
        )

    provider.chat_stream_with_retry = model
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, model="offline")
    loop.tools.register(tool)
    sent = []

    async def send(message):
        sent.append(message)

    loop.tools.get("message").set_send_callback(send)
    assert (
        await loop._process_message(
            InboundMessage(
                channel="telegram",
                sender_id="123",
                chat_id="123",
                content="news",
                metadata={"message_thread_id": 7},
            ),
            ephemeral=True,
        )
        is None
    )
    assert collections == [1] and len(posts) == 1 and len(requests) == 1 and sent == []
    assert posts[0]["message_thread_id"] == 7
    assert DeliveryLedger(s.db_path).list()[0]["state"] == "sent"


def test_operator_status_does_not_create_or_seed(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from msalt import cli as root_cli
    from msalt.news import delivery_cli

    path = tmp_path / "없는 파일.db"
    monkeypatch.setattr(delivery_cli, "database_path", lambda: path)
    monkeypatch.setattr(root_cli, "_seed_if_missing", lambda: pytest.fail("status must not seed"))
    runner = CliRunner()
    result = runner.invoke(root_cli.app, ["news", "delivery", "list"])
    assert result.exit_code == 0 and "[]" in result.stdout
    result = runner.invoke(root_cli.app, ["news", "delivery", "show", "missing"])
    assert result.exit_code == 1 and "not found" in result.stdout
    assert not path.exists()


def test_preview_invalid_slot_has_zero_collection(monkeypatch):
    from msalt.news import cli

    calls = []
    monkeypatch.setattr(cli, "_get_storage", lambda: calls.append(1))
    with pytest.raises(ValueError):
        cli.run_briefing("invalid")
    assert calls == []


def test_operator_resolve_output_redacts_target_and_body(storage, monkeypatch, capsys):
    from msalt.news import delivery_cli
    from msalt.news.briefing import GeneratedBriefing

    ledger_instance = DeliveryLedger(storage.db_path)
    row, _ = ledger_instance.begin("123", "7", "2026-10-09", "morning")
    ledger_instance.prepare(
        row["delivery_id"], row["owner"], GeneratedBriefing("SECRET SAVED BODY", ())
    )
    monkeypatch.setattr(delivery_cli, "database_path", lambda: storage.db_path)
    assert delivery_cli.run_command(["resolve", row["delivery_id"], "--received"]) == 0
    assert delivery_cli.run_command(["show", row["delivery_id"]]) == 0
    out = capsys.readouterr().out
    assert "SECRET SAVED BODY" not in out and '"target"' not in out and '"thread"' not in out
    assert "human_received" in out
    assert ledger_instance.show(row["delivery_id"])["parts"][0]["message_id"] is None


def test_custom_workspace_keeps_canonical_legacy_database(tmp_path):
    from msalt.config import MsaltConfig
    from msalt.news.delivery_cli import database_path
    from msalt.news.reply_tool import NewsBriefingTool

    tool = NewsBriefingTool(tmp_path / "custom-agent-workspace")
    assert Path(tool.db_path) == database_path() == Path(MsaltConfig().db_path)
    assert not (tmp_path / "custom-agent-workspace" / "msalt.db").exists()
