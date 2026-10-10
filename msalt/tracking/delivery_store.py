"""Persistent tracking claims. No message bodies, credentials or automatic expiry."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal

from msalt.storage import Storage


@dataclass(frozen=True)
class DeliveryCandidate:
    item_id: int
    recorded_for: str
    kind: Literal['scheduled', 'retry']
    slot_utc: str


def normalize_utc(value: str) -> str:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError('Delivery slot requires an explicit timezone')
    return moment.astimezone(timezone.utc).isoformat(timespec='seconds')


class DeliveryStore:
    def __init__(self, storage: Storage):
        self.storage = storage

    def claim(self, candidates: list[DeliveryCandidate], when_utc: str) -> list[dict]:
        """Claim every eligible candidate in one short transaction before any POST."""
        normalized = []
        for candidate in candidates:
            if candidate.kind not in ('scheduled', 'retry'):
                raise ValueError('Invalid delivery kind')
            date.fromisoformat(candidate.recorded_for)
            normalized.append(DeliveryCandidate(
                candidate.item_id, candidate.recorded_for, candidate.kind,
                normalize_utc(candidate.slot_utc),
            ))
        conn = self.storage._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            claims = []
            for candidate in normalized:
                # Recheck under the writer lock: another process or user may have acted
                # since Dispatcher built its candidate list.
                if not conn.execute('SELECT 1 FROM tracked_items WHERE id = ?',
                                    (candidate.item_id,)).fetchone():
                    continue
                if conn.execute('SELECT 1 FROM records WHERE item_id = ? AND recorded_for = ?',
                                (candidate.item_id, candidate.recorded_for)).fetchone():
                    continue
                if conn.execute("""
                    SELECT 1 FROM tracking_deliveries
                    WHERE item_id = ? AND recorded_for = ? AND resolved_at IS NULL
                    AND state IN ('claimed', 'unknown')
                """, (candidate.item_id, candidate.recorded_for)).fetchone():
                    continue
                if candidate.kind == 'retry':
                    boundaries = conn.execute("""
                        SELECT state, completed_at, resolved_at FROM tracking_deliveries
                        WHERE item_id = ? AND recorded_for = ?
                        AND (state = 'rejected' OR resolved_at IS NOT NULL)
                    """, (candidate.item_id, candidate.recorded_for)).fetchall()
                    slot = datetime.fromisoformat(candidate.slot_utc)
                    cutoff_times = []
                    for row in boundaries:
                        for value in (row['completed_at'] if row['state'] == 'rejected'
                                      else None, row['resolved_at']):
                            if value is not None:
                                cutoff = datetime.fromisoformat(value)
                                # completed_at uses existing naive UTC storage format;
                                # resolved_at is an aware UTC ISO timestamp.
                                if cutoff.tzinfo is None:
                                    cutoff = cutoff.replace(tzinfo=timezone.utc)
                                cutoff_times.append(cutoff)
                    if cutoff_times and slot <= max(cutoff_times):
                        continue
                cursor = conn.execute("""
                    INSERT INTO tracking_deliveries
                    (item_id, recorded_for, kind, slot_utc, state, claimed_at)
                    VALUES (?, ?, ?, ?, 'claimed', ?)
                    ON CONFLICT(item_id, recorded_for, kind, slot_utc) DO NOTHING
                """, (candidate.item_id, candidate.recorded_for, candidate.kind,
                      candidate.slot_utc, when_utc))
                if cursor.rowcount:
                    claims.append(dict(conn.execute(
                        'SELECT * FROM tracking_deliveries WHERE id = ?',
                        (cursor.lastrowid,),
                    ).fetchone()))
            conn.commit()
            return claims
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def finish(self, ids: list[int], state: Literal['sent', 'rejected', 'unknown'],
               when_utc: str) -> None:
        """Confirm ACK and pending/last-success together; rollback keeps claim blocked."""
        if state not in ('sent', 'rejected', 'unknown'):
            raise ValueError('Invalid delivery outcome')
        conn = self.storage._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            for delivery_id in ids:
                row = conn.execute('SELECT * FROM tracking_deliveries WHERE id = ?',
                                   (delivery_id,)).fetchone()
                if row is None:
                    # Concurrent deletion removes the item and its claims by cascade.
                    continue
                if row['state'] != 'claimed' or row['resolved_at'] is not None:
                    raise ValueError('Delivery claim is no longer unresolved')
                conn.execute('UPDATE tracking_deliveries SET state = ?, completed_at = ? '
                             'WHERE id = ?', (state, when_utc, delivery_id))
                if state in ('sent', 'rejected'):
                    self._retain_pending(conn, row, when_utc)
                if state == 'sent':
                    conn.execute('UPDATE tracked_items SET last_asked_at = ? WHERE id = ?',
                                 (when_utc, row['item_id']))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _retain_pending(conn, row, when_utc: str) -> None:
        conn.execute("""
            UPDATE tracked_items SET pending_since = ?, pending_recorded_for = ?
            WHERE id = ? AND pending_since IS NULL
            AND NOT EXISTS (SELECT 1 FROM records WHERE item_id = ? AND recorded_for = ?)
        """, (when_utc, row['recorded_for'], row['item_id'],
              row['item_id'], row['recorded_for']))

    def status(self) -> list[dict]:
        """Only ledger identifiers, slots and states; omit names and payloads."""
        conn = self.storage._connect()
        try:
            return [dict(row) for row in conn.execute("""
                SELECT id, item_id, recorded_for, kind, slot_utc, state,
                       claimed_at, completed_at, resolved_at
                FROM tracking_deliveries ORDER BY id
            """)]
        finally:
            conn.close()

    def release(self, delivery_id: int, *, confirmed_received: bool) -> None:
        """Operator checked receipt; preserve tombstone and allow a later retry slot."""
        if not confirmed_received:
            raise ValueError('Explicit receipt confirmation is required')
        conn = self.storage._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM tracking_deliveries WHERE id = ?',
                               (delivery_id,)).fetchone()
            if (row is None or row['state'] not in ('claimed', 'unknown')
                    or row['resolved_at'] is not None):
                raise ValueError('Unresolved delivery ID not found')
            conn.execute('UPDATE tracking_deliveries SET resolved_at = ? WHERE id = ?',
                         (datetime.now(timezone.utc).isoformat(timespec='seconds'), delivery_id))
            self._retain_pending(conn, row, row['claimed_at'])
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
