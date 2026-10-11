"""Explicit Watch dispatcher; no collection, evaluation, jobs or model calls."""

from __future__ import annotations

import sqlite3

from msalt.watch.sender import NotificationSender


class Dispatcher:
    def __init__(self, store, *, post):
        self.store, self.post = store, post

    async def run(self, target, *, now=None):
        try:
            self.store.recover()
        except sqlite3.Error:
            # Failed recovery leaves durable sending claims; no automatic resend.
            pass
        row = self.store.prepare(target, now=now)
        if row["state"] != "pending":
            return {"state": row["state"], "delivery_id": row.get("delivery_id")}
        state = await NotificationSender(self.store, post=self.post).send(
            row["delivery_id"], now=now
        )
        return {"state": state, "delivery_id": row["delivery_id"]}
