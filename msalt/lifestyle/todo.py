from msalt.storage import Storage


class TodoManager:
    """할일을 관리한다."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def add(self, content: str, due_at: str | None = None) -> int:
        return self.storage.insert_todo(content, due_at)

    def complete(self, todo_id: int):
        self.storage.complete_todo(todo_id)

    def list_pending(self) -> list[dict]:
        return self.storage.get_pending_todos()

    def get_due_soon(self, before: str) -> list[dict]:
        return self.storage.get_todos_due_before(before)

    def format_list(self) -> str:
        todos = self.list_pending()
        if not todos:
            return "미완료 할일이 없습니다."

        lines = [f"할일 목록 ({len(todos)}건)", ""]
        for t in todos:
            due = f" (기한: {t['due_at']})" if t["due_at"] else ""
            lines.append(f"  [{t['id']}] {t['content']}{due}")
        return "\n".join(lines)
