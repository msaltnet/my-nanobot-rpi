"""msalt 생활 습관 CLI — 스킬에서 호출하는 엔트리포인트."""
import sys

from msalt.config import MsaltConfig
from msalt.storage import Storage
from msalt.lifestyle.sleep import SleepTracker
from msalt.lifestyle.todo import TodoManager
from msalt.lifestyle.tracker import LifeTracker


def _get_storage() -> Storage:
    config = MsaltConfig()
    storage = Storage(config.db_path)
    storage.initialize()
    return storage


def run_sleep_record(date: str, bedtime: str, wakeup: str, duration_min: int) -> str:
    storage = _get_storage()
    tracker = SleepTracker(storage)
    tracker.record(date, bedtime, wakeup, duration_min)
    return f"수면 기록 완료: {date} ({duration_min}분)"


def run_sleep_stats(days: int = 7) -> str:
    storage = _get_storage()
    tracker = SleepTracker(storage)
    return tracker.format_stats(days)


def run_todo_add(content: str, due_at: str | None = None) -> str:
    storage = _get_storage()
    manager = TodoManager(storage)
    todo_id = manager.add(content, due_at)
    return f"할일 추가 (#{todo_id}): {content}"


def run_todo_list() -> str:
    storage = _get_storage()
    manager = TodoManager(storage)
    return manager.format_list()


def run_todo_complete(todo_id: int) -> str:
    storage = _get_storage()
    manager = TodoManager(storage)
    manager.complete(todo_id)
    return f"할일 #{todo_id} 완료"


def run_log(text: str) -> str:
    storage = _get_storage()
    tracker = LifeTracker(storage)
    entry_id = tracker.log(text)
    return f"기록 완료 (#{entry_id}): {text}"


def run_life_summary(days: int = 7) -> str:
    storage = _get_storage()
    tracker = LifeTracker(storage)
    return tracker.format_summary(days)


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m msalt.lifestyle.cli [sleep-record|sleep-stats|todo-add|todo-list|todo-done|log|summary]")
        sys.exit(1)

    command = sys.argv[1]
    if command == "sleep-record":
        print(run_sleep_record(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])))
    elif command == "sleep-stats":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        print(run_sleep_stats(days))
    elif command == "todo-add":
        due = sys.argv[3] if len(sys.argv) > 3 else None
        print(run_todo_add(sys.argv[2], due))
    elif command == "todo-list":
        print(run_todo_list())
    elif command == "todo-done":
        print(run_todo_complete(int(sys.argv[2])))
    elif command == "log":
        print(run_log(" ".join(sys.argv[2:])))
    elif command == "summary":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        print(run_life_summary(days))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
