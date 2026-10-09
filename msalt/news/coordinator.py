"""One bounded action: collect once, freeze exact URLs, then send saved parts."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from datetime import datetime

from msalt.news.briefing import (
    BRIEFING_LABELS,
    BRIEFING_TZ,
    CATEGORY_ORDER,
    MAX_ARTICLES_PER_CATEGORY,
    BriefingGenerator,
    _briefing_since_utc,
)
from msalt.news.collector import NewsCollector
from msalt.news.delivery import RUN_SECONDS, DeliveryLedger
from msalt.news.sender import DeliverySender
from msalt.storage import Storage


def generate_snapshot(*, db_path, ident, owner, slot, deadline=None, collector=None, use_llm=True):
    """Runs in an owned child process; no Telegram capability is passed to it."""
    ledger = DeliveryLedger(db_path)
    storage = Storage(db_path)
    deadline = deadline if deadline is not None else time.monotonic() + RUN_SECONDS
    ledger.check_generation(ident, owner)
    if time.monotonic() >= deadline:
        raise TimeoutError("action deadline")
    (collector or NewsCollector(storage)).collect()
    ledger.check_generation(ident, owner)
    generator = BriefingGenerator(
        storage,
        use_llm=use_llm,
        before_summary=lambda: ledger.reserve_summary(ident, owner),
        deadline=deadline,
    )
    articles = generator.get_articles_for_briefing(
        since_date=_briefing_since_utc(slot), exclude_reserved=False
    )
    selected = []
    # Reserve up to the original category cap, filling race losers in that category.
    for category in CATEGORY_ORDER:
        count = 0
        for article in (a for a in articles if a["category"] == category):
            if count == MAX_ARTICLES_PER_CATEGORY:
                break
            if ledger.reserve(ident, owner, [article["url"]]):
                selected.append(article)
                count += 1
    result = generator.render_articles(selected, slot)
    if time.monotonic() >= deadline:
        raise TimeoutError("action deadline")
    ledger.prepare(ident, owner, result)


def _generation_child(kwargs):
    # Source/SDK exceptions can contain request URLs or credentials. The child
    # persists only a fixed classification; it never publishes raw tracebacks.
    logging.disable(logging.CRITICAL)
    try:
        generate_snapshot(**kwargs)
    except BaseException:
        try:
            DeliveryLedger(kwargs["db_path"]).fail_generation(kwargs["ident"], kwargs["owner"])
        except Exception:
            pass  # Original durable generating claim recovers after lease expiry.


async def bounded_generation(**kwargs):
    """Terminate and join on deadline/cancellation: no orphan paid-call worker."""
    deadline = kwargs["deadline"]
    process = multiprocessing.get_context("spawn").Process(target=_generation_child, args=(kwargs,))
    process.start()
    try:
        while process.is_alive():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("action deadline")
            await asyncio.sleep(min(0.05, remaining))
        process.join()
        if process.exitcode != 0:
            raise RuntimeError("generation worker unavailable")
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
        process.close()


class NewsDeliveryCoordinator:
    def __init__(self, db_path, *, post, generation=bounded_generation):
        self.db_path = str(db_path)
        self.ledger = DeliveryLedger(db_path)
        self.post = post
        self.generation = generation

    async def run(self, target, thread, slot, *, regenerate=None):
        if slot not in BRIEFING_LABELS:
            raise ValueError("invalid slot")
        deadline = time.monotonic() + RUN_SECONDS
        self.ledger.recover()
        if regenerate:
            row = self.ledger.regenerate(regenerate)
            if (row["target"], row["thread"], row["slot"]) != (target, thread, slot):
                raise ValueError("saved target mismatch")
            owned = True
        else:
            row, owned = self.ledger.begin(
                target, thread, datetime.now(BRIEFING_TZ).date().isoformat(), slot
            )
        ident = row["delivery_id"]
        if not owned:
            return {"status": row["state"], "delivery_id": ident}
        try:
            await self.generation(
                db_path=self.db_path, ident=ident, owner=row["owner"], slot=slot, deadline=deadline
            )
            detail = self.ledger.show(ident)
            if detail["state"] not in ("prepared", "empty"):
                return {"status": detail["state"], "delivery_id": ident}
            state = await DeliverySender(self.ledger, post=self.post).send(ident, deadline=deadline)
            return {"status": state, "delivery_id": ident}
        except asyncio.CancelledError:
            self._fail_generation(ident, row["owner"])
            raise
        except Exception:
            self._fail_generation(ident, row["owner"])
            return {"status": "unavailable", "delivery_id": ident}

    def _fail_generation(self, ident, owner):
        try:
            if self.ledger.show(ident)["state"] == "generating":
                self.ledger.fail_generation(ident, owner)
        except Exception:
            pass  # No further external work; persisted lease is operator-visible.
