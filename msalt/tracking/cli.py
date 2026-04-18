"""msalt.tracking CLI: dispatch / add / list / delete / record / summary."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import httpx

from msalt.storage import Storage
from msalt.tracking.items import (
    TrackedItemManager, ItemAlreadyExists, ItemNotFound,
)
from msalt.tracking.records import RecordManager
from msalt.tracking.dispatcher import Dispatcher


DEFAULT_DB = str(Path.home() / ".nanobot" / "workspace" / "msalt.db")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="msalt.tracking")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_disp = sub.add_parser("dispatch", help="run dispatcher once")
    p_disp.add_argument("--now", help="ISO8601 datetime override (testing)")

    p_add = sub.add_parser("add", help="add tracked item")
    p_add.add_argument("name")
    p_add.add_argument("schema",
                       choices=["freetext", "duration", "quantity", "boolean"])
    p_add.add_argument("--unit", default=None)
    p_add.add_argument("--time", required=True, help="HH:MM")

    sub.add_parser("list", help="list tracked items")

    p_del = sub.add_parser("delete", help="delete tracked item")
    p_del.add_argument("name")

    p_rec = sub.add_parser("record", help="insert record")
    p_rec.add_argument("name")
    p_rec.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_rec.add_argument("--text", default=None)
    p_rec.add_argument("--num", type=float, default=None)
    p_rec.add_argument("--bool", dest="value_bool", action="store_true")
    p_rec.add_argument("--no-bool", dest="value_bool_neg",
                       action="store_true")
    p_rec.add_argument("--raw", required=True)

    p_sum = sub.add_parser("summary", help="show summary")
    p_sum.add_argument("name")
    p_sum.add_argument("--days", type=int, default=7)
    p_sum.add_argument("--ref", help="reference date YYYY-MM-DD",
                       default=None)

    return p


def _make_telegram_sender() -> Callable[[str], None]:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_USER_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send(text: str) -> None:
        httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)

    return send


def run_command(argv: list[str], *, db_path: str = DEFAULT_DB) -> int:
    args = build_parser().parse_args(argv)

    storage = Storage(db_path)
    storage.initialize()
    items = TrackedItemManager(storage)
    records = RecordManager(storage, items)

    if args.cmd == "add":
        try:
            items.add(args.name, args.schema, args.unit, args.time)
        except (ValueError, ItemAlreadyExists) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(f"등록: {args.name} ({args.schema}, {args.time})")
        return 0

    if args.cmd == "list":
        for it in items.list_all():
            unit = f" [{it['unit']}]" if it["unit"] else ""
            print(f"{it['name']}: {it['schema']}{unit} @ {it['schedule_time']}")
        return 0

    if args.cmd == "delete":
        try:
            items.delete(args.name)
        except ItemNotFound as e:
            print(f"error: not found: {e}", file=sys.stderr)
            return 2
        print(f"삭제: {args.name}")
        return 0

    if args.cmd == "record":
        bool_val: bool | None = None
        if args.value_bool:
            bool_val = True
        elif args.value_bool_neg:
            bool_val = False
        try:
            records.upsert(
                args.name, args.date,
                raw_input=args.raw,
                value_text=args.text,
                value_num=args.num,
                value_bool=bool_val,
            )
        except KeyError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(f"기록: {args.name} {args.date}")
        return 0

    if args.cmd == "summary":
        ref = args.ref or datetime.now().date().isoformat()
        try:
            print(records.summarize(args.name, days=args.days, ref_date=ref))
        except KeyError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "dispatch":
        sender = _make_telegram_sender()
        d = Dispatcher(items, records, telegram_send=sender)
        if args.now:
            now = datetime.fromisoformat(args.now)
        else:
            now = datetime.now().astimezone()
        msgs = d.run(now=now)
        print(f"dispatched {len(msgs)} message(s)")
        return 0

    return 1


def main() -> None:
    sys.exit(run_command(sys.argv[1:]))
