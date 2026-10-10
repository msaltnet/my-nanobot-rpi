"""Structured offline Watch management CLI, shared by the root command."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

from msalt.storage import Storage
from msalt.watch.store import WatchStore

DEFAULT_DB = str(Path.home() / ".nanobot" / "workspace" / "msalt.db")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="my-nanobot-rpi watch")
    parser.add_argument("--json", action="store_true", help="structured JSON output")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("add", "list", "show", "update", "pause", "resume", "delete"):
        child = sub.add_parser(command)
        child.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if command == "list":
            child.add_argument("--all", action="store_true", help="include deleted conditions")
        elif command == "add":
            child.add_argument("name")
            child.add_argument("--description", required=True)
            child.add_argument("--keywords-json", required=True)
            child.add_argument("--excluded-json", required=True)
        else:
            child.add_argument("id", type=int)
            if command != "show":
                child.add_argument("--expected-revision", type=int, required=True)
            if command == "update":
                child.add_argument("--name")
                child.add_argument("--description")
                child.add_argument("--keywords-json")
                child.add_argument("--excluded-json")
            if command == "delete":
                child.add_argument("--confirm", action="store_true")
    child = sub.add_parser('evaluate', help='Evaluate saved articles; model calls may incur cost')
    child.add_argument('--json', action='store_true', default=argparse.SUPPRESS)
    child.add_argument('--max-articles', type=int, default=100)
    child.add_argument('--max-calls', type=int, default=10)
    child.add_argument('--retry-errors', action='store_true')
    child = sub.add_parser('evaluations')
    child.add_argument('--json', action='store_true', default=argparse.SUPPRESS)
    child.add_argument('--watch-id', type=int)
    child.add_argument('--status')
    child.add_argument('--limit', type=int, default=100)
    child = sub.add_parser('notify', help='Operator Watch delivery control')
    child.add_argument('--json', action='store_true', default=argparse.SUPPRESS)
    commands = child.add_subparsers(dest='notify_command', required=True)
    for name in ('status', 'dispatch', 'enable', 'disable', 'resolve'):
        command = commands.add_parser(name)
        command.add_argument('--json', action='store_true', default=argparse.SUPPRESS)
        if name == 'status':
            command.add_argument('--limit', type=int, default=100)
        elif name == 'dispatch':
            command.add_argument('--now', help='ISO8601 diagnostic time; requires --diagnostic-time')
            command.add_argument('--diagnostic-time', action='store_true')
        else:
            command.add_argument('--confirm', action='store_true')
            if name == 'resolve':
                command.add_argument('delivery_id')
                command.add_argument('--outcome', required=True, choices=('sent','retry'))
                command.add_argument('--evidence')
                command.add_argument('--message-id', type=int)
    return parser


def _keywords(raw: str):
    try:
        return json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError("Keyword JSON must be a list of strings") from None


def _emit(data, *, structured: bool) -> None:
    if structured:
        print(json.dumps(data, ensure_ascii=False))
    elif isinstance(data, dict) and "error" in data:
        print(data["error"], file=sys.stderr)
    elif isinstance(data, dict) and ('enabled' in data or 'state' in data or 'outcome' in data):
        print(json.dumps(data, ensure_ascii=False))
    else:
        rows = data if isinstance(data, list) else [data]
        if not rows:
            print("No Watch conditions")
        for item in rows:
            if 'run_id' in item and 'calls_reserved' in item:
                print(f"Processed {item['articles_processed']} candidates; reserved {item['calls_reserved']} model calls")
                continue
            if 'article' in item:
                print(f"{item['id']} watch={item['watch_id']} revision={item['revision']} {item['status']} stale={item['stale']}")
                print(item['article']['title'])
                print(f"published_at={item['article']['published_at']}")
                print(item['reason'] or item['error_code'] or '')
                print(item['evidence'] or '')
                continue
            state = "deleted" if item["deleted_at"] else "active" if item["active"] else "paused"
            print(f"{item['id']} revision={item['revision']} {state}: {item['name']}")
            print(item["description"])
            print("keywords=" + json.dumps(item["keywords"], ensure_ascii=False))
            print("excluded=" + json.dumps(item["excluded_keywords"], ensure_ascii=False))



def _notify(args, storage):
    from msalt.watch.notification_store import NotificationStore, clock
    notifications = NotificationStore(storage)
    if args.notify_command == 'status':
        return notifications.status(limit=args.limit)
    if args.notify_command in ('enable', 'disable'):
        return notifications.set_enabled(args.notify_command == 'enable', confirm=args.confirm)
    if args.notify_command == 'resolve':
        return notifications.resolve(args.delivery_id, outcome=args.outcome, confirm=args.confirm,
                                     evidence=args.evidence, message_id=args.message_id)
    now = None
    if args.now is not None:
        if not args.diagnostic_time:
            raise ValueError('--now requires explicit --diagnostic-time; production uses actual time')
        from datetime import datetime
        try:
            now = clock(datetime.fromisoformat(args.now))
        except ValueError:
            raise ValueError('now must be a timezone-aware ISO8601 datetime') from None
    if not notifications.status()['enabled']:
        notifications.recover()
        return {'state': 'disabled', 'delivery_id': None}
    # Existing allowFrom/private recipient configuration is the same news boundary.
    import asyncio
    import os

    from msalt.cli import _load_dotenv
    from msalt.news.reply_tool import authorized_target
    from msalt.watch.dispatcher import Dispatcher
    from msalt.watch.sender import BotAPI
    _load_dotenv()
    target = os.environ.get('TELEGRAM_USER_ID', '').strip()
    try:
        token = authorized_target(target)
    except ValueError:
        raise ValueError('Watch Telegram target configuration unavailable') from None
    print('Watch dispatch may send one Telegram message; no model calls.', file=sys.stderr)
    return asyncio.run(Dispatcher(notifications, post=BotAPI(token)).run(target, now=now))


def run_command(argv: list[str], *, db_path: str | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    storage = Storage(db_path if db_path is not None else DEFAULT_DB)
    try:
        storage.initialize()
    except (sqlite3.Error, OSError, ValueError):
        _emit({"error": "Watch database initialization failed"}, structured=args.json)
        return 1
    store = WatchStore(storage)
    try:
        if args.command == 'notify':
            result = _notify(args, storage)
        elif args.command in {'evaluate', 'evaluations'}:
            from msalt.watch.evaluation import Evaluator
            from msalt.watch.evaluation_store import EvaluationStore
            evaluations = EvaluationStore(storage)
            if args.command == 'evaluate':
                print('Watch evaluation model calls may incur API cost.', file=sys.stderr)
                result = Evaluator(evaluations).run(max_articles=args.max_articles,
                                                  max_calls=args.max_calls,
                                                  retry_errors=args.retry_errors)
            else:
                result = evaluations.list(watch_id=args.watch_id, status=args.status, limit=args.limit)
        elif args.command == "add":
            result = store.add(args.name, description=args.description,
                               keywords=_keywords(args.keywords_json),
                               excluded_keywords=_keywords(args.excluded_json))
        elif args.command == "list":
            result = store.list(include_deleted=args.all)
        elif args.command == "show":
            result = store.show(args.id)
        elif args.command == "update":
            changes = {}
            for field in ("name", "description"):
                if getattr(args, field) is not None:
                    changes[field] = getattr(args, field)
            for flag, field in (("keywords_json", "keywords"), ("excluded_json", "excluded_keywords")):
                if getattr(args, flag) is not None:
                    changes[field] = _keywords(getattr(args, flag))
            if not changes:
                raise ValueError("Update requires at least one condition field")
            result = store.update(args.id, expected_revision=args.expected_revision, **changes)
        else:
            if args.command == "delete" and not args.confirm:
                raise ValueError("Delete requires user confirmation and --confirm")
            result = getattr(store, args.command)(args.id, expected_revision=args.expected_revision)
        data = ([item if isinstance(item, dict) else asdict(item) for item in result]
                if isinstance(result, list) else result if isinstance(result, dict) else asdict(result))
        _emit(data, structured=args.json)
        return 0
    except ValueError as exc:
        _emit({"error": str(exc)}, structured=args.json)
        return 2
    except (sqlite3.Error, OSError):
        _emit({"error": "Watch database operation failed"}, structured=args.json)
        return 1


if __name__ == "__main__":
    raise SystemExit(run_command(sys.argv[1:]))
