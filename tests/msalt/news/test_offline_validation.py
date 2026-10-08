"""Issue #7 offline characterization: PASS proves observed behavior, not safety.

Only temporary SQLite and fake collectors/LLM/send boundaries are used. Schedule
assertions prove configuration only; they do not prove execution or receipt.
"""

import json
import socket
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from msalt.news import briefing, cli, collector
from msalt.storage import Storage

KST = ZoneInfo("Asia/Seoul")
COLLECTORS = ("RssCollector", "OfficialFeedCollector", "SearchCollector", "FallbackCollector")


def article(key, *, category="domestic", published_at="2026-10-08 06:00:00"):
    return {
        "source": "synthetic",
        "title": f"synthetic {key}",
        "url": f"https://example.invalid/{key}",
        "summary": "offline summary",
        "category": category,
        "published_at": published_at,
    }


@pytest.fixture(autouse=True)
def offline_boundaries(monkeypatch):
    """Fail closed on socket/DNS access and replace all four collector classes."""

    def blocked(*args, **kwargs):
        raise AssertionError("external network is forbidden in Issue #7 tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(cli, "_get_storage", blocked)
    fakes = []
    for name in COLLECTORS:
        fake = MagicMock(name=name)
        fake.collect_all.return_value = []
        monkeypatch.setattr(collector, name, MagicMock(return_value=fake))
        fakes.append(fake)
    # Even an accidental LLM-enabled path cannot instantiate the real client.
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("offline fake API failure")
    monkeypatch.setattr("openai.OpenAI", MagicMock(return_value=llm))
    return fakes, llm


@pytest.fixture
def storage(tmp_path, monkeypatch):
    db = Storage(str(tmp_path / "offline-news.db"))
    db.initialize()
    # Every CLI call uses this DB; MsaltConfig/default operational path is bypassed.
    monkeypatch.setattr(cli, "_get_storage", lambda: db)
    return db


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    def freeze(now):
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now.astimezone(tz) if tz else now.replace(tzinfo=None)

        monkeypatch.setattr(briefing, "datetime", FixedDatetime)

    freeze(datetime(2026, 10, 8, 20, tzinfo=KST))
    return freeze


def stored_urls(storage):
    return {a["url"] for a in storage.get_articles_since("2020-01-01")}


@pytest.mark.parametrize("scenario", ["success", "one_failure", "all_empty"])
def test_four_collector_paths_have_isolated_results(storage, offline_boundaries, scenario):
    fakes, _ = offline_boundaries
    tracking_id = storage.insert_tracked_item("offline-preserved", "number", "count", "08:00")
    storage.upsert_record(tracking_id, "2026-10-08", value_num=3, raw_input="synthetic")
    expected = set()
    for index, fake in enumerate(fakes):
        if scenario == "all_empty":
            continue
        if scenario == "one_failure" and index == 1:
            fake.collect_all.side_effect = RuntimeError("synthetic source failure")
        else:
            item = article(f"path-{index}")
            fake.collect_all.return_value = [item]
            expected.add(item["url"])
    count = collector.NewsCollector(storage).collect()
    assert count == len(expected)
    assert stored_urls(storage) == expected
    assert storage.get_tracked_item_by_name("offline-preserved")["id"] == tracking_id
    assert storage.get_records_for_item(tracking_id, 1, "2026-10-08")[0]["value_num"] == 3
    for fake in fakes:
        fake.collect_all.assert_called_once_with()


def test_source_and_database_url_duplicates_keep_first_payload(storage, offline_boundaries):
    fakes, _ = offline_boundaries
    existing = article("existing")
    storage.insert_article(**existing)
    shared = article("shared")
    fakes[0].collect_all.return_value = [shared, existing]
    replacement = dict(shared, title="later source replacement")
    fakes[1].collect_all.return_value = [replacement]
    fakes[2].collect_all.return_value = [article("new")]
    news = collector.NewsCollector(storage)
    assert news.collect() == 2
    assert news.collect() == 0
    rows = storage.get_articles_since("2020-01-01")
    assert len(rows) == 3
    assert next(a for a in rows if a["url"] == shared["url"])["title"] == shared["title"]


def test_insert_failure_commits_prefix_and_aborts_rest_characterization(
    storage, offline_boundaries
):
    """Known failure boundary: partial persistence is not an atomic/safety PASS."""
    fakes, _ = offline_boundaries
    first, failed, last = [article(key) for key in ("first", "failed", "last")]
    fakes[0].collect_all.return_value = [first, failed, last]
    with sqlite3.connect(storage.db_path) as conn:
        conn.execute("""CREATE TRIGGER reject_article BEFORE INSERT ON news_articles
                        WHEN NEW.url = 'https://example.invalid/failed'
                        BEGIN SELECT RAISE(ABORT, 'synthetic insert failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic insert failure"):
        collector.NewsCollector(storage).collect()
    reopened = Storage(storage.db_path)
    assert stored_urls(reopened) == {first["url"]}
    assert last["url"] not in stored_urls(reopened)


@pytest.mark.parametrize(
    "time_of_day,hour,since",
    [
        ("morning", 7, "2026-10-07 10:00:00"),
        ("afternoon", 14, "2026-10-07 22:00:00"),
        ("evening", 20, "2026-10-08 05:00:00"),
    ],
)
def test_kst_schedule_query_boundary_and_exclusions(
    storage, frozen_clock, time_of_day, hour, since
):
    now = datetime(2026, 10, 8, hour, tzinfo=KST)
    frozen_clock(now)
    assert briefing._briefing_since_utc(time_of_day) == since
    before = (datetime.fromisoformat(since) - timedelta(seconds=1)).isoformat(sep=" ")
    after = (datetime.fromisoformat(since) + timedelta(seconds=1)).isoformat(sep=" ")
    samples = [
        article("at-boundary", published_at=since),
        article("after-boundary", published_at=after),
        article("before-boundary", published_at=before),
        article("old", published_at="2021-01-01 00:00:00"),
        article("missing", published_at=None),
        article("already-briefed", published_at=after),
    ]
    for item in samples:
        storage.insert_article(**item)
    storage.mark_articles_briefed([samples[-1]["url"]], "previous")
    gen = briefing.BriefingGenerator(storage, use_llm=False)
    selected = gen.get_articles_for_briefing(since_date=since)
    assert {a["url"] for a in selected} == {samples[0]["url"], samples[1]["url"]}
    text = gen.format_briefing(time_of_day, mark_as_briefed=False)
    assert samples[0]["url"] in text and samples[1]["url"] in text
    assert all(a["url"] not in text for a in samples[2:])


def test_category_cap_marks_only_rendered_articles(storage):
    items = []
    for category in briefing.CATEGORY_ORDER:
        for index in range(12):
            item = article(
                f"{category}-{index}",
                category=category,
                published_at=f"2026-10-08 06:00:{index:02d}",
            )
            storage.insert_article(**item)
            items.append(item)
    gen = briefing.BriefingGenerator(storage, use_llm=False)
    text = gen.format_briefing("evening")
    rendered = {
        line.strip().removeprefix("원문: ")
        for line in text.splitlines()
        if line.strip().startswith("원문: ")
    }
    expected = {a["url"] for a in items if int(a["url"].rsplit("-", 1)[1]) >= 2}
    assert rendered == expected
    assert len(rendered) == 30
    assert storage.get_briefed_article_urls([a["url"] for a in items]) == expected
    assert {a["url"] for a in gen.get_articles_for_briefing(since_date="2026-10-08 05:00:00")} == {
        a["url"] for a in items
    } - expected


@pytest.mark.parametrize("failure", ["api_error", "timeout", "empty_response"])
def test_mock_llm_failure_falls_back_and_marks_plain_output(storage, offline_boundaries, failure):
    _, llm = offline_boundaries
    if failure == "timeout":
        import httpx
        from openai import APITimeoutError

        llm.chat.completions.create.side_effect = APITimeoutError(
            request=httpx.Request("POST", "https://example.invalid/llm")
        )
    elif failure == "empty_response":
        llm.chat.completions.create.side_effect = None
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="   "))]
        llm.chat.completions.create.return_value = response
    item = article("llm-fallback")
    storage.insert_article(**item)
    text = briefing.BriefingGenerator(storage).format_briefing("evening")
    assert f"   원문: {item['url']}" in text
    assert item["title"] in text
    llm.chat.completions.create.assert_called_once()
    assert storage.get_briefed_article_urls([item["url"]]) == {item["url"]}


def test_plain_mode_makes_no_llm_call(storage, offline_boundaries):
    _, llm = offline_boundaries
    item = article("plain")
    storage.insert_article(**item)
    text = briefing.BriefingGenerator(storage, use_llm=False).format_briefing("evening")
    assert item["url"] in text
    llm.chat.completions.create.assert_not_called()


def test_generated_state_survives_fake_failed_send_and_suppresses_restart_retry(storage):
    """Characterizes loss after generation; fake send is not real Telegram validation."""
    item = article("undelivered")
    storage.insert_article(**item)
    text = briefing.BriefingGenerator(storage, use_llm=False).format_briefing("evening")
    observed = []

    def fake_failed_send(payload):
        # A new Storage sees durable state before any send result is available.
        observed.append(Storage(storage.db_path).get_briefed_article_urls([item["url"]]))
        assert item["url"] in payload
        raise RuntimeError("synthetic send failure")

    with pytest.raises(RuntimeError, match="synthetic send failure"):
        fake_failed_send(text)
    assert observed == [{item["url"]}]
    restarted = briefing.BriefingGenerator(Storage(storage.db_path), use_llm=False)
    assert restarted.get_articles_for_briefing(since_date="2026-10-08 05:00:00") == []
    assert "수집된 뉴스가 없습니다" in restarted.format_briefing("evening")


def test_mark_failure_returns_no_text_and_restart_retry_is_available(storage):
    item = article("mark-failure")
    storage.insert_article(**item)
    with sqlite3.connect(storage.db_path) as conn:
        conn.execute("""CREATE TRIGGER reject_mark BEFORE INSERT ON news_briefed_articles
                        BEGIN SELECT RAISE(ABORT, 'synthetic mark failure'); END""")
    returned = []
    with pytest.raises(sqlite3.IntegrityError, match="synthetic mark failure"):
        returned.append(
            briefing.BriefingGenerator(storage, use_llm=False).format_briefing("evening")
        )
    assert returned == []
    reopened = Storage(storage.db_path)
    assert reopened.get_briefed_article_urls([item["url"]]) == set()
    gen = briefing.BriefingGenerator(reopened, use_llm=False)
    assert [a["url"] for a in gen.get_articles_for_briefing(since_date="2026-10-08 05:00:00")] == [
        item["url"]
    ]
    with sqlite3.connect(storage.db_path) as conn:
        conn.execute("DROP TRIGGER reject_mark")
    assert item["url"] in gen.format_briefing("evening")
    assert reopened.get_briefed_article_urls([item["url"]]) == {item["url"]}


def test_collect_then_cli_briefing_collects_all_four_paths_twice(storage, offline_boundaries):
    """Characterizes the skill's two-command sequence, not real remote call cost."""
    fakes, _ = offline_boundaries
    for index, fake in enumerate(fakes):
        fake.collect_all.return_value = [article(f"cli-{index}")]
    assert "4건" in cli.run_collect()
    text = cli.run_briefing("evening")
    assert len(stored_urls(storage)) == 4
    assert all(article(f"cli-{i}")["url"] in text for i in range(4))
    for fake in fakes:
        assert fake.collect_all.call_count == 2


def test_keyword_search_includes_old_articles_and_over_ten_without_marking(storage):
    """Current search has a 2020 lower bound and no ten-result cap."""
    included = []
    for index in range(12):
        item = article(f"search-{index}", published_at=f"2021-01-{index + 1:02d} 00:00:00")
        # Check title and summary matches, case insensitivity, and no briefed exclusion.
        item["title"] = f"ECONOMY old {index}" if index % 2 else f"other old {index}"
        item["summary"] = "economy in summary" if not index % 2 else "other"
        storage.insert_article(**item)
        included.append(item)
    excluded = article("too-old", published_at="2019-12-31 23:59:59")
    excluded["title"] = "economy before lower bound"
    storage.insert_article(**excluded)
    storage.insert_article(**dict(article("unmatched"), title="unrelated"))
    storage.mark_articles_briefed([included[0]["url"]], "prior")
    text = cli.run_search("Economy")
    assert "(12건)" in text
    assert all(item["url"] in text for item in included)
    assert excluded["url"] not in text
    assert article("unmatched")["url"] not in text
    assert storage.get_briefed_article_urls([item["url"] for item in included]) == {
        included[0]["url"]
    }


def test_three_news_cron_schedules_configuration_only():
    path = Path(__file__).resolve().parents[3] / "msalt" / "workspace" / "cron" / "jobs.json"
    jobs = json.loads(path.read_text(encoding="utf-8"))["jobs"]
    news = {job["id"]: job for job in jobs if job["id"].startswith("msalt-news-briefing-")}
    assert set(news) == {
        f"msalt-news-briefing-{slot}" for slot in ("morning", "afternoon", "evening")
    }
    for slot, hour in (("morning", 7), ("afternoon", 14), ("evening", 20)):
        job = news[f"msalt-news-briefing-{slot}"]
        assert job["enabled"] is True
        assert job["schedule"] == {"kind": "cron", "expr": f"0 {hour} * * *", "tz": "Asia/Seoul"}
        assert job["payload"]["deliver"] is True
        assert job["payload"]["channel"] == "telegram"
