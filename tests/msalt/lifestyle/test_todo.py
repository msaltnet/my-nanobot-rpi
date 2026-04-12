import pytest

from msalt.storage import Storage
from msalt.lifestyle.todo import TodoManager


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    s = Storage(str(db_path))
    s.initialize()
    return s


def test_add_todo(storage):
    manager = TodoManager(storage)
    todo_id = manager.add("장보기")
    assert todo_id is not None
    todos = manager.list_pending()
    assert len(todos) == 1
    assert todos[0]["content"] == "장보기"
    assert todos[0]["status"] == "pending"


def test_add_todo_with_due(storage):
    manager = TodoManager(storage)
    manager.add("치과 예약", due_at="2026-04-13 15:00")
    todos = manager.list_pending()
    assert todos[0]["due_at"] == "2026-04-13 15:00"


def test_complete_todo(storage):
    manager = TodoManager(storage)
    todo_id = manager.add("장보기")
    manager.complete(todo_id)
    pending = manager.list_pending()
    assert len(pending) == 0


def test_list_pending_excludes_done(storage):
    manager = TodoManager(storage)
    id1 = manager.add("할일 1")
    id2 = manager.add("할일 2")
    manager.complete(id1)
    pending = manager.list_pending()
    assert len(pending) == 1
    assert pending[0]["content"] == "할일 2"


def test_get_due_soon(storage):
    manager = TodoManager(storage)
    manager.add("곧 할일", due_at="2026-04-12 15:00")
    manager.add("나중 할일", due_at="2099-12-31 23:59")
    due = manager.get_due_soon(before="2026-04-12 16:00")
    assert len(due) == 1
    assert due[0]["content"] == "곧 할일"
