"""Operator-only delivery inspection and explicit recovery. No automatic seeding."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from msalt.config import MsaltConfig
from msalt.news.coordinator import NewsDeliveryCoordinator
from msalt.news.delivery import DeliveryLedger
from msalt.news.reply_tool import authorized_target
from msalt.news.sender import BotAPI, DeliverySender


def database_path():
    return Path(MsaltConfig().db_path)


def public_status(row):
    result = {
        key: row[key]
        for key in (
            "delivery_id",
            "state",
            "kst_date",
            "slot",
            "generation",
            "error",
            "created_at",
            "updated_at",
        )
        if key in row
    }
    if "parts" in row:
        result["parts"] = [
            {key: part[key] for key in ("part_no", "state", "attempts", "message_id", "ack_at")}
            for part in row["parts"]
        ]
        result["attempt_log"] = [
            {key: attempt[key] for key in ("part_no", "created_at", "outcome", "error", "manual")}
            for attempt in row["attempt_log"]
        ]
    return result


def run_command(argv):
    parser = argparse.ArgumentParser(prog="my-nanobot-rpi news delivery")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Read existing ledger without initializing a database")
    for name in ("show", "retry", "resolve", "regenerate"):
        sub = commands.add_parser(name)
        sub.add_argument("delivery_id")
        if name == "retry":
            sub.add_argument("--confirm-uncertain", action="store_true")
        if name == "resolve":
            choice = sub.add_mutually_exclusive_group(required=True)
            choice.add_argument("--received", action="store_true")
            choice.add_argument("--abandon", action="store_true")
    args = parser.parse_args(argv)
    ledger = DeliveryLedger(database_path())
    try:
        if args.command == "list":
            result = [public_status(row) for row in ledger.list()]
        elif args.command == "show":
            result = public_status(ledger.show(args.delivery_id))
        else:
            # Explicit mutation only; readonly commands never recover/initialize.
            ledger.recover()
            row = ledger.show(args.delivery_id)
            if args.command == "resolve":
                ledger.resolve(args.delivery_id, received=args.received, abandon=args.abandon)
            else:
                from msalt.cli import _load_dotenv

                _load_dotenv()
                token = authorized_target(row["target"])
                if args.command == "retry":
                    asyncio.run(
                        DeliverySender(ledger, post=BotAPI(token)).send(
                            args.delivery_id, manual=True, confirm_uncertain=args.confirm_uncertain
                        )
                    )
                else:
                    service = NewsDeliveryCoordinator(ledger.db_path, post=BotAPI(token))
                    asyncio.run(
                        service.run(
                            row["target"], row["thread"], row["slot"], regenerate=args.delivery_id
                        )
                    )
            result = public_status(ledger.show(args.delivery_id))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ValueError as exc:
        # Only locally-defined policy errors are exposed; transport exceptions are not.
        safe = (
            "not found",
            "confirm-uncertain",
            "no saved payload",
            "cannot be resolved",
            "only failed generation",
        )
        message = next((value for value in safe if value in str(exc)), "operation refused")
        print(json.dumps({"status": "unavailable", "error": message}))
        return 1
    except Exception:
        print(json.dumps({"status": "unavailable", "error": "ledger unavailable"}))
        return 1
