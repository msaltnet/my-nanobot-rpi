"""Atomic condition management. Each operation opens its own SQLite connection."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Iterator

from msalt.storage import Storage
from msalt.watch.models import (
    WatchCondition,
    normalize,
    validate_keywords,
    validate_positive_int,
    validate_text,
)


class WatchStore:
    def __init__(self, storage: Storage):
        self.storage = storage

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.storage._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            duplicate_names = {
                "UNIQUE constraint failed: watch_conditions.name",
                "UNIQUE constraint failed: watch_conditions.normalized_name",
            }
            if exc.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE and str(exc) in duplicate_names:
                raise ValueError("Watch name already exists") from None
            raise
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _condition(row: sqlite3.Row) -> WatchCondition:
        return WatchCondition(
            id=row["id"], name=row["name"], description=row["description"],
            keywords=json.loads(row["keywords_json"]),
            excluded_keywords=json.loads(row["excluded_keywords_json"]),
            active=bool(row["active"]), revision=row["revision"],
            start_article_id=row["start_article_id"], created_at=row["created_at"],
            updated_at=row["updated_at"], deleted_at=row["deleted_at"],
        )

    def _row(self, conn: sqlite3.Connection, identifier: int) -> sqlite3.Row:
        validate_positive_int(identifier, "id")
        row = conn.execute("SELECT * FROM watch_conditions WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("Watch condition not found")
        return row

    def _editable(self, conn: sqlite3.Connection, identifier: int,
                  expected_revision: int) -> sqlite3.Row:
        validate_positive_int(expected_revision, "expected revision")
        row = self._row(conn, identifier)
        if row["revision"] != expected_revision:
            raise ValueError("Watch revision conflict; show the condition and confirm again")
        if row["deleted_at"] is not None:
            raise ValueError("Watch condition is deleted")
        return row

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _watermark(conn: sqlite3.Connection) -> int:
        return conn.execute("SELECT COALESCE(MAX(id), 0) FROM news_articles").fetchone()[0]

    def add(self, name: str, *, description: str, keywords: list[str],
            excluded_keywords: list[str]) -> WatchCondition:
        name = validate_text(name, "name", 80)
        description = validate_text(description, "description", 2000)
        keywords = validate_keywords(keywords, "keywords")
        excluded_keywords = validate_keywords(excluded_keywords, "excluded keywords")
        with self._transaction() as conn:
            count = conn.execute("SELECT COUNT(*) FROM watch_conditions WHERE deleted_at IS NULL").fetchone()[0]
            if count >= 100:
                raise ValueError("At most 100 nondeleted Watch conditions are allowed")
            now = self._now()
            cursor = conn.execute(
                "INSERT INTO watch_conditions (name, normalized_name, description, keywords_json, "
                "excluded_keywords_json, active, revision, start_article_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 0, 1, 0, ?, ?)",
                (name, normalize(name), description, json.dumps(keywords, ensure_ascii=False),
                 json.dumps(excluded_keywords, ensure_ascii=False), now, now),
            )
            return self._condition(self._row(conn, cursor.lastrowid))

    def list(self, *, include_deleted: bool = False) -> list[WatchCondition]:
        conn = self.storage._connect()
        try:
            where = "" if include_deleted else " WHERE deleted_at IS NULL"
            return [self._condition(row) for row in conn.execute(
                "SELECT * FROM watch_conditions" + where + " ORDER BY id")]
        finally:
            conn.close()

    def show(self, identifier: int) -> WatchCondition:
        conn = self.storage._connect()
        try:
            return self._condition(self._row(conn, identifier))
        finally:
            conn.close()

    def update(self, identifier: int, *, expected_revision: int, **changes) -> WatchCondition:
        allowed = {"name", "description", "keywords", "excluded_keywords"}
        if changes.keys() - allowed:
            raise ValueError("Unknown Watch field")
        validated = {}
        for field, value in changes.items():
            if field in {"keywords", "excluded_keywords"}:
                validated[field] = validate_keywords(value, field)
            else:
                validated[field] = validate_text(value, field, 80 if field == "name" else 2000)
        with self._transaction() as conn:
            row = self._editable(conn, identifier, expected_revision)
            current = self._condition(row)
            if all(getattr(current, field) == value for field, value in validated.items()):
                return current
            values = {field: validated.get(field, getattr(current, field)) for field in allowed}
            conn.execute(
                "UPDATE watch_conditions SET name=?, normalized_name=?, description=?, "
                "keywords_json=?, excluded_keywords_json=?, revision=revision+1, "
                "start_article_id=?, updated_at=? WHERE id=?",
                (values["name"], normalize(values["name"]), values["description"],
                 json.dumps(values["keywords"], ensure_ascii=False),
                 json.dumps(values["excluded_keywords"], ensure_ascii=False),
                 self._watermark(conn), self._now(), identifier),
            )
            return self._condition(self._row(conn, identifier))

    def pause(self, identifier: int, *, expected_revision: int) -> WatchCondition:
        return self._state(identifier, expected_revision=expected_revision, active=False)

    def resume(self, identifier: int, *, expected_revision: int) -> WatchCondition:
        return self._state(identifier, expected_revision=expected_revision, active=True)

    def _state(self, identifier: int, *, expected_revision: int, active: bool) -> WatchCondition:
        with self._transaction() as conn:
            row = self._editable(conn, identifier, expected_revision)
            if bool(row["active"]) == active:
                return self._condition(row)
            if active:
                count = conn.execute("SELECT COUNT(*) FROM watch_conditions WHERE active=1 AND deleted_at IS NULL").fetchone()[0]
                if count >= 20:
                    raise ValueError("At most 20 active Watch conditions are allowed")
            watermark = self._watermark(conn) if active else row["start_article_id"]
            conn.execute(
                "UPDATE watch_conditions SET active=?, revision=revision+1, "
                "start_article_id=?, updated_at=? WHERE id=?",
                (int(active), watermark, self._now(), identifier),
            )
            return self._condition(self._row(conn, identifier))

    def delete(self, identifier: int, *, expected_revision: int) -> WatchCondition:
        with self._transaction() as conn:
            self._editable(conn, identifier, expected_revision)
            now = self._now()
            conn.execute(
                "UPDATE watch_conditions SET active=0, revision=revision+1, deleted_at=?, "
                "updated_at=? WHERE id=?", (now, now, identifier),
            )
            return self._condition(self._row(conn, identifier))
