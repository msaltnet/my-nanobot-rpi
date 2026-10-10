"""Durable evaluation queue, revision cursors and conservative request reservations."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict

from msalt.storage import Storage
from msalt.watch.models import normalize, validate_positive_int
from msalt.watch.store import WatchStore

STATUSES = ("pending", "evaluating", "relevant", "irrelevant", "error")


def bounded(value, field, maximum, minimum=1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def literal_rule(snapshot):
    condition, article = snapshot["condition"], snapshot["article"]
    text = normalize(article["title"] + "\n" + (article["summary"] or ""))
    if any(normalize(k) in text for k in condition["excluded_keywords"]):
        return "excluded_keyword"
    if condition["keywords"] and not any(normalize(k) in text for k in condition["keywords"]):
        return "keyword_mismatch"
    return None


def validate_result(result, snapshot):
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (ValueError, RecursionError):
            raise ValueError("invalid_response") from None
    if not isinstance(result, dict) or set(result) != {
        "relevant",
        "importance",
        "reason",
        "evidence",
    }:
        raise ValueError("invalid_response")
    if type(result["relevant"]) is not bool or result["importance"] not in (
        "low",
        "medium",
        "high",
    ):
        raise ValueError("invalid_response")
    for field in ("reason", "evidence"):
        value = result[field]
        if not isinstance(value, str) or not value.strip() or not 1 <= len(value) <= 500:
            raise ValueError("invalid_response")
    evidence, article = result["evidence"], snapshot["article"]
    if evidence not in article["title"] and evidence not in (article["summary"] or ""):
        raise ValueError("invalid_response")
    return result


class EvaluationStore:
    def __init__(self, storage: Storage):
        self.storage = storage

    @contextmanager
    def _transaction(self):
        conn = self.storage._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def enqueue(self, maximum=100):
        """Persist oldest candidates and each revision cursor atomically, globally bounded."""
        bounded(maximum, "max articles", 100)
        count = 0
        with self._transaction() as conn:
            watches = conn.execute(
                "SELECT * FROM watch_conditions WHERE active=1 AND deleted_at IS NULL ORDER BY id"
            ).fetchall()
            for watch in watches:
                if count == maximum:
                    break
                cursor = conn.execute(
                    "SELECT last_article_id FROM watch_scan_cursors WHERE watch_id=? AND revision=?",
                    (watch["id"], watch["revision"]),
                ).fetchone()
                after = max(watch["start_article_id"], cursor[0] if cursor else 0)
                rows = conn.execute(
                    "SELECT * FROM news_articles WHERE id>? ORDER BY id LIMIT ?",
                    (after, maximum - count),
                ).fetchall()
                for article in rows:
                    snapshot = {
                        "condition": asdict(WatchStore._condition(watch)),
                        "article": dict(article),
                    }
                    raw = json.dumps(
                        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    )
                    now = time.time()
                    conn.execute(
                        "INSERT INTO watch_evaluations (watch_id,revision,article_id,status,input_snapshot,input_hash,created_at,updated_at) VALUES (?,?,?,'pending',?,?,?,?) ON CONFLICT(watch_id,revision,article_id) DO NOTHING",
                        (
                            watch["id"],
                            watch["revision"],
                            article["id"],
                            raw,
                            hashlib.sha256(raw.encode()).hexdigest(),
                            now,
                            now,
                        ),
                    )
                    count += 1
                if rows:
                    conn.execute(
                        "INSERT INTO watch_scan_cursors VALUES (?,?,?) ON CONFLICT(watch_id,revision) DO UPDATE SET last_article_id=excluded.last_article_id",
                        (watch["id"], watch["revision"], rows[-1]["id"]),
                    )
        return count

    def begin_run(self, max_articles=100, max_calls=10, *, retry_errors=False):
        bounded(max_articles, "max articles", 100)
        bounded(max_calls, "max calls", 10, 0)
        if type(retry_errors) is not bool:
            raise ValueError("retry_errors must be bool")
        identifier = uuid.uuid4().hex
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO watch_evaluation_runs(run_id,max_articles,max_calls,retry_errors,created_at) VALUES (?,?,?,?,?)",
                (identifier, max_articles, max_calls, int(retry_errors), time.time()),
            )
        return identifier

    @staticmethod
    def _expire(conn, now):
        conn.execute(
            "UPDATE watch_evaluations SET status='error', error_code='lease_expired', owner_token=NULL, lease_until=NULL, updated_at=? WHERE status='evaluating' AND lease_until<=?",
            (now, now),
        )

    def claim(self, run_id):
        """Reserve a candidate, attempt and run call before crossing the HTTP boundary."""
        with self._transaction() as conn:
            now = time.time()
            self._expire(conn, now)
            run = conn.execute(
                "SELECT * FROM watch_evaluation_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise ValueError("Evaluation run not found")
            if run["articles_processed"] >= run["max_articles"]:
                return None
            statuses = "('pending','error')" if run["retry_errors"] else "('pending')"
            rows = conn.execute(
                f"SELECT e.* FROM watch_evaluations e JOIN watch_conditions w ON w.id=e.watch_id WHERE w.active=1 AND w.deleted_at IS NULL AND w.revision=e.revision AND e.status IN {statuses} AND e.attempts<3 AND (e.last_run_id IS NULL OR e.last_run_id<>?) ORDER BY e.article_id,e.watch_id LIMIT 100",
                (run_id,),
            ).fetchall()
            for row in rows:
                snapshot = json.loads(row["input_snapshot"])
                rule = literal_rule(snapshot)
                if rule:
                    conn.execute(
                        "UPDATE watch_evaluations SET status='irrelevant',relevant=0,importance='low',reason=?,evidence=?,filter_rule=?,error_code=NULL,last_run_id=?,updated_at=? WHERE id=?",
                        (
                            rule,
                            rule + ": title/summary in input_snapshot",
                            rule,
                            run_id,
                            now,
                            row["id"],
                        ),
                    )
                    conn.execute(
                        "UPDATE watch_evaluation_runs SET articles_processed=articles_processed+1 WHERE run_id=?",
                        (run_id,),
                    )
                    run = conn.execute(
                        "SELECT * FROM watch_evaluation_runs WHERE run_id=?", (run_id,)
                    ).fetchone()
                    if run["articles_processed"] >= run["max_articles"]:
                        return None
                    continue
                if run["calls_reserved"] >= run["max_calls"]:
                    continue
                token = uuid.uuid4().hex
                conn.execute(
                    "UPDATE watch_evaluations SET status='evaluating', attempts=attempts+1,owner_token=?,lease_until=?,last_run_id=?,error_code=NULL,updated_at=? WHERE id=?",
                    (token, now + 30, run_id, now, row["id"]),
                )
                conn.execute(
                    "UPDATE watch_evaluation_runs SET calls_reserved=calls_reserved+1,articles_processed=articles_processed+1 WHERE run_id=?",
                    (run_id,),
                )
                claim = dict(
                    conn.execute(
                        "SELECT * FROM watch_evaluations WHERE id=?", (row["id"],)
                    ).fetchone()
                )
                claim["snapshot"] = snapshot
                return claim
            return None

    def authorize_call(self, identifier, token):
        """Fence pause/revision/deletion immediately before starting an external call."""
        with self._transaction() as conn:
            now = time.time()
            self._expire(conn, now)
            row = conn.execute(
                "SELECT e.id,w.active,w.revision,w.deleted_at,e.revision AS evaluation_revision FROM watch_evaluations e JOIN watch_conditions w ON w.id=e.watch_id WHERE e.id=? AND e.owner_token=? AND e.status='evaluating'",
                (identifier, token),
            ).fetchone()
            if (
                row
                and row["active"]
                and row["revision"] == row["evaluation_revision"]
                and row["deleted_at"] is None
            ):
                return True
            if row:
                conn.execute(
                    "UPDATE watch_evaluations SET status='error',error_code='condition_changed',owner_token=NULL,lease_until=NULL,updated_at=? WHERE id=? AND owner_token=?",
                    (now, identifier, token),
                )
            return False

    def complete(self, identifier, token, result=None, *, error_code=None):
        with self._transaction() as conn:
            now = time.time()
            self._expire(conn, now)
            row = conn.execute(
                "SELECT e.*,w.active,w.revision AS current_revision,w.deleted_at FROM watch_evaluations e JOIN watch_conditions w ON w.id=e.watch_id WHERE e.id=? AND e.owner_token=? AND e.status='evaluating'",
                (identifier, token),
            ).fetchone()
            if row is None:
                return False
            if error_code is None:
                try:
                    result = validate_result(result, json.loads(row["input_snapshot"]))
                except ValueError:
                    error_code = "invalid_response"
            if error_code is not None:
                # Persist only bounded public codes, never model/HTTP exceptions.
                if error_code not in (
                    "invalid_response",
                    "timeout",
                    "adapter_error",
                    "configuration_error",
                ):
                    error_code = "adapter_error"
                status, relevant, importance, reason, evidence = "error", None, None, None, None
            else:
                status = "relevant" if result["relevant"] else "irrelevant"
                relevant, importance, reason, evidence = (
                    int(result["relevant"]),
                    result["importance"],
                    result["reason"],
                    result["evidence"],
                )
            stale = (
                not row["active"]
                or row["deleted_at"] is not None
                or row["revision"] != row["current_revision"]
            )
            conn.execute(
                "UPDATE watch_evaluations SET status=?,relevant=?,importance=?,reason=?,evidence=?,error_code=?,stale_at_completion=?,owner_token=NULL,lease_until=NULL,updated_at=?,completed_at=? WHERE id=? AND owner_token=?",
                (
                    status,
                    relevant,
                    importance,
                    reason,
                    evidence,
                    error_code,
                    int(stale),
                    now,
                    now,
                    identifier,
                    token,
                ),
            )
            return True

    def run_summary(self, identifier):
        conn = self.storage._connect()
        try:
            row = conn.execute(
                "SELECT * FROM watch_evaluation_runs WHERE run_id=?", (identifier,)
            ).fetchone()
            if row is None:
                raise ValueError("Evaluation run not found")
            return dict(row)
        finally:
            conn.close()

    def list(self, *, watch_id=None, status=None, limit=100, eligible_only=False):
        bounded(limit, "limit", 1000)
        if watch_id is not None:
            validate_positive_int(watch_id, "watch id")
        if status is not None and status not in STATUSES:
            raise ValueError("Unknown evaluation status")
        where, params = [], []
        if watch_id is not None:
            where.append("e.watch_id=?")
            params.append(watch_id)
        if status is not None:
            where.append("e.status=?")
            params.append(status)
        if eligible_only:
            where.append(
                "e.status='relevant' AND e.relevant=1 AND e.importance='high' AND w.active=1 AND w.deleted_at IS NULL AND w.revision=e.revision"
            )
        conn = self.storage._connect()
        try:
            sql = "SELECT e.*,w.active,w.revision AS current_revision,w.deleted_at FROM watch_evaluations e JOIN watch_conditions w ON w.id=e.watch_id"
            sql += (" WHERE " + " AND ".join(where)) if where else ""
            rows = conn.execute(
                sql + " ORDER BY e.watch_id,e.article_id,e.revision LIMIT ?", [*params, limit]
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                snapshot = json.loads(item.pop("input_snapshot"))
                item["condition"], item["article"] = snapshot["condition"], snapshot["article"]
                active, deleted, revision = (
                    item.pop("active"),
                    item.pop("deleted_at"),
                    item.pop("current_revision"),
                )
                item["stale"] = (
                    not bool(active) or deleted is not None or item["revision"] != revision
                )
                if item["relevant"] is not None:
                    item["relevant"] = bool(item["relevant"])
                item.pop("owner_token")
                result.append(item)
            return result
        finally:
            conn.close()

    def notification_candidates(self, *, limit=100):
        """Shared Issue 11 contract: active/current relevant+high only; no delivery effects."""
        return self.list(limit=limit, eligible_only=True)
