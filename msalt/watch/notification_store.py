"""Watch delivery ledger. Payloads are private; reservations are never refunded."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from msalt.watch.evaluation_store import EvaluationStore, bounded
from msalt.watch.models import validate_positive_int

KST = timezone(timedelta(hours=9))
ELIGIBLE = "e.status='relevant' AND e.relevant=1 AND e.importance='high' AND w.active=1 AND w.deleted_at IS NULL AND w.revision=e.revision"


def migrate_notifications(conn):
    # Called only inside Storage.initialize's transaction. No commit/executescript.
    statements = [
        """CREATE TABLE IF NOT EXISTS watch_notification_settings (
            id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL CHECK(enabled IN (0,1)))""",
        "INSERT INTO watch_notification_settings VALUES(1,0) ON CONFLICT(id) DO NOTHING",
        """CREATE TABLE IF NOT EXISTS watch_notifications (
            delivery_id TEXT PRIMARY KEY, target_hash TEXT NOT NULL, target TEXT NOT NULL,
            slot_utc TEXT NOT NULL, kst_day TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('pending','sending','sent','rejected','unknown','cancelled')),
            payload TEXT NOT NULL, payload_hash TEXT NOT NULL, snapshot TEXT NOT NULL,
            owner_token TEXT, error_code TEXT, ack_message_id INTEGER,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(target_hash,slot_utc))""",
        """CREATE TABLE IF NOT EXISTS watch_notification_urls (
            target_hash TEXT NOT NULL, url TEXT NOT NULL,
            delivery_id TEXT REFERENCES watch_notifications(delivery_id),
            state TEXT NOT NULL CHECK(state IN ('available','pending','sending','sent','rejected','unknown')),
            attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 2),
            PRIMARY KEY(target_hash,url))""",
        """CREATE TABLE IF NOT EXISTS watch_notification_candidates (
            delivery_id TEXT NOT NULL REFERENCES watch_notifications(delivery_id),
            evaluation_id INTEGER NOT NULL REFERENCES watch_evaluations(id),
            url TEXT NOT NULL, PRIMARY KEY(delivery_id,evaluation_id))""",
        """CREATE TABLE IF NOT EXISTS watch_notification_attempts (
            attempt_id TEXT PRIMARY KEY, delivery_id TEXT NOT NULL REFERENCES watch_notifications(delivery_id),
            owner_token TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('sending','sent','rejected','unknown')),
            error_code TEXT, ack_message_id INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS watch_notification_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, delivery_id TEXT REFERENCES watch_notifications(delivery_id),
            action TEXT NOT NULL, evidence TEXT, message_id INTEGER, created_at TEXT NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_watch_notification_day ON watch_notifications(target_hash,kst_day)",
    ]
    for statement in statements:
        conn.execute(statement)


def clock(now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware ISO8601 datetime")
    return now.astimezone(timezone.utc)


def target_key(target):
    if not isinstance(target, str) or not target.isdecimal() or not 1 <= len(target) <= 32:
        raise ValueError("Telegram target must be a decimal private recipient id")
    return hashlib.sha256(target.encode()).hexdigest()


def text_units(text):
    # A conservative Telegram budget also bounds Python code points for emoji.
    return len(text.encode("utf-16-le")) // 2


def cut(text, limit):
    text = " ".join(text.split())
    if text_units(text) <= limit:
        return text
    result, used = [], 0
    for char in text:
        units = text_units(char)
        if used + units > limit - 1:
            break
        result.append(char)
        used += units
    return "".join(result) + "…"


def article_text(rows, budget):
    snapshot = json.loads(rows[0]["input_snapshot"])
    article = snapshot["article"]
    url = article["url"]
    # An indivisible URL cannot be trimmed. Unsafe/oversized items stay in backlog.
    if not isinstance(url, str) or not url or any(c.isspace() for c in url):
        return None
    title = cut(article["title"], 200)
    names = [cut(json.loads(r["input_snapshot"])["condition"]["name"], 80) for r in rows]
    minimum = text_units(title) + text_units(url) + 3 + sum(text_units(name) + 8 for name in names)
    if minimum > budget:
        return None
    reason_limit = min(
        180,
        (budget - text_units(title) - text_units(url) - 3 - sum(text_units(n) + 4 for n in names))
        // len(names),
    )
    lines = (
        [title]
        + [f"• {name}: {cut(r['reason'], reason_limit)}" for name, r in zip(names, rows)]
        + [url]
    )
    return "\n".join(lines)


class NotificationStore(EvaluationStore):
    """Shares Storage and short transaction helper with evaluation; no model calls."""

    @staticmethod
    def _enabled(conn):
        return bool(
            conn.execute("SELECT enabled FROM watch_notification_settings WHERE id=1").fetchone()[0]
        )

    def set_enabled(self, enabled, *, confirm=False):
        if type(enabled) is not bool or confirm is not True:
            raise ValueError("Enable/disable requires explicit confirmation and --confirm")
        with self._transaction() as conn:
            conn.execute(
                "UPDATE watch_notification_settings SET enabled=? WHERE id=1", (int(enabled),)
            )
            conn.execute(
                "INSERT INTO watch_notification_audit(action,created_at) VALUES(?,?)",
                ("enable" if enabled else "disable", clock().isoformat()),
            )
        return {"enabled": enabled}

    def status(self, *, limit=100):
        bounded(limit, "limit", 1000)
        conn = self.storage._connect()
        try:
            rows = conn.execute(
                "SELECT delivery_id,state,slot_utc,kst_day,payload_hash,error_code,ack_message_id,created_at,updated_at FROM watch_notifications ORDER BY created_at DESC,delivery_id LIMIT ?",
                (limit,),
            ).fetchall()
            return {"enabled": self._enabled(conn), "deliveries": [dict(r) for r in rows]}
        finally:
            conn.close()

    def show(self, identifier):
        conn = self.storage._connect()
        try:
            row = conn.execute(
                "SELECT * FROM watch_notifications WHERE delivery_id=?", (identifier,)
            ).fetchone()
            if row is None:
                raise ValueError("Notification not found")
            result = dict(row)
            for key, table in [
                ("candidates", "watch_notification_candidates"),
                ("attempts", "watch_notification_attempts"),
                ("audit", "watch_notification_audit"),
            ]:
                result[key] = [
                    dict(r)
                    for r in conn.execute(
                        f"SELECT * FROM {table} WHERE delivery_id=? ORDER BY rowid", (identifier,)
                    )
                ]
            return result
        finally:
            conn.close()

    @staticmethod
    def _cancel(conn, row, now, error):
        identifier = row["delivery_id"]
        conn.execute(
            "UPDATE watch_notifications SET state='cancelled',error_code=?,updated_at=? WHERE delivery_id=? AND state='pending'",
            (error, now.isoformat(), identifier),
        )
        # Retain attempts across release: a cancelled prepared retry has no refund.
        conn.execute(
            "UPDATE watch_notification_urls SET state='available',delivery_id=NULL WHERE delivery_id=? AND state='pending'",
            (identifier,),
        )

    def recover(self):
        """Startup recovery has no timeout: all unresolved transports stay claimed."""
        with self._transaction() as conn:
            now = clock().isoformat()
            conn.execute(
                "UPDATE watch_notifications SET state='unknown',error_code='restart_uncertain',updated_at=? WHERE state='sending'",
                (now,),
            )
            conn.execute("UPDATE watch_notification_urls SET state='unknown' WHERE state='sending'")
            conn.execute(
                "UPDATE watch_notification_attempts SET state='unknown',error_code='restart_uncertain',updated_at=? WHERE state='sending'",
                (now,),
            )

    def _guard(self, conn, key, now):
        """Bounded shared policy checks, including old pending cancellation."""
        slot = now.replace(minute=0, second=0, microsecond=0).isoformat()
        day = now.astimezone(KST).date().isoformat()
        pending = conn.execute(
            "SELECT * FROM watch_notifications WHERE target_hash=? AND state='pending' ORDER BY created_at LIMIT 1",
            (key,),
        ).fetchone()
        if pending and pending["slot_utc"] == slot:
            return dict(pending)
        if pending:
            self._cancel(conn, pending, now, "slot_expired")
        if not self._enabled(conn):
            return {"state": "disabled"}
        if not 9 <= now.astimezone(KST).hour < 21:
            return {"state": "quiet"}
        if (
            conn.execute(
                "SELECT 1 FROM watch_notifications WHERE target_hash=? AND slot_utc=?", (key, slot)
            ).fetchone()
            or conn.execute(
                "SELECT COUNT(*) FROM watch_notifications WHERE target_hash=? AND kst_day=?",
                (key, day),
            ).fetchone()[0]
            >= 6
        ):
            return {"state": "limited"}
        return None

    def _scan(self, key):
        """Coherent read snapshot; bounded live rows, no RESERVED writer lock.

        Scan through unformattable prefixes instead of truncating progress. Under
        DELETE journaling this SHARED reader can delay writer COMMIT; work/read
        duration can grow with backlog, but full snapshot materialization cannot.
        """
        conn = self.storage._connect()
        try:
            conn.execute("BEGIN")
            sql = f"""SELECT json_extract(e.input_snapshot,'$.article.url') AS url,
                u.state AS url_state,u.attempts AS url_attempts,u.delivery_id AS url_owner
                FROM watch_evaluations e JOIN watch_conditions w ON w.id=e.watch_id
                LEFT JOIN watch_notification_urls u ON u.target_hash=? AND u.url=json_extract(e.input_snapshot,'$.article.url')
                WHERE {ELIGIBLE} AND (u.url IS NULL OR (u.state IN ('available','rejected') AND u.attempts<2))
                ORDER BY e.article_id,e.watch_id,e.id"""
            cursor = conn.execute(sql, (key,))
            sections, selected, snapshots, claims = [], [], [], {}
            used = text_units("Watch 알림\n\n")
            while len(sections) < 3:
                page = cursor.fetchmany(100)
                if not page:
                    break
                for url_row in page:
                    url = url_row["url"]
                    # Only accepted URLs are retained for deduplication (max3).
                    # Unformattable duplicates may be inspected again, never cached
                    # into an unbounded Python set or skipped on later invocations.
                    if (
                        url in claims
                        or not isinstance(url, str)
                        or not url
                        or any(c.isspace() for c in url)
                        or text_units(url) > 3500
                    ):
                        continue
                    group = conn.execute(
                        f"""SELECT * FROM (
                        SELECT e.*, ROW_NUMBER() OVER (PARTITION BY e.watch_id ORDER BY e.article_id,e.id) AS reason_rank
                        FROM watch_evaluations e JOIN watch_conditions w ON w.id=e.watch_id
                        WHERE {ELIGIBLE} AND json_extract(e.input_snapshot,'$.article.url')=?
                        ) WHERE reason_rank=1 ORDER BY article_id,watch_id,id""",
                        (url,),
                    ).fetchall()
                    remaining = 3500 - used - (2 if sections else 0)
                    text = article_text(group, min(1100, remaining)) or article_text(
                        group, remaining
                    )
                    if text is None:
                        # A valid older item that needs a fresh message must lead
                        # the next slot; do not pack younger items around it.
                        if (
                            sections
                            and article_text(group, 3500 - text_units("Watch 알림\n\n")) is not None
                        ):
                            cursor.close()
                            return sections, selected, snapshots, claims
                        continue
                    used += text_units(text) + (2 if sections else 0)
                    sections.append(text)
                    selected.extend((r, url) for r in group)
                    claims[url] = (
                        url_row["url_state"],
                        url_row["url_attempts"],
                        url_row["url_owner"],
                    )
                    snapshots.extend(
                        {
                            "evaluation_id": r["id"],
                            "input_hash": r["input_hash"],
                            "input": json.loads(r["input_snapshot"]),
                            "reason": r["reason"],
                            "evidence": r["evidence"],
                        }
                        for r in group
                    )
                    if len(sections) == 3:
                        break
            cursor.close()
            return sections, selected, snapshots, claims
        finally:
            conn.rollback()
            conn.close()

    def prepare(self, target, *, now=None):
        requested_now = now
        now = clock(requested_now)
        key = target_key(target)
        with self._transaction() as conn:
            existing = self._guard(conn, key, now)
            if existing is not None:
                return existing
        sections, selected, snapshots, claims = self._scan(key)
        # Refresh production time after an arbitrarily long readonly scan. Explicit
        # diagnostic time stays fixed; sending independently refreshes real time.
        now = clock(requested_now)
        slot = now.replace(minute=0, second=0, microsecond=0).isoformat()
        day = now.astimezone(KST).date().isoformat()
        with self._transaction() as conn:
            existing = self._guard(conn, key, now)
            if existing is not None:
                return existing
            if not selected:
                return {"state": "empty"}
            identifiers = [r["id"] for r, _ in selected]
            placeholders = ",".join("?" for _ in identifiers)
            current = {
                r["id"]: r
                for r in conn.execute(
                    f"SELECT e.* FROM watch_evaluations e JOIN watch_conditions w ON w.id=e.watch_id WHERE {ELIGIBLE} AND e.id IN ({placeholders})",
                    identifiers,
                ).fetchall()
            }
            # Do not partially rebuild a prepared read snapshot under the write
            # fence. Any changed selected source/control or URL claim aborts all.
            fields = ("input_hash", "input_snapshot", "reason", "evidence")
            if len(current) != len(selected) or any(
                any(current[row["id"]][field] != row[field] for field in fields)
                for row, _ in selected
            ):
                return {"state": "empty", "error_code": "candidates_changed"}
            for url, observed in claims.items():
                claim = conn.execute(
                    "SELECT state,attempts,delivery_id FROM watch_notification_urls WHERE target_hash=? AND url=?",
                    (key, url),
                ).fetchone()
                actual = tuple(claim) if claim else (None, None, None)
                if actual != observed:
                    return {"state": "empty", "error_code": "url_claim_changed"}
            payload = json.dumps(
                {"chat_id": target, "text": "Watch 알림\n\n" + "\n\n".join(sections)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            identifier = uuid.uuid4().hex
            timestamp = now.isoformat()
            conn.execute(
                "INSERT INTO watch_notifications(delivery_id,target_hash,target,slot_utc,kst_day,state,payload,payload_hash,snapshot,created_at,updated_at) VALUES(?,?,?,?,?,'pending',?,?,?,?,?)",
                (
                    identifier,
                    key,
                    target,
                    slot,
                    day,
                    payload,
                    hashlib.sha256(payload.encode()).hexdigest(),
                    json.dumps(snapshots, ensure_ascii=False, sort_keys=True),
                    timestamp,
                    timestamp,
                ),
            )
            for row, url in selected:
                conn.execute(
                    "INSERT INTO watch_notification_candidates VALUES(?,?,?)",
                    (identifier, row["id"], url),
                )
                conn.execute(
                    "INSERT INTO watch_notification_urls(target_hash,url,delivery_id,state) VALUES(?,?,?,'pending') ON CONFLICT(target_hash,url) DO UPDATE SET delivery_id=excluded.delivery_id,state='pending'",
                    (key, url, identifier),
                )
            return dict(
                conn.execute(
                    "SELECT * FROM watch_notifications WHERE delivery_id=?", (identifier,)
                ).fetchone()
            )

    def start_sending(self, identifier, *, now=None):
        now = clock(now)
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM watch_notifications WHERE delivery_id=?", (identifier,)
            ).fetchone()
            if row is None:
                raise ValueError("Notification not found")
            if row["state"] != "pending":
                return None
            eligible = conn.execute(
                f"SELECT COUNT(*) FROM watch_notification_candidates c JOIN watch_evaluations e ON e.id=c.evaluation_id JOIN watch_conditions w ON w.id=e.watch_id WHERE c.delivery_id=? AND {ELIGIBLE}",
                (identifier,),
            ).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM watch_notification_candidates WHERE delivery_id=?",
                (identifier,),
            ).fetchone()[0]
            slot = now.replace(minute=0, second=0, microsecond=0).isoformat()
            if (
                not self._enabled(conn)
                or eligible != total
                or row["slot_utc"] != slot
                or not 9 <= now.astimezone(KST).hour < 21
            ):
                self._cancel(conn, row, now, "final_gate_changed")
                return None
            urls = conn.execute(
                "SELECT * FROM watch_notification_urls WHERE delivery_id=?", (identifier,)
            ).fetchall()
            if not urls or any(u["state"] != "pending" or u["attempts"] >= 2 for u in urls):
                self._cancel(conn, row, now, "url_attempt_limit")
                return None
            raw = row["payload"]
            if hashlib.sha256(raw.encode()).hexdigest() != row["payload_hash"]:
                self._cancel(conn, row, now, "snapshot_invalid")
                return None
            token = uuid.uuid4().hex
            conn.execute(
                "UPDATE watch_notifications SET state='sending',owner_token=?,updated_at=? WHERE delivery_id=?",
                (token, now.isoformat(), identifier),
            )
            conn.execute(
                "UPDATE watch_notification_urls SET state='sending',attempts=attempts+1 WHERE delivery_id=?",
                (identifier,),
            )
            conn.execute(
                "INSERT INTO watch_notification_attempts VALUES(?,?,?,'sending',NULL,NULL,?,?)",
                (uuid.uuid4().hex, identifier, token, now.isoformat(), now.isoformat()),
            )
            return token

    def finish(self, identifier, token, *, state, message_id=None, error_code=None):
        if state not in ("sent", "rejected", "unknown"):
            raise ValueError("Invalid notification result")
        if state == "sent":
            validate_positive_int(message_id, "message id")
        if error_code not in (
            None,
            "api_rejected",
            "ambiguous_response",
            "missing_message_id",
            "post_uncertain",
            "ack_storage_failed",
            "post_cancelled",
        ):
            error_code = "post_uncertain"
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM watch_notifications WHERE delivery_id=? AND owner_token=? AND state IN ('sending','unknown')",
                (identifier, token),
            ).fetchone()
            if row is None:
                return False
            # A receipt resolved by an operator/new owner cannot be overwritten.
            now = clock().isoformat()
            conn.execute(
                "UPDATE watch_notifications SET state=?,error_code=?,ack_message_id=?,updated_at=? WHERE delivery_id=?",
                (state, error_code, message_id, now, identifier),
            )
            conn.execute(
                "UPDATE watch_notification_urls SET state=? WHERE delivery_id=?",
                (state, identifier),
            )
            conn.execute(
                "UPDATE watch_notification_attempts SET state=?,error_code=?,ack_message_id=?,updated_at=? WHERE delivery_id=? AND owner_token=?",
                (state, error_code, message_id, now, identifier, token),
            )
            return True

    def resolve(self, identifier, *, outcome, confirm=False, evidence=None, message_id=None):
        if confirm is not True:
            raise ValueError("Resolution requires explicit confirmation and --confirm")
        if outcome not in ("sent", "retry"):
            raise ValueError("Outcome must be sent or retry")
        if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 1000:
            raise ValueError("Resolution requires receipt/nonreceipt evidence (1-1000 characters)")
        if outcome == "sent":
            validate_positive_int(message_id, "receipt message id")
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM watch_notifications WHERE delivery_id=?", (identifier,)
            ).fetchone()
            if row is None:
                raise ValueError("Notification not found")
            if row["state"] not in ("unknown", "rejected"):
                raise ValueError(
                    "Only unknown/rejected notifications can be resolved; stop active worker first"
                )
            urls = conn.execute(
                "SELECT * FROM watch_notification_urls WHERE delivery_id=?", (identifier,)
            ).fetchall()
            if not urls:
                raise ValueError("Notification claims already released")
            if outcome == "retry" and any(r["attempts"] >= 2 for r in urls):
                raise ValueError("URL attempt limit reached (maximum 2)")
            now = clock().isoformat()
            if outcome == "sent":
                conn.execute(
                    "UPDATE watch_notifications SET state='sent',owner_token=NULL,ack_message_id=?,error_code=NULL,updated_at=? WHERE delivery_id=?",
                    (message_id, now, identifier),
                )
                conn.execute(
                    "UPDATE watch_notification_urls SET state='sent' WHERE delivery_id=?",
                    (identifier,),
                )
            else:
                # This authorizes a new reservation. No POST and no quota bypass here.
                conn.execute(
                    "UPDATE watch_notifications SET owner_token=NULL,updated_at=? WHERE delivery_id=?",
                    (now, identifier),
                )
                conn.execute(
                    "UPDATE watch_notification_urls SET state='available',delivery_id=NULL WHERE delivery_id=?",
                    (identifier,),
                )
            conn.execute(
                "INSERT INTO watch_notification_audit(delivery_id,action,evidence,message_id,created_at) VALUES(?,?,?,?,?)",
                (identifier, outcome, evidence, message_id, now),
            )
        return {
            "delivery_id": identifier,
            "outcome": outcome,
            "state": "sent" if outcome == "sent" else "retry_authorized",
        }
