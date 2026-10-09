"""Persistent, fenced news delivery state. Network work never holds a DB lock."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

LIMITS = {
    "generations": 24,
    "summaries": 72,
    "deliveries": 25,
    "parts": 100,
    "posts": 300,
    "manual_retries": 1,
}
LEASE_SECONDS = 600
RUN_SECONDS = 300


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_payload(text):
    """Keep lines/URLs whole; plain Unicode text plus stable part headers <=3500."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty payload")
    text.encode("utf-8")  # reject lone surrogates before any HTTP
    if len(text) <= 3500:
        return [text]
    chunks, chunk = [], ""
    for line in text.splitlines(keepends=True):
        if len(line) > 3494:
            if chunk:
                chunks.append(chunk)
                chunk = ""
            for token in re.split(r"(https?://\S+)", line):
                if token.startswith(("https://", "http://")):
                    if len(token) > 3494:
                        raise ValueError("URL exceeds part limit")
                    if len(chunk) + len(token) > 3494:
                        chunks.append(chunk)
                        chunk = ""
                    chunk += token
                else:
                    while token:
                        take = min(3494 - len(chunk), len(token))
                        chunk += token[:take]
                        token = token[take:]
                        if len(chunk) == 3494:
                            chunks.append(chunk)
                            chunk = ""
            continue
        if len(chunk) + len(line) > 3494:
            chunks.append(chunk)
            chunk = ""
        chunk += line
    if chunk:
        chunks.append(chunk)
    if len(chunks) > 4:
        raise ValueError("payload exceeds four parts")
    return [f"[{i}/{len(chunks)}]\n{part}" for i, part in enumerate(chunks, 1)]


class DeliveryLedger:
    def __init__(self, db_path, *, clock=time.time):
        self.db_path = str(db_path)
        self.clock = clock

    @contextmanager
    def _tx(self):
        # A missing database must be initialized explicitly by the caller.
        conn = sqlite3.connect(
            Path(self.db_path).resolve().as_uri() + "?mode=rw", uri=True, timeout=10
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("BEGIN IMMEDIATE")
            from msalt.news.delivery_schema import validate

            validate(conn)
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def _read(self):
        conn = sqlite3.connect(Path(self.db_path).resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _budget(conn, name, count=1):
        conn.execute("INSERT OR IGNORE INTO news_delivery_budget VALUES (?,0)", (name,))
        cur = conn.execute(
            "UPDATE news_delivery_budget SET used=used+? WHERE name=? AND used+?<=?",
            (count, name, count, LIMITS[name]),
        )
        if cur.rowcount != 1:
            raise ValueError(f"{name} quota exhausted")

    def list(self):
        if not Path(self.db_path).exists():
            return []
        with self._read() as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='news_deliveries'").fetchone():
                return []
            return [
                dict(r) for r in c.execute("SELECT * FROM news_deliveries ORDER BY created_at DESC")
            ]

    def show(self, delivery_id):
        if not Path(self.db_path).exists():
            raise ValueError("delivery not found (database absent)")
        with self._read() as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='news_deliveries'").fetchone():
                raise ValueError("delivery not found (database not migrated)")
            row = c.execute(
                "SELECT * FROM news_deliveries WHERE delivery_id=?", (delivery_id,)
            ).fetchone()
            if row is None:
                raise ValueError("delivery not found")
            result = dict(row)
            result["parts"] = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM news_delivery_parts WHERE delivery_id=? ORDER BY part_no",
                    (delivery_id,),
                )
            ]
            result["attempt_log"] = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM news_delivery_attempts WHERE delivery_id=? ORDER BY created_at,attempt_id",
                    (delivery_id,),
                )
            ]
            return result

    def reserved_urls(self):
        if not Path(self.db_path).exists():
            return set()
        with self._read() as c:
            if not c.execute(
                "SELECT 1 FROM sqlite_master WHERE name='news_delivery_articles'"
            ).fetchone():
                return set()
            return {
                r[0]
                for r in c.execute("SELECT article_url FROM news_delivery_articles WHERE active=1")
            }

    def begin(self, target, thread, kst_date, slot):
        if slot not in ("morning", "afternoon", "evening"):
            raise ValueError("invalid slot")
        now, owner, ident = self.clock(), uuid.uuid4().hex, uuid.uuid4().hex
        with self._tx() as c:
            old = c.execute(
                "SELECT * FROM news_deliveries WHERE target=? AND thread=? AND kst_date=? AND slot=?",
                (target, thread, kst_date, slot),
            ).fetchone()
            if old:
                return dict(old), False
            self._budget(c, "generations")
            self._budget(c, "deliveries")
            c.execute(
                "INSERT INTO news_deliveries (delivery_id,target,thread,kst_date,slot,created_at,updated_at,state,owner,lease_until,generation_started) VALUES (?,?,?,?,?,?,?,'generating',?,?,?)",
                (ident, target, thread, kst_date, slot, now, now, owner, now + LEASE_SECONDS, now),
            )
            self._audit(c, ident, None, owner, "generation_claim")
            return dict(
                c.execute("SELECT * FROM news_deliveries WHERE delivery_id=?", (ident,)).fetchone()
            ), True

    def _fence(self, c, ident, owner, state, *, receipt=False):
        row = c.execute("SELECT * FROM news_deliveries WHERE delivery_id=?", (ident,)).fetchone()
        if (
            row is None
            or row["state"] != state
            or row["owner"] != owner
            or (not receipt and row["lease_until"] <= self.clock())
        ):
            raise ValueError("stale delivery owner")
        started = row["generation_started"] if state == "generating" else row["send_started"]
        if not receipt and self.clock() >= started + RUN_SECONDS:
            raise ValueError("run deadline exceeded")
        return row

    def check_generation(self, ident, owner):
        with self._tx() as c:
            self._fence(c, ident, owner, "generating")

    def reserve(self, ident, owner, urls):
        selected = []
        with self._tx() as c:
            self._fence(c, ident, owner, "generating")
            for url in dict.fromkeys(urls):
                if c.execute(
                    "SELECT 1 FROM news_briefed_articles WHERE article_url=?", (url,)
                ).fetchone():
                    continue
                cur = c.execute(
                    "INSERT OR IGNORE INTO news_delivery_articles VALUES (?,?,1)", (ident, url)
                )
                if (
                    cur.rowcount
                    or c.execute(
                        "SELECT 1 FROM news_delivery_articles WHERE delivery_id=? AND article_url=? AND active=1",
                        (ident, url),
                    ).fetchone()
                ):
                    selected.append(url)
        return selected

    def reserve_summary(self, ident, owner):
        with self._tx() as c:
            self._fence(c, ident, owner, "generating")
            count = c.execute(
                "SELECT COUNT(*) FROM news_delivery_attempts WHERE delivery_id=? AND owner=? AND outcome='summary_claim'",
                (ident, owner),
            ).fetchone()[0]
            if count >= 3:
                raise ValueError("generation summary quota exhausted")
            self._budget(c, "summaries")
            self._audit(c, ident, None, owner, "summary_claim")

    def prepare(self, ident, owner, payload, *, empty=False):
        from msalt.news.briefing import GeneratedBriefing

        if not isinstance(payload, GeneratedBriefing):
            raise ValueError("an immutable generated snapshot is required")
        urls = tuple(dict.fromkeys(payload.urls))
        if urls != payload.urls or any(url not in payload.text for url in urls):
            raise ValueError("snapshot URLs do not match rendered text")
        empty = not urls
        payload = payload.text
        parts = split_payload(payload)
        with self._tx() as c:
            self._fence(c, ident, owner, "generating")
            reserved = {
                r[0]
                for r in c.execute(
                    "SELECT article_url FROM news_delivery_articles WHERE delivery_id=? AND active=1",
                    (ident,),
                )
            }
            if not set(urls).issubset(reserved):
                raise ValueError("snapshot contains unreserved articles")
            c.execute(
                "UPDATE news_deliveries SET snapshot_urls=?,snapshot_hash=? WHERE delivery_id=?",
                (json.dumps(urls), digest(json.dumps([payload, urls])), ident),
            )
            self._budget(c, "parts", len(parts))
            c.execute(
                "UPDATE news_deliveries SET is_empty=? WHERE delivery_id=?", (int(empty), ident)
            )
            c.executemany(
                "INSERT INTO news_delivery_parts (delivery_id,part_no,text,hash) VALUES (?,?,?,?)",
                [(ident, i, text, digest(text)) for i, text in enumerate(parts, 1)],
            )
            c.execute(
                "UPDATE news_deliveries SET state=?,payload=?,payload_hash=?,updated_at=?,owner=NULL,lease_until=NULL WHERE delivery_id=?",
                ("empty" if empty else "prepared", payload, digest(payload), self.clock(), ident),
            )

    def fail_generation(self, ident, owner, error="generation_failed"):
        with self._tx() as c:
            cur = c.execute(
                "UPDATE news_deliveries SET state='failed',error=?,updated_at=?,owner=NULL,lease_until=NULL WHERE delivery_id=? AND owner=? AND state='generating'",
                (error, self.clock(), ident, owner),
            )
            if cur.rowcount != 1:
                raise ValueError("stale delivery owner")
            self._audit(c, ident, None, owner, "generation_failed", error)

    def regenerate(self, ident):
        with self._tx() as c:
            row = c.execute(
                "SELECT * FROM news_deliveries WHERE delivery_id=?", (ident,)
            ).fetchone()
            if row is None or row["state"] != "failed" or row["payload"] is not None:
                raise ValueError("only failed generation without payload can regenerate")
            self._budget(c, "generations")
            owner, now = uuid.uuid4().hex, self.clock()
            c.execute(
                "UPDATE news_deliveries SET state='generating',generation=generation+1,generation_started=?,owner=?,lease_until=?,updated_at=?,error=NULL WHERE delivery_id=?",
                (now, owner, now + LEASE_SECONDS, now, ident),
            )
            self._audit(c, ident, None, owner, "manual_regeneration", manual=True)
            return dict(
                c.execute("SELECT * FROM news_deliveries WHERE delivery_id=?", (ident,)).fetchone()
            )

    def claim_send(self, ident, *, manual=False, confirm_uncertain=False):
        now, owner = self.clock(), uuid.uuid4().hex
        with self._tx() as c:
            row = c.execute(
                "SELECT * FROM news_deliveries WHERE delivery_id=?", (ident,)
            ).fetchone()
            if row is None or row["payload"] is None:
                raise ValueError("no saved payload")
            allowed = (
                ("prepared", "empty") if not manual else ("prepared", "empty", "failed", "unknown")
            )
            if row["state"] not in allowed:
                return None
            if (
                row["state"] == "empty"
                and c.execute(
                    "SELECT 1 FROM news_delivery_parts WHERE delivery_id=? AND message_id IS NULL",
                    (ident,),
                ).fetchone()
                is None
            ):
                return None
            if row["state"] == "unknown" and not confirm_uncertain:
                raise ValueError("unknown requires confirm-uncertain")
            if manual:
                self._budget(c, "manual_retries")
            c.execute(
                "UPDATE news_deliveries SET state='sending',owner=?,lease_until=?,send_started=?,updated_at=?,manual=? WHERE delivery_id=?",
                (
                    owner,
                    now + LEASE_SECONDS,
                    now if manual else row["generation_started"],
                    now,
                    int(manual),
                    ident,
                ),
            )
            self._audit(
                c, ident, None, owner, "manual_retry" if manual else "send_claim", manual=manual
            )
            return owner

    def claim_part(self, ident, owner, part_no):
        with self._tx() as c:
            row = self._fence(c, ident, owner, "sending")
            self.validate_snapshot(ident)
            part = c.execute(
                "SELECT * FROM news_delivery_parts WHERE delivery_id=? AND part_no=?",
                (ident, part_no),
            ).fetchone()
            if part is None or part["message_id"] is not None or part["state"] == "sending":
                raise ValueError("part cannot be claimed")
            if not row["manual"] and part["attempts"] >= 3:
                raise ValueError("attempt quota exhausted")
            if (
                row["manual"]
                and c.execute(
                    "SELECT 1 FROM news_delivery_attempts WHERE delivery_id=? AND owner=? AND part_no=?",
                    (ident, owner, part_no),
                ).fetchone()
            ):
                raise ValueError("manual retry allows one attempt per unfinished part")
            self._budget(c, "posts")
            attempt = self._audit(c, ident, part_no, owner, "sending", manual=bool(row["manual"]))
            c.execute(
                "UPDATE news_delivery_parts SET state='sending',attempts=attempts+1 WHERE delivery_id=? AND part_no=?",
                (ident, part_no),
            )
            return attempt

    @staticmethod
    def _attempt(c, ident, owner, part_no, attempt):
        row = c.execute(
            "SELECT 1 FROM news_delivery_attempts a JOIN news_delivery_parts p ON p.delivery_id=a.delivery_id AND p.part_no=a.part_no WHERE a.attempt_id=? AND a.delivery_id=? AND a.part_no=? AND a.owner=? AND a.outcome='sending' AND p.state='sending' AND p.message_id IS NULL",
            (attempt, ident, part_no, owner),
        ).fetchone()
        if row is None:
            raise ValueError("attempt is not current")

    def validate_snapshot(self, ident):
        row = self.show(ident)
        if row["schema_version"] != 1 or row["payload_hash"] != digest(row["payload"]):
            raise ValueError("invalid snapshot")
        urls = json.loads(row["snapshot_urls"])
        if row["snapshot_hash"] != digest(json.dumps([row["payload"], urls])):
            raise ValueError("invalid article manifest hash")
        with self._read() as c:
            reserved = {
                r[0]
                for r in c.execute(
                    "SELECT article_url FROM news_delivery_articles WHERE delivery_id=?", (ident,)
                )
            }
        if not set(urls).issubset(reserved) or any(url not in row["payload"] for url in urls):
            raise ValueError("invalid snapshot article association")
        expected = split_payload(row["payload"])
        if len(expected) != len(row["parts"]):
            raise ValueError("invalid parts")
        for number, (text, part) in enumerate(zip(expected, row["parts"]), 1):
            if part["part_no"] != number or part["text"] != text or part["hash"] != digest(text):
                raise ValueError("invalid part snapshot")
        return row

    def ack(self, ident, owner, part_no, attempt, message_id):
        if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id <= 0:
            raise ValueError("invalid message ID")
        with self._tx() as c:
            self._fence(c, ident, owner, "sending", receipt=True)
            self._attempt(c, ident, owner, part_no, attempt)
            cur = c.execute(
                "UPDATE news_delivery_parts SET state='sent',message_id=?,ack_at=? WHERE delivery_id=? AND part_no=? AND state='sending' AND message_id IS NULL",
                (message_id, self.clock(), ident, part_no),
            )
            if cur.rowcount != 1:
                raise ValueError("part not in flight")
            c.execute(
                "UPDATE news_delivery_attempts SET outcome='api_ack',updated_at=? WHERE attempt_id=? AND owner=? AND outcome='sending'",
                (self.clock(), attempt, owner),
            )

    def reject(self, ident, owner, part_no, attempt, error, *, unknown=False):
        with self._tx() as c:
            self._fence(c, ident, owner, "sending")
            self._attempt(c, ident, owner, part_no, attempt)
            state = "unknown" if unknown else "failed"
            c.execute(
                "UPDATE news_delivery_parts SET state=? WHERE delivery_id=? AND part_no=? AND message_id IS NULL",
                (state, ident, part_no),
            )
            c.execute(
                "UPDATE news_delivery_attempts SET outcome=?,error=?,updated_at=? WHERE attempt_id=? AND owner=?",
                (state, error, self.clock(), attempt, owner),
            )

    def finish_failure(self, ident, owner, error, *, unknown=False):
        with self._tx() as c:
            row = c.execute(
                "SELECT * FROM news_deliveries WHERE delivery_id=?", (ident,)
            ).fetchone()
            if row is None or row["owner"] != owner or row["state"] != "sending":
                return
            partial = c.execute(
                "SELECT 1 FROM news_delivery_parts WHERE delivery_id=? AND message_id IS NOT NULL",
                (ident,),
            ).fetchone()
            state = "unknown" if unknown or partial else "failed"
            c.execute(
                "UPDATE news_deliveries SET state=?,error=?,owner=NULL,lease_until=NULL,updated_at=? WHERE delivery_id=?",
                (state, error, self.clock(), ident),
            )
            c.execute(
                "UPDATE news_delivery_parts SET state='unknown' WHERE delivery_id=? AND state='sending'",
                (ident,),
            )
            c.execute(
                "UPDATE news_delivery_attempts SET outcome='unknown',error=?,updated_at=? WHERE delivery_id=? AND outcome='sending'",
                (error, self.clock(), ident),
            )

    def finish(self, ident, owner):
        with self._tx() as c:
            row = self._fence(c, ident, owner, "sending")
            self.validate_snapshot(ident)
            parts = c.execute(
                "SELECT * FROM news_delivery_parts WHERE delivery_id=?", (ident,)
            ).fetchall()
            if not parts or any(p["message_id"] is None or p["state"] != "sent" for p in parts):
                raise ValueError("all parts require API ACK")
            c.executemany(
                "INSERT OR IGNORE INTO news_briefed_articles (article_url,briefing_label) VALUES (?,?)",
                [
                    (url, row["kst_date"] + ":" + row["slot"])
                    for url in json.loads(row["snapshot_urls"])
                ],
            )
            final_state = "empty" if row["is_empty"] else "sent"
            c.execute(
                "UPDATE news_deliveries SET state=?,error=NULL,owner=NULL,lease_until=NULL,updated_at=? WHERE delivery_id=?",
                (final_state, self.clock(), ident),
            )
            c.executemany(
                "UPDATE news_delivery_articles SET active=0 WHERE delivery_id=? AND article_url=?",
                [(ident, url) for url in json.loads(row["snapshot_urls"])],
            )

    def resolve(self, ident, *, received=False, abandon=False):
        if received == abandon:
            raise ValueError("select received or abandon")
        with self._tx() as c:
            row = c.execute(
                "SELECT * FROM news_deliveries WHERE delivery_id=?", (ident,)
            ).fetchone()
            if row is None or row["state"] not in ("unknown", "failed", "prepared", "empty"):
                raise ValueError("delivery cannot be resolved")
            state = "received" if received else "abandoned"
            c.execute(
                "UPDATE news_deliveries SET state=?,owner=NULL,lease_until=NULL,updated_at=? WHERE delivery_id=?",
                (state, self.clock(), ident),
            )
            # Keep reservation: human evidence/abandon excludes automatic reselection,
            # without forging an API ACK or modifying historical briefed rows.
            self._audit(c, ident, None, None, "human_" + state, manual=True)

    def recover(self):
        now = self.clock()
        with self._tx() as c:
            rows = c.execute(
                "SELECT * FROM news_deliveries WHERE state IN ('generating','sending') AND lease_until<=?",
                (now,),
            ).fetchall()
            for row in rows:
                state = "unknown" if row["state"] == "sending" else "failed"
                c.execute(
                    "UPDATE news_deliveries SET state=?,owner=NULL,lease_until=NULL,error=?,updated_at=? WHERE delivery_id=?",
                    (state, "lease_expired", now, row["delivery_id"]),
                )
                c.execute(
                    "UPDATE news_delivery_parts SET state='unknown' WHERE delivery_id=? AND state='sending'",
                    (row["delivery_id"],),
                )
                c.execute(
                    "UPDATE news_delivery_attempts SET outcome='unknown',error='lease_expired',updated_at=? WHERE delivery_id=? AND outcome='sending'",
                    (now, row["delivery_id"]),
                )

    def _audit(self, c, ident, part, owner, outcome, error=None, *, manual=False):
        attempt = uuid.uuid4().hex
        c.execute(
            "INSERT INTO news_delivery_attempts VALUES (?,?,?,?,?,?,?,?,?)",
            (attempt, ident, part, self.clock(), self.clock(), owner, outcome, error, int(manual)),
        )
        return attempt
