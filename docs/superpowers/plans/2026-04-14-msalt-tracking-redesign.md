# msalt 생활 습관 트래킹 재설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 `msalt/lifestyle/` (수면·할일·자유기록) 모듈을 완전히 제거하고, 사용자 정의 추적 항목 + 30분 디스패처 + LLM 자연어 파싱 기반의 `msalt/tracking/` 시스템으로 대체한다.

**Architecture:** 두 SQLite 테이블(`tracked_items`, `records`) + 단일 cron 디스패처(systemd timer)로 능동 질문/누락 검출을 처리. 모든 자연어 입력은 gpt-5-mini 단발 호출로 시점·값을 추출. 사용자가 항목을 자연어로 추가/삭제할 수 있고, LLM이 schema/주기를 추론한 뒤 사용자 확인을 거쳐 등록.

**Tech Stack:** Python 3.11+, SQLite, OpenAI gpt-5-mini, httpx (Telegram Bot API 직접 호출), pytest, freezegun, systemd timer.

**Spec:** [docs/superpowers/specs/2026-04-14-msalt-tracking-redesign.md](../specs/2026-04-14-msalt-tracking-redesign.md)

---

## File Structure

### 신규 (구현 대상)

| 경로 | 책임 |
|------|------|
| `msalt/tracking/__init__.py` | 패키지 마커 (빈 파일) |
| `msalt/tracking/items.py` | TrackedItemManager — 항목 CRUD, 시드 |
| `msalt/tracking/records.py` | RecordManager — 기록 upsert/조회/통계 |
| `msalt/tracking/parser.py` | NaturalLanguageParser — LLM 단발 호출, ParsedRecord/ParsedItemIntent dataclass |
| `msalt/tracking/dispatcher.py` | Dispatcher — 시각 도래/미기록 검출, 메시지 빌드, Telegram 직접 발송 |
| `msalt/tracking/cli.py` | argparse 엔트리 (`dispatch`, `add`, `list`, `delete`, `record`, `summary`) |
| `msalt/tracking/__main__.py` | `python -m msalt.tracking` 위임 |
| `msalt/skills/tracking/SKILL.md` | 대화형 스킬 (기록·조회·항목 관리) |
| `deploy/msalt-tracking-dispatch.service` | systemd oneshot service |
| `deploy/msalt-tracking-dispatch.timer` | systemd timer (`*:00,30`) |
| `tests/msalt/tracking/test_items.py` | TrackedItemManager 테스트 |
| `tests/msalt/tracking/test_records.py` | RecordManager 테스트 |
| `tests/msalt/tracking/test_parser.py` | parser 테스트 (LLM 모킹) |
| `tests/msalt/tracking/test_dispatcher.py` | Dispatcher 테스트 (`now` 주입, Telegram 모킹) |
| `tests/msalt/tracking/test_cli.py` | CLI 테스트 |

### 수정 대상

| 경로 | 변경 |
|------|------|
| `msalt/storage.py` | `sleep_log`/`todos`/`life_log` 테이블·메서드 제거. `tracked_items`/`records` 테이블·메서드·기본 시드 추가 |
| `tests/msalt/test_storage.py` | 기존 lifestyle 관련 테스트 제거, 새 테이블 테스트 추가 |
| `msalt/nanobot-config.example.json` | (변경 없음 — cron은 systemd로 처리) |
| `deploy/setup-rpi.sh` | 신규 service/timer 설치 단계 추가 |
| `docs/msalt-prd.md` | §4.2 lifestyle → tracking 재작성, §8 ADR #11~#14 추가 |
| `docs/msalt-trd.md` | §3.3, §4(데이터 모델), §5(외부 의존성), §6(배포 토폴로지) 갱신 |
| `msalt-nanobot.md` | 기능 섹션, 디렉토리 트리 갱신 |
| `msalt/workspace/SOUL.md` | "할일" 언급 제거, tracking 시스템 설명 |
| `msalt/workspace/USER.md` | 루틴 갱신 |
| `docs/msalt-setup.md`, `docs/msalt-rpi-deploy.md` | tracking 관련 단계 추가 |

### 삭제 대상

| 경로 | 비고 |
|------|------|
| `msalt/lifestyle/` (전체 디렉토리) | 7개 파일 |
| `msalt/skills/lifestyle/` | SKILL.md |
| `tests/msalt/lifestyle/` (전체 디렉토리) | 5개 파일 |

---

## 디스패처 트리거 방식 결정

Spec §9에서 "nanobot config에 cron 엔트리 추가"로 가정했지만, 실제 nanobot의 `Config` 스키마에는 사용자 정의 cron 섹션이 없고 `CronService`는 동적 등록 전용이다. Plan 단계에서 다음과 같이 확정한다:

**채택**: **systemd timer + Telegram Bot API 직접 호출**

- `python -m msalt.tracking dispatch` 가 1회 실행 → 디스패처 결과(메시지 리스트) → 환경변수 `TELEGRAM_BOT_TOKEN`/`TELEGRAM_USER_ID`로 직접 `sendMessage` 호출
- systemd timer (`OnCalendar=*:00,30`) 가 30분마다 oneshot service 트리거
- nanobot agent 호출 경로를 거치지 않으므로 단순·결정적·테스트 용이
- 사용자가 답하면 nanobot이 텔레그램 polling으로 받아 tracking 스킬로 처리 (기존 경로)

**대안 기각 이유**:
- nanobot에 신규 cron 섹션 추가: 본체 schema 수정 필요, msalt 격리 원칙 위배
- `croniter`로 in-process 스케줄링: 별도 데몬 프로세스 필요, OOM 위험
- Dream/Heartbeat 같은 내장 서비스 fork: 본체 수정 동반

**cron 표현 변경**: spec §9의 `*/30 * * * *`는 systemd `OnCalendar=*:00,30`으로 등가 변경.

---

## Phase A: lifestyle 제거 (Tasks 1-3)

### Task 1: lifestyle 디렉토리·테스트 제거

**Files:**
- Delete: `msalt/lifestyle/` (전체)
- Delete: `msalt/skills/lifestyle/` (전체)
- Delete: `tests/msalt/lifestyle/` (전체)

- [ ] **Step 1: 삭제 대상 확인**

```bash
ls -R msalt/lifestyle msalt/skills/lifestyle tests/msalt/lifestyle
```

Expected: 13개 파일 출력 (7+1+5).

- [ ] **Step 2: 디렉토리 삭제**

```bash
rm -rf msalt/lifestyle msalt/skills/lifestyle tests/msalt/lifestyle
```

- [ ] **Step 3: 잔존 참조 검증**

```bash
grep -rn "msalt.lifestyle\|msalt/lifestyle\|from msalt import lifestyle" msalt/ tests/ 2>/dev/null || echo "no refs"
```

Expected: `no refs`. (문서·deploy 파일에는 남을 수 있음 — 후속 task에서 처리)

- [ ] **Step 4: 테스트 스위트 통과 확인**

```bash
pytest tests/msalt -q
```

Expected: lifestyle 테스트 사라지고 나머지(news/storage)만 통과.

- [ ] **Step 5: 커밋**

```bash
git add -A msalt/lifestyle msalt/skills/lifestyle tests/msalt/lifestyle
git commit -m "refactor(msalt): remove lifestyle module ahead of tracking redesign"
```

---

### Task 2: storage.py에서 lifestyle 테이블·메서드 제거

**Files:**
- Modify: `msalt/storage.py`
- Modify: `tests/msalt/test_storage.py`

- [ ] **Step 1: 실패 테스트 작성 — 제거된 메서드는 더 이상 존재하지 않아야 함**

`tests/msalt/test_storage.py`에 기존 sleep/todo/life_log 테스트가 있다면 모두 삭제하거나, 명시적인 부존재 테스트로 대체:

```python
def test_storage_does_not_expose_lifestyle_methods():
    from msalt.storage import Storage
    legacy = ["upsert_sleep", "get_sleep_log", "get_sleep_logs_since",
              "insert_todo", "complete_todo", "get_pending_todos",
              "get_todos_due_before", "insert_life_log",
              "get_life_logs_since", "get_life_log_category_counts"]
    for name in legacy:
        assert not hasattr(Storage, name), f"{name} should be removed"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/msalt/test_storage.py::test_storage_does_not_expose_lifestyle_methods -v
```

Expected: FAIL (메서드 아직 존재).

- [ ] **Step 3: storage.py에서 lifestyle 관련 제거**

`msalt/storage.py`를 다음과 같이 수정:

1. `initialize()` 내 `executescript`에서 `sleep_log`, `todos`, `life_log` CREATE 문 제거.
2. 메서드 제거: `upsert_sleep`, `get_sleep_log`, `get_sleep_logs_since`, `insert_todo`, `complete_todo`, `get_pending_todos`, `get_todos_due_before`, `insert_life_log`, `get_life_logs_since`, `get_life_log_category_counts`.

수정 후 `initialize()`는 `news_articles` CREATE만 남는다.

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/msalt/test_storage.py -v
```

Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add msalt/storage.py tests/msalt/test_storage.py
git commit -m "refactor(msalt): drop lifestyle tables and methods from Storage"
```

---

### Task 3: lifestyle 잔존 문서 참조 임시 비활성화

**Files:**
- Modify: `msalt/skills/news/SKILL.md` (참조 없으면 skip)
- Modify: `msalt-nanobot.md` (lifestyle 언급에 "(deprecated)" 마크)

이 단계는 **임시 표시**다. 최종 문서 갱신은 Task 11에서 일괄 처리.

- [ ] **Step 1: lifestyle 잔존 참조 식별**

```bash
grep -rn "lifestyle" msalt-nanobot.md docs/ deploy/ 2>/dev/null
```

- [ ] **Step 2: 즉시 깨질 명령(예: `python -m msalt.lifestyle ...`) 주석화**

각 발견 위치마다 한 줄 추가:
> `> NOTE: lifestyle 모듈은 제거됨. tracking으로 대체 예정 (2026-04-14 spec 참조).`

- [ ] **Step 3: 커밋**

```bash
git add -u
git commit -m "docs(msalt): mark lifestyle references as deprecated pending tracking"
```

---

## Phase B: tracking 인프라 구축 (Tasks 4-7)

### Task 4: storage.py에 tracked_items/records 테이블·메서드 추가

**Files:**
- Modify: `msalt/storage.py`
- Modify: `tests/msalt/test_storage.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/msalt/test_storage.py`에 추가:

```python
import sqlite3
import pytest
from msalt.storage import Storage


@pytest.fixture
def storage(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    return s


def test_initialize_creates_tracking_tables(storage):
    conn = sqlite3.connect(storage.db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    conn.close()
    names = {r[0] for r in rows}
    assert "tracked_items" in names
    assert "records" in names


def test_insert_and_get_tracked_item(storage):
    storage.insert_tracked_item("수면", "duration", None, "08:00")
    item = storage.get_tracked_item_by_name("수면")
    assert item["name"] == "수면"
    assert item["schema"] == "duration"
    assert item["unit"] is None
    assert item["schedule_time"] == "08:00"
    assert item["frequency"] == "daily"


def test_insert_tracked_item_unique_name(storage):
    storage.insert_tracked_item("수면", "duration", None, "08:00")
    with pytest.raises(sqlite3.IntegrityError):
        storage.insert_tracked_item("수면", "duration", None, "09:00")


def test_list_tracked_items(storage):
    storage.insert_tracked_item("a", "boolean", None, "10:00")
    storage.insert_tracked_item("b", "quantity", "잔", "22:00")
    items = storage.list_tracked_items()
    assert [i["name"] for i in items] == ["a", "b"]


def test_delete_tracked_item_cascades_records(storage):
    storage.insert_tracked_item("음주", "quantity", "잔", "22:00")
    item = storage.get_tracked_item_by_name("음주")
    storage.upsert_record(item["id"], "2026-04-13", value_num=2.0,
                          raw_input="2잔")
    storage.delete_tracked_item("음주")
    assert storage.get_tracked_item_by_name("음주") is None
    conn = sqlite3.connect(storage.db_path)
    cnt = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    conn.close()
    assert cnt == 0


def test_upsert_record_replaces_same_date(storage):
    storage.insert_tracked_item("수면", "duration", None, "08:00")
    item = storage.get_tracked_item_by_name("수면")
    storage.upsert_record(item["id"], "2026-04-13", value_num=420,
                          raw_input="7시간")
    storage.upsert_record(item["id"], "2026-04-13", value_num=480,
                          raw_input="8시간")
    recs = storage.get_records_for_item(item["id"], days=7,
                                        ref_date="2026-04-14")
    assert len(recs) == 1
    assert recs[0]["value_num"] == 480
    assert recs[0]["raw_input"] == "8시간"


def test_get_records_for_item_filters_by_days(storage):
    storage.insert_tracked_item("수면", "duration", None, "08:00")
    item = storage.get_tracked_item_by_name("수면")
    storage.upsert_record(item["id"], "2026-04-01", value_num=400,
                          raw_input="x")
    storage.upsert_record(item["id"], "2026-04-13", value_num=480,
                          raw_input="y")
    recs = storage.get_records_for_item(item["id"], days=7,
                                        ref_date="2026-04-14")
    assert [r["recorded_for"] for r in recs] == ["2026-04-13"]


def test_record_exists_for_date(storage):
    storage.insert_tracked_item("수면", "duration", None, "08:00")
    item = storage.get_tracked_item_by_name("수면")
    assert storage.record_exists(item["id"], "2026-04-13") is False
    storage.upsert_record(item["id"], "2026-04-13", value_num=480,
                          raw_input="8h")
    assert storage.record_exists(item["id"], "2026-04-13") is True
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/msalt/test_storage.py -q
```

Expected: 다수 FAIL (테이블·메서드 부재).

- [ ] **Step 3: storage.py 구현**

`msalt/storage.py`를 다음과 같이 수정:

1. `initialize()`의 `executescript`에 추가:

```sql
CREATE TABLE IF NOT EXISTS tracked_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    schema TEXT NOT NULL,
    unit TEXT,
    schedule_time TEXT NOT NULL,
    frequency TEXT NOT NULL DEFAULT 'daily',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES tracked_items(id) ON DELETE CASCADE,
    recorded_for TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    value_text TEXT,
    value_num REAL,
    value_bool INTEGER,
    raw_input TEXT NOT NULL,
    UNIQUE(item_id, recorded_for)
);

CREATE INDEX IF NOT EXISTS idx_records_for ON records(recorded_for);
CREATE INDEX IF NOT EXISTS idx_records_item ON records(item_id, recorded_for DESC);
```

2. `_connect()` 호출 시 외래키 활성화:

```python
def _connect(self):
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

3. 메서드 추가:

```python
def insert_tracked_item(self, name: str, schema: str,
                        unit: str | None, schedule_time: str,
                        frequency: str = "daily") -> int:
    conn = self._connect()
    try:
        cursor = conn.execute(
            "INSERT INTO tracked_items (name, schema, unit, schedule_time, frequency) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, schema, unit, schedule_time, frequency),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def get_tracked_item_by_name(self, name: str) -> dict | None:
    conn = self._connect()
    try:
        row = conn.execute(
            "SELECT * FROM tracked_items WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def list_tracked_items(self) -> list[dict]:
    conn = self._connect()
    try:
        rows = conn.execute(
            "SELECT * FROM tracked_items ORDER BY name ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def delete_tracked_item(self, name: str) -> None:
    conn = self._connect()
    try:
        conn.execute("DELETE FROM tracked_items WHERE name = ?", (name,))
        conn.commit()
    finally:
        conn.close()

def upsert_record(self, item_id: int, recorded_for: str,
                  value_text: str | None = None,
                  value_num: float | None = None,
                  value_bool: bool | None = None,
                  raw_input: str = "") -> None:
    conn = self._connect()
    try:
        bool_int = None if value_bool is None else int(bool(value_bool))
        conn.execute(
            "INSERT INTO records (item_id, recorded_for, value_text, value_num, "
            "value_bool, raw_input) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(item_id, recorded_for) DO UPDATE SET "
            "value_text=excluded.value_text, value_num=excluded.value_num, "
            "value_bool=excluded.value_bool, raw_input=excluded.raw_input, "
            "recorded_at=datetime('now')",
            (item_id, recorded_for, value_text, value_num, bool_int, raw_input),
        )
        conn.commit()
    finally:
        conn.close()

def get_records_for_item(self, item_id: int, days: int,
                         ref_date: str) -> list[dict]:
    """ref_date 기준 최근 days일 기록 (recorded_for 내림차순)."""
    from datetime import date, timedelta
    ref = date.fromisoformat(ref_date)
    since = (ref - timedelta(days=days - 1)).isoformat()
    conn = self._connect()
    try:
        rows = conn.execute(
            "SELECT * FROM records WHERE item_id = ? AND recorded_for >= ? "
            "ORDER BY recorded_for DESC",
            (item_id, since),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def record_exists(self, item_id: int, recorded_for: str) -> bool:
    conn = self._connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM records WHERE item_id = ? AND recorded_for = ?",
            (item_id, recorded_for),
        ).fetchone()
        return row is not None
    finally:
        conn.close()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/msalt/test_storage.py -q
```

Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add msalt/storage.py tests/msalt/test_storage.py
git commit -m "feat(msalt): add tracked_items/records tables to Storage"
```

---

### Task 5: TrackedItemManager 구현 + 시드

**Files:**
- Create: `msalt/tracking/__init__.py`
- Create: `msalt/tracking/items.py`
- Create: `tests/msalt/tracking/test_items.py`

- [ ] **Step 1: 빈 패키지 마커 생성**

`msalt/tracking/__init__.py`:

```python
```

(빈 파일)

- [ ] **Step 2: 실패 테스트 작성**

`tests/msalt/tracking/test_items.py`:

```python
import pytest
from msalt.storage import Storage
from msalt.tracking.items import (
    TrackedItemManager, ItemAlreadyExists, ItemNotFound, DEFAULT_SEEDS,
)


@pytest.fixture
def storage(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    return s


def test_add_and_get_item(storage):
    mgr = TrackedItemManager(storage)
    mgr.add("수면", "duration", None, "08:00")
    item = mgr.get("수면")
    assert item is not None
    assert item["schema"] == "duration"


def test_add_duplicate_raises(storage):
    mgr = TrackedItemManager(storage)
    mgr.add("수면", "duration", None, "08:00")
    with pytest.raises(ItemAlreadyExists):
        mgr.add("수면", "duration", None, "09:00")


def test_invalid_schema_rejected(storage):
    mgr = TrackedItemManager(storage)
    with pytest.raises(ValueError):
        mgr.add("x", "invalid", None, "08:00")


def test_invalid_schedule_time_rejected(storage):
    mgr = TrackedItemManager(storage)
    with pytest.raises(ValueError):
        mgr.add("x", "duration", None, "25:00")
    with pytest.raises(ValueError):
        mgr.add("x", "duration", None, "08:99")
    with pytest.raises(ValueError):
        mgr.add("x", "duration", None, "8:00")  # 두 자리 강제


def test_quantity_requires_unit(storage):
    mgr = TrackedItemManager(storage)
    with pytest.raises(ValueError):
        mgr.add("음주", "quantity", None, "22:00")


def test_non_quantity_unit_must_be_none(storage):
    mgr = TrackedItemManager(storage)
    with pytest.raises(ValueError):
        mgr.add("수면", "duration", "분", "08:00")


def test_list_all_returns_sorted(storage):
    mgr = TrackedItemManager(storage)
    mgr.add("b", "boolean", None, "10:00")
    mgr.add("a", "boolean", None, "11:00")
    items = mgr.list_all()
    assert [i["name"] for i in items] == ["a", "b"]


def test_delete_removes_item(storage):
    mgr = TrackedItemManager(storage)
    mgr.add("수면", "duration", None, "08:00")
    mgr.delete("수면")
    assert mgr.get("수면") is None


def test_delete_nonexistent_raises(storage):
    mgr = TrackedItemManager(storage)
    with pytest.raises(ItemNotFound):
        mgr.delete("없음")


def test_seed_defaults_when_empty(storage):
    mgr = TrackedItemManager(storage)
    mgr.seed_defaults()
    items = mgr.list_all()
    names = {i["name"] for i in items}
    assert names == {s["name"] for s in DEFAULT_SEEDS}


def test_seed_defaults_no_op_when_not_empty(storage):
    mgr = TrackedItemManager(storage)
    mgr.add("기존", "boolean", None, "12:00")
    mgr.seed_defaults()
    items = mgr.list_all()
    assert [i["name"] for i in items] == ["기존"]
```

- [ ] **Step 3: 테스트 실행 — 실패 확인**

```bash
pytest tests/msalt/tracking/test_items.py -q
```

Expected: ImportError (모듈 없음).

- [ ] **Step 4: items.py 구현**

`msalt/tracking/items.py`:

```python
"""TrackedItem 관리: CRUD + 검증 + 기본 시드."""
from __future__ import annotations

import re
from typing import Final

from msalt.storage import Storage


VALID_SCHEMAS: Final = ("freetext", "duration", "quantity", "boolean")
TIME_RE: Final = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

DEFAULT_SEEDS: Final = [
    {"name": "수면", "schema": "duration", "unit": None, "schedule_time": "08:00"},
    {"name": "음주", "schema": "quantity", "unit": "잔", "schedule_time": "22:00"},
    {"name": "영어공부", "schema": "duration", "unit": None, "schedule_time": "22:00"},
]


class ItemAlreadyExists(Exception):
    pass


class ItemNotFound(Exception):
    pass


class TrackedItemManager:
    def __init__(self, storage: Storage):
        self.storage = storage

    @staticmethod
    def _validate(name: str, schema: str, unit: str | None,
                  schedule_time: str) -> None:
        if not name:
            raise ValueError("name must be non-empty")
        if schema not in VALID_SCHEMAS:
            raise ValueError(
                f"schema must be one of {VALID_SCHEMAS}, got {schema!r}"
            )
        if not TIME_RE.match(schedule_time):
            raise ValueError(
                f"schedule_time must be 'HH:MM' (00-23:00-59), got {schedule_time!r}"
            )
        if schema == "quantity" and not unit:
            raise ValueError("schema=quantity requires unit")
        if schema != "quantity" and unit is not None:
            raise ValueError("unit only allowed for schema=quantity")

    def add(self, name: str, schema: str, unit: str | None,
            schedule_time: str, frequency: str = "daily") -> int:
        self._validate(name, schema, unit, schedule_time)
        if self.storage.get_tracked_item_by_name(name) is not None:
            raise ItemAlreadyExists(name)
        return self.storage.insert_tracked_item(
            name, schema, unit, schedule_time, frequency
        )

    def get(self, name: str) -> dict | None:
        return self.storage.get_tracked_item_by_name(name)

    def list_all(self) -> list[dict]:
        return self.storage.list_tracked_items()

    def delete(self, name: str) -> None:
        if self.storage.get_tracked_item_by_name(name) is None:
            raise ItemNotFound(name)
        self.storage.delete_tracked_item(name)

    def seed_defaults(self) -> int:
        """빈 테이블이면 기본 항목들 삽입. 그렇지 않으면 no-op. 삽입 수 반환."""
        if self.list_all():
            return 0
        for seed in DEFAULT_SEEDS:
            self.storage.insert_tracked_item(
                seed["name"], seed["schema"], seed["unit"],
                seed["schedule_time"], "daily",
            )
        return len(DEFAULT_SEEDS)
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/msalt/tracking/test_items.py -q
```

Expected: PASS (10개).

- [ ] **Step 6: 커밋**

```bash
git add msalt/tracking/__init__.py msalt/tracking/items.py tests/msalt/tracking/test_items.py
git commit -m "feat(msalt): TrackedItemManager with validation and default seeds"
```

---

### Task 6: RecordManager 구현 (upsert + 통계)

**Files:**
- Create: `msalt/tracking/records.py`
- Create: `tests/msalt/tracking/test_records.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/msalt/tracking/test_records.py`:

```python
import pytest
from msalt.storage import Storage
from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager


@pytest.fixture
def setup(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    items = TrackedItemManager(s)
    records = RecordManager(s, items)
    return s, items, records


def test_upsert_freetext(setup):
    _, items, records = setup
    items.add("메모", "freetext", None, "23:00")
    records.upsert("메모", "2026-04-13", raw_input="기분 좋음",
                   value_text="기분 좋음")
    recs = records.recent("메모", days=1, ref_date="2026-04-13")
    assert len(recs) == 1
    assert recs[0]["value_text"] == "기분 좋음"


def test_upsert_unknown_item_raises(setup):
    _, _, records = setup
    with pytest.raises(KeyError):
        records.upsert("없음", "2026-04-13", raw_input="x")


def test_upsert_overwrites_same_date(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    records.upsert("수면", "2026-04-13", value_num=420, raw_input="7h")
    records.upsert("수면", "2026-04-13", value_num=480, raw_input="8h")
    recs = records.recent("수면", days=1, ref_date="2026-04-13")
    assert len(recs) == 1
    assert recs[0]["value_num"] == 480


def test_summarize_duration(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    records.upsert("수면", "2026-04-12", value_num=420, raw_input="7h")
    records.upsert("수면", "2026-04-13", value_num=480, raw_input="8h")
    summary = records.summarize("수면", days=7, ref_date="2026-04-13")
    assert "수면" in summary
    assert "2회" in summary
    assert "평균" in summary
    assert "450" in summary or "7시간 30분" in summary


def test_summarize_quantity(setup):
    _, items, records = setup
    items.add("음주", "quantity", "잔", "22:00")
    records.upsert("음주", "2026-04-12", value_num=2.0, raw_input="2잔")
    records.upsert("음주", "2026-04-13", value_num=4.0, raw_input="4잔")
    summary = records.summarize("음주", days=7, ref_date="2026-04-13")
    assert "음주" in summary
    assert "잔" in summary
    assert "6" in summary  # 합계 6잔
    assert "평균" in summary  # 평균 3잔


def test_summarize_boolean(setup):
    _, items, records = setup
    items.add("운동", "boolean", None, "20:00")
    records.upsert("운동", "2026-04-12", value_bool=True, raw_input="함")
    records.upsert("운동", "2026-04-13", value_bool=False, raw_input="안함")
    summary = records.summarize("운동", days=7, ref_date="2026-04-13")
    assert "운동" in summary
    assert "1/2" in summary or "50%" in summary


def test_summarize_freetext_lists_recent(setup):
    _, items, records = setup
    items.add("메모", "freetext", None, "23:00")
    records.upsert("메모", "2026-04-12", value_text="피곤",
                   raw_input="피곤")
    records.upsert("메모", "2026-04-13", value_text="좋음",
                   raw_input="좋음")
    summary = records.summarize("메모", days=7, ref_date="2026-04-13")
    assert "피곤" in summary
    assert "좋음" in summary


def test_summarize_no_records(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    summary = records.summarize("수면", days=7, ref_date="2026-04-13")
    assert "기록 없음" in summary or "없" in summary


def test_recent_returns_empty_for_unknown_item(setup):
    _, _, records = setup
    with pytest.raises(KeyError):
        records.recent("없음", days=7, ref_date="2026-04-13")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/msalt/tracking/test_records.py -q
```

Expected: ImportError.

- [ ] **Step 3: records.py 구현**

`msalt/tracking/records.py`:

```python
"""Record 관리: upsert, 조회, schema별 통계 포맷."""
from __future__ import annotations

from msalt.storage import Storage
from msalt.tracking.items import TrackedItemManager


def _format_minutes(total: float) -> str:
    """duration: 분(float) → '7시간 30분'."""
    minutes = int(round(total))
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}시간 {m}분"
    if h:
        return f"{h}시간"
    return f"{m}분"


class RecordManager:
    def __init__(self, storage: Storage, items: TrackedItemManager):
        self.storage = storage
        self.items = items

    def _resolve(self, name: str) -> dict:
        item = self.items.get(name)
        if item is None:
            raise KeyError(f"unknown tracked item: {name}")
        return item

    def upsert(self, name: str, recorded_for: str, *,
               raw_input: str,
               value_text: str | None = None,
               value_num: float | None = None,
               value_bool: bool | None = None) -> None:
        item = self._resolve(name)
        self.storage.upsert_record(
            item["id"], recorded_for,
            value_text=value_text, value_num=value_num,
            value_bool=value_bool, raw_input=raw_input,
        )

    def recent(self, name: str, days: int, ref_date: str) -> list[dict]:
        item = self._resolve(name)
        return self.storage.get_records_for_item(
            item["id"], days=days, ref_date=ref_date
        )

    def summarize(self, name: str, days: int, ref_date: str) -> str:
        item = self._resolve(name)
        recs = self.storage.get_records_for_item(
            item["id"], days=days, ref_date=ref_date
        )
        if not recs:
            return f"{name}: 최근 {days}일 기록 없음"

        schema = item["schema"]
        n = len(recs)

        if schema == "duration":
            total = sum(r["value_num"] or 0 for r in recs)
            avg = total / n
            return (f"{name}: 최근 {days}일 {n}회 기록, "
                    f"평균 {_format_minutes(avg)} (총 {_format_minutes(total)})")

        if schema == "quantity":
            unit = item["unit"] or ""
            total = sum(r["value_num"] or 0 for r in recs)
            avg = total / n
            return (f"{name}: 최근 {days}일 {n}회 기록, "
                    f"합계 {total:g}{unit}, 평균 {avg:g}{unit}")

        if schema == "boolean":
            done = sum(1 for r in recs if r["value_bool"])
            pct = done * 100 // n
            return f"{name}: 최근 {days}일 {done}/{n}회 수행 ({pct}%)"

        # freetext
        lines = [f"{name}: 최근 {days}일 {n}건"]
        for r in recs[:5]:
            lines.append(f"  {r['recorded_for']}: {r['value_text'] or r['raw_input']}")
        return "\n".join(lines)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/msalt/tracking/test_records.py -q
```

Expected: PASS (9개).

- [ ] **Step 5: 커밋**

```bash
git add msalt/tracking/records.py tests/msalt/tracking/test_records.py
git commit -m "feat(msalt): RecordManager with upsert and per-schema summaries"
```

---

### Task 7: NaturalLanguageParser (LLM 기반)

**Files:**
- Create: `msalt/tracking/parser.py`
- Create: `tests/msalt/tracking/test_parser.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/msalt/tracking/test_parser.py`:

```python
import json
from unittest.mock import MagicMock
import pytest

from msalt.tracking.parser import (
    NaturalLanguageParser, ParsedRecord, ParsedItemIntent,
)


def _mock_client_with(content: str) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    client.chat.completions.create.return_value = response
    return client


def test_parse_record_extracts_fields():
    payload = {
        "item_name": "수면",
        "recorded_for": "2026-04-13",
        "value_num": 480,
        "value_text": None,
        "value_bool": None,
        "confidence": 0.9,
    }
    client = _mock_client_with(json.dumps(payload))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_record(
        "어제 11시에 자서 7시에 일어났어",
        known_items=[{"name": "수면", "schema": "duration", "unit": None}],
        now="2026-04-14T08:30:00+09:00",
    )
    assert isinstance(result, ParsedRecord)
    assert result.item_name == "수면"
    assert result.recorded_for == "2026-04-13"
    assert result.value_num == 480
    assert result.confidence == 0.9


def test_parse_record_returns_none_when_no_match():
    payload = {"item_name": None, "recorded_for": "2026-04-14",
               "value_num": None, "value_text": None,
               "value_bool": None, "confidence": 0.0}
    client = _mock_client_with(json.dumps(payload))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_record(
        "오늘 날씨 좋다",
        known_items=[{"name": "수면", "schema": "duration", "unit": None}],
        now="2026-04-14T08:30:00+09:00",
    )
    assert result.item_name is None


def test_parse_record_handles_invalid_json_gracefully():
    client = _mock_client_with("not json at all")
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_record(
        "x", known_items=[], now="2026-04-14T08:30:00+09:00"
    )
    assert result.item_name is None
    assert result.confidence == 0.0


def test_parse_item_intent_extracts_fields():
    payload = {
        "name": "독서",
        "schema": "duration",
        "unit": None,
        "schedule_time": "22:00",
    }
    client = _mock_client_with(json.dumps(payload))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_item_intent(
        "독서 시간도 매일 자기 전에 기록할래"
    )
    assert isinstance(result, ParsedItemIntent)
    assert result.name == "독서"
    assert result.schema == "duration"
    assert result.schedule_time == "22:00"


def test_parse_item_intent_quantity_with_unit():
    payload = {"name": "물", "schema": "quantity", "unit": "잔",
               "schedule_time": "22:00"}
    client = _mock_client_with(json.dumps(payload))
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    result = parser.parse_item_intent("매일 물 몇 잔 마셨는지")
    assert result.unit == "잔"


def test_parse_item_intent_invalid_json():
    client = _mock_client_with("garbage")
    parser = NaturalLanguageParser(client=client, model="gpt-5-mini")
    with pytest.raises(ValueError):
        parser.parse_item_intent("x")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/msalt/tracking/test_parser.py -q
```

Expected: ImportError.

- [ ] **Step 3: parser.py 구현**

`msalt/tracking/parser.py`:

```python
"""LLM 기반 자연어 파서: 기록 입력 / 항목 추가 의도."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedRecord:
    item_name: str | None
    recorded_for: str
    value_text: str | None
    value_num: float | None
    value_bool: bool | None
    confidence: float


@dataclass
class ParsedItemIntent:
    name: str
    schema: str  # 'freetext'|'duration'|'quantity'|'boolean'
    unit: str | None
    schedule_time: str  # 'HH:MM'


_RECORD_SYSTEM = """\
사용자가 일상 기록(수면·음주·운동 등)을 자연어로 입력했다.
주어진 known_items 중 하나에 매칭되는지 판단하고, 해당하는 시점·값을 추출하라.
응답은 반드시 다음 JSON 한 줄만 출력:
{"item_name": str|null, "recorded_for": "YYYY-MM-DD", "value_text": str|null,
 "value_num": number|null, "value_bool": bool|null, "confidence": 0~1}

규칙:
- "어제"/"지난주 화요일" 등 상대 시점은 now 기준으로 절대 날짜 변환.
- duration schema → value_num은 분 단위 정수.
- quantity schema → value_num은 숫자, 단위는 item의 unit 사용.
- boolean schema → value_bool.
- freetext schema → value_text에 원문 핵심.
- 매칭 없거나 모호하면 item_name=null, confidence=0.
"""

_ITEM_INTENT_SYSTEM = """\
사용자가 새로 추적할 항목을 자연어로 제안했다.
다음 JSON 한 줄만 출력:
{"name": str, "schema": "freetext"|"duration"|"quantity"|"boolean",
 "unit": str|null, "schedule_time": "HH:MM"}

규칙:
- name은 한국어 짧은 명사 (예: "독서", "물 섭취").
- 시간을 측정 → duration. 횟수·양 → quantity (unit 필수, 예: "잔", "회").
- 했음/안함만 → boolean. 자유 메모 → freetext.
- schedule_time은 사용자 의도 기반 24시간 HH:MM (아침=08:00, 자기 전=22:00 등).
"""


class NaturalLanguageParser:
    def __init__(self, client: Any, model: str):
        self.client = client
        self.model = model

    def _chat(self, system: str, user: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content or ""

    def parse_record(self, text: str, known_items: list[dict],
                     now: str) -> ParsedRecord:
        items_view = [
            {"name": i["name"], "schema": i["schema"], "unit": i.get("unit")}
            for i in known_items
        ]
        user = json.dumps({
            "now": now,
            "known_items": items_view,
            "input": text,
        }, ensure_ascii=False)
        raw = self._chat(_RECORD_SYSTEM, user)
        try:
            data = json.loads(raw)
            return ParsedRecord(
                item_name=data.get("item_name"),
                recorded_for=data.get("recorded_for") or now[:10],
                value_text=data.get("value_text"),
                value_num=data.get("value_num"),
                value_bool=data.get("value_bool"),
                confidence=float(data.get("confidence", 0)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return ParsedRecord(
                item_name=None, recorded_for=now[:10],
                value_text=None, value_num=None, value_bool=None,
                confidence=0.0,
            )

    def parse_item_intent(self, text: str) -> ParsedItemIntent:
        raw = self._chat(_ITEM_INTENT_SYSTEM, text)
        try:
            data = json.loads(raw)
            return ParsedItemIntent(
                name=data["name"],
                schema=data["schema"],
                unit=data.get("unit"),
                schedule_time=data["schedule_time"],
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise ValueError(f"failed to parse item intent: {raw!r}") from e
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/msalt/tracking/test_parser.py -q
```

Expected: PASS (6개).

- [ ] **Step 5: 커밋**

```bash
git add msalt/tracking/parser.py tests/msalt/tracking/test_parser.py
git commit -m "feat(msalt): LLM-backed natural language parser for tracking"
```

---

## Phase C: 디스패처 + CLI (Tasks 8-9)

### Task 8: Dispatcher 구현

**Files:**
- Create: `msalt/tracking/dispatcher.py`
- Create: `tests/msalt/tracking/test_dispatcher.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/msalt/tracking/test_dispatcher.py`:

```python
from datetime import datetime, time
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import pytest

from msalt.storage import Storage
from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager
from msalt.tracking.dispatcher import Dispatcher, DispatchMessage


KST = ZoneInfo("Asia/Seoul")


@pytest.fixture
def setup(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    items = TrackedItemManager(s)
    records = RecordManager(s, items)
    return s, items, records


def test_no_items_no_messages(setup):
    _, items, records = setup
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 8, 0, tzinfo=KST))
    assert msgs == []


def test_scheduled_item_within_window_triggers_question(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 8, 5, tzinfo=KST))
    assert len(msgs) == 1
    assert msgs[0].kind == "scheduled"
    assert msgs[0].item_name == "수면"


def test_outside_window_no_scheduled_message(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 7, 30, tzinfo=KST))
    # 7:30 → 다음 슬롯은 7:30, 윈도우는 [7:30, 8:00). 8:00은 미포함.
    assert all(m.item_name != "수면" for m in msgs if m.kind == "scheduled")


def test_missed_item_after_schedule_triggers_alert(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 12, 0, tzinfo=KST))
    assert len(msgs) == 1
    assert msgs[0].kind == "missed"
    assert msgs[0].item_name == "수면"


def test_recorded_item_no_missed_alert(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    records.upsert("수면", "2026-04-14", value_num=480, raw_input="8h")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 12, 0, tzinfo=KST))
    assert msgs == []


def test_scheduled_takes_priority_over_missed(setup):
    """같은 회차에 scheduled로 잡히면 missed에서 제외."""
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=datetime(2026, 4, 14, 8, 15, tzinfo=KST))
    kinds = {m.kind for m in msgs if m.item_name == "수면"}
    assert kinds == {"scheduled"}


def test_run_calls_telegram_send_for_each_message(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    items.add("음주", "quantity", "잔", "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=datetime(2026, 4, 14, 23, 0, tzinfo=KST))
    # 22:00 이후이므로 음주는 missed
    assert send.call_count >= 1
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/msalt/tracking/test_dispatcher.py -q
```

Expected: ImportError.

- [ ] **Step 3: dispatcher.py 구현**

`msalt/tracking/dispatcher.py`:

```python
"""디스패처: 시각 도래 / 누락 항목 검출 후 Telegram 메시지 발송."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Literal
from zoneinfo import ZoneInfo

from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager


KST = ZoneInfo("Asia/Seoul")
WINDOW_MINUTES = 30


@dataclass
class DispatchMessage:
    kind: Literal["scheduled", "missed"]
    item_name: str
    text: str


def _parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _question_text(item: dict) -> str:
    name = item["name"]
    schema = item["schema"]
    unit = item.get("unit") or ""
    if schema == "duration":
        return f"⏰ '{name}' 기록할 시간이야. 얼마나 했는지 알려줘."
    if schema == "quantity":
        return f"⏰ '{name}' 기록할 시간이야. 몇 {unit}인지 알려줘."
    if schema == "boolean":
        return f"⏰ '{name}' 했어?"
    return f"⏰ '{name}' 한 줄 메모 남겨줘."


def _missed_text(item: dict, recorded_for: str) -> str:
    return f"📝 {recorded_for} '{item['name']}' 기록이 비어있어. 지금 입력할래?"


class Dispatcher:
    def __init__(self, items: TrackedItemManager, records: RecordManager,
                 telegram_send: Callable[[str], None]):
        self.items = items
        self.records = records
        self.send = telegram_send

    def run(self, now: datetime) -> list[DispatchMessage]:
        if now.tzinfo is None:
            now = now.replace(tzinfo=KST)
        else:
            now = now.astimezone(KST)

        all_items = self.items.list_all()
        if not all_items:
            return []

        # 윈도우: [now - WINDOW, now]
        window_start = now - timedelta(minutes=WINDOW_MINUTES)
        today_str = now.date().isoformat()

        scheduled: list[DispatchMessage] = []
        scheduled_names: set[str] = set()
        for it in all_items:
            h, m = _parse_hhmm(it["schedule_time"])
            slot_today = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if window_start < slot_today <= now:
                scheduled.append(DispatchMessage(
                    kind="scheduled", item_name=it["name"],
                    text=_question_text(it),
                ))
                scheduled_names.add(it["name"])

        missed: list[DispatchMessage] = []
        for it in all_items:
            if it["name"] in scheduled_names:
                continue
            h, m = _parse_hhmm(it["schedule_time"])
            slot_today = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if slot_today > now:
                continue  # 오늘 슬롯이 아직 안 옴
            if self.records.storage.record_exists(it["id"], today_str):
                continue
            missed.append(DispatchMessage(
                kind="missed", item_name=it["name"],
                text=_missed_text(it, today_str),
            ))

        messages = scheduled + missed
        for msg in messages:
            self.send(msg.text)
        return messages
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/msalt/tracking/test_dispatcher.py -q
```

Expected: PASS (7개).

- [ ] **Step 5: 커밋**

```bash
git add msalt/tracking/dispatcher.py tests/msalt/tracking/test_dispatcher.py
git commit -m "feat(msalt): Dispatcher detects scheduled and missed items"
```

---

### Task 9: CLI 엔트리포인트 + Telegram 클라이언트

**Files:**
- Create: `msalt/tracking/cli.py`
- Create: `msalt/tracking/__main__.py`
- Create: `tests/msalt/tracking/test_cli.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/msalt/tracking/test_cli.py`:

```python
from unittest.mock import patch
import pytest

from msalt.tracking.cli import build_parser, run_command
from msalt.storage import Storage
from msalt.tracking.items import TrackedItemManager


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "test.db"
    s = Storage(str(p))
    s.initialize()
    return str(p)


def test_add_command(db_path, capsys):
    rc = run_command(["add", "수면", "duration", "--time", "08:00"],
                     db_path=db_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "수면" in out
    s = Storage(db_path)
    items = TrackedItemManager(s)
    assert items.get("수면") is not None


def test_add_command_quantity_requires_unit(db_path, capsys):
    rc = run_command(["add", "음주", "quantity", "--time", "22:00"],
                     db_path=db_path)
    assert rc != 0
    err = capsys.readouterr().err
    assert "unit" in err.lower()


def test_list_command(db_path, capsys):
    s = Storage(db_path)
    TrackedItemManager(s).add("수면", "duration", None, "08:00")
    rc = run_command(["list"], db_path=db_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "수면" in out


def test_record_command(db_path, capsys):
    s = Storage(db_path)
    TrackedItemManager(s).add("수면", "duration", None, "08:00")
    rc = run_command(
        ["record", "수면", "--date", "2026-04-13", "--num", "480",
         "--raw", "8시간"],
        db_path=db_path,
    )
    assert rc == 0


def test_summary_command(db_path, capsys):
    s = Storage(db_path)
    TrackedItemManager(s).add("수면", "duration", None, "08:00")
    run_command(
        ["record", "수면", "--date", "2026-04-13", "--num", "480",
         "--raw", "8h"],
        db_path=db_path,
    )
    rc = run_command(["summary", "수면", "--days", "7",
                      "--ref", "2026-04-13"], db_path=db_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "수면" in out


def test_dispatch_command_invokes_dispatcher(db_path, capsys, monkeypatch):
    s = Storage(db_path)
    TrackedItemManager(s).add("수면", "duration", None, "08:00")

    sent: list[str] = []
    monkeypatch.setattr(
        "msalt.tracking.cli._make_telegram_sender",
        lambda: sent.append,
    )
    rc = run_command(["dispatch", "--now", "2026-04-14T08:05:00+09:00"],
                     db_path=db_path)
    assert rc == 0
    assert any("수면" in m for m in sent)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/msalt/tracking/test_cli.py -q
```

Expected: ImportError.

- [ ] **Step 3: CLI 구현**

`msalt/tracking/cli.py`:

```python
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
```

`msalt/tracking/__main__.py`:

```python
from msalt.tracking.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/msalt/tracking/test_cli.py -q
```

Expected: PASS (6개).

- [ ] **Step 5: 커밋**

```bash
git add msalt/tracking/cli.py msalt/tracking/__main__.py tests/msalt/tracking/test_cli.py
git commit -m "feat(msalt): tracking CLI with dispatch/add/list/delete/record/summary"
```

---

## Phase D: 통합 (Tasks 10-13)

### Task 10: 첫 실행 시 기본 시드

**Files:**
- Modify: `msalt/storage.py`
- Modify: `msalt/tracking/cli.py`
- Modify: `tests/msalt/tracking/test_cli.py`

`Storage.initialize()`는 테이블만 만들고 시드는 별도다. CLI 첫 실행 시 자동 시드를 추가한다.

- [ ] **Step 1: 실패 테스트 추가**

`tests/msalt/tracking/test_cli.py`에:

```python
def test_first_run_seeds_defaults(tmp_path, capsys):
    db = tmp_path / "fresh.db"
    rc = run_command(["list"], db_path=str(db))
    assert rc == 0
    out = capsys.readouterr().out
    assert "수면" in out
    assert "음주" in out
    assert "영어공부" in out


def test_seed_only_on_empty_db(tmp_path, capsys):
    db = tmp_path / "fresh.db"
    run_command(["list"], db_path=str(db))   # seeds
    run_command(["delete", "수면"], db_path=str(db))
    capsys.readouterr()
    rc = run_command(["list"], db_path=str(db))
    out = capsys.readouterr().out
    assert "수면" not in out
    assert "음주" in out  # 다른 시드는 그대로
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/msalt/tracking/test_cli.py::test_first_run_seeds_defaults -v
```

Expected: FAIL (시드 없음).

- [ ] **Step 3: cli.py 수정**

`run_command` 안에서 `items = TrackedItemManager(storage)` 직후 한 줄 추가:

```python
items.seed_defaults()
```

`seed_defaults()`는 빈 테이블에서만 동작하므로 idempotent.

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/msalt/tracking/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add msalt/tracking/cli.py tests/msalt/tracking/test_cli.py
git commit -m "feat(msalt): seed default tracked items on first CLI invocation"
```

---

### Task 11: 스킬 파일 + systemd timer

**Files:**
- Create: `msalt/skills/tracking/SKILL.md`
- Create: `deploy/msalt-tracking-dispatch.service`
- Create: `deploy/msalt-tracking-dispatch.timer`

- [ ] **Step 1: 스킬 작성**

`msalt/skills/tracking/SKILL.md`:

```markdown
---
name: tracking
description: 사용자가 정의한 항목(수면·음주·영어공부 등)에 대한 기록·조회·통계, 항목 추가/삭제를 처리합니다.
---

# 추적 항목 관리 스킬

## 사용 시점

다음 의도가 보이면 이 스킬을 사용:
- 무언가를 기록한다 (예: "어제 11시에 잤어", "오늘 영어 1시간 했어")
- 새 항목 추적을 원한다 (예: "독서도 매일 기록할래")
- 통계·조회 (예: "지난주 수면 평균은?", "이번 주 음주 얼마나 했어?")
- 항목 목록 (예: "뭐뭐 기록하고 있지?")
- 항목 삭제 (예: "영어공부 더 이상 기록 안 할래")

## 처리 절차

### 기록 입력
사용자 발화를 자연어 그대로 다음 명령에 전달. 시점·값 파싱은 내부 LLM 파서가 처리.

```bash
# 일반 흐름은 nanobot agent가 직접 NaturalLanguageParser를 호출하는 것이 이상적이지만,
# 현 구현에서는 agent가 시점·값을 추출한 뒤 CLI로 호출:
python -m msalt.tracking record <항목명> --date YYYY-MM-DD --num <분 or 양> --raw "<원문>"
python -m msalt.tracking record <항목명> --date YYYY-MM-DD --bool --raw "<원문>"
python -m msalt.tracking record <항목명> --date YYYY-MM-DD --text "<자유텍스트>" --raw "<원문>"
```

### 항목 추가
사용자에게 schema/시각 추론 결과를 확인받은 뒤:

```bash
python -m msalt.tracking add <이름> <schema> --time HH:MM [--unit <단위>]
```

확인 흐름 예: "독서 시간도 기록할래" → "이렇게 등록할게: 독서 / duration / 매일 22:00. 맞아?" → "응" → add 실행.

### 조회/통계

```bash
python -m msalt.tracking list
python -m msalt.tracking summary <항목명> --days 7
```

### 삭제

```bash
python -m msalt.tracking delete <항목명>
```

## 응답 가이드

- 자연어 시점 표현은 절대 날짜로 변환해 사용자에게 다시 확인.
- 항목 추가는 반드시 사용자 yes/no 확인 후 실행.
- 통계는 CLI 출력 그대로 전달하되, 한 줄 코멘트 추가 가능 (단, 평가/훈계 금지).
- 미확실하면 묻는다. 추측하지 않는다.
```

- [ ] **Step 2: systemd service 작성**

`deploy/msalt-tracking-dispatch.service`:

```ini
[Unit]
Description=msalt tracking dispatcher (one-shot)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/msalt-nanobot
EnvironmentFile=/home/pi/msalt-nanobot/.env
ExecStart=/home/pi/msalt-nanobot/.venv/bin/python -m msalt.tracking dispatch
StandardOutput=journal
StandardError=journal
```

- [ ] **Step 3: systemd timer 작성**

`deploy/msalt-tracking-dispatch.timer`:

```ini
[Unit]
Description=Run msalt tracking dispatcher every 30 minutes

[Timer]
OnCalendar=*:00,30
Persistent=true
Unit=msalt-tracking-dispatch.service

[Install]
WantedBy=timers.target
```

- [ ] **Step 4: 커밋**

```bash
git add msalt/skills/tracking/SKILL.md deploy/msalt-tracking-dispatch.service deploy/msalt-tracking-dispatch.timer
git commit -m "feat(msalt): tracking skill and systemd timer for dispatcher"
```

---

### Task 12: setup-rpi.sh에 timer 설치 단계 추가

**Files:**
- Modify: `deploy/setup-rpi.sh`

- [ ] **Step 1: 현재 setup-rpi.sh 확인**

```bash
grep -n "systemctl\|cp.*service" deploy/setup-rpi.sh
```

- [ ] **Step 2: tracking timer 설치 블록 추가**

기존 `cp deploy/msalt-nanobot.service` 라인 뒤에 다음 추가:

```bash
sudo cp deploy/msalt-tracking-dispatch.service /etc/systemd/system/
sudo cp deploy/msalt-tracking-dispatch.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now msalt-tracking-dispatch.timer
echo "tracking dispatcher timer enabled (every 30 min)"
```

(기존 스크립트의 정확한 들여쓰기와 변수명을 따를 것 — 파일을 먼저 읽어 컨텍스트 확인 후 적용.)

- [ ] **Step 3: 커밋**

```bash
git add deploy/setup-rpi.sh
git commit -m "deploy(msalt): install tracking dispatcher timer in setup-rpi.sh"
```

---

### Task 13: 전체 테스트 + 잔존 참조 청소

- [ ] **Step 1: 전체 테스트 실행**

```bash
pytest tests/msalt -q
```

Expected: 신규 tracking 테스트 + 기존 news/storage 테스트 모두 PASS.

- [ ] **Step 2: lifestyle 잔존 import 검증**

```bash
grep -rn "msalt\.lifestyle\|from msalt import lifestyle" msalt/ tests/ deploy/
```

Expected: 매치 없음.

- [ ] **Step 3: pytest 컬렉션 경고 확인**

```bash
pytest tests/msalt -q --collect-only 2>&1 | grep -i "warning\|error" || echo clean
```

Expected: `clean`.

- [ ] **Step 4: 커밋 (변경 없으면 skip)**

이 task는 검증 목적. 미해결 잔존 참조가 발견되면 즉시 수정 후:

```bash
git add -u
git commit -m "chore(msalt): clean up residual lifestyle references"
```

---

## Phase E: 문서 갱신 (Task 14)

### Task 14: PRD/TRD/SOUL/USER/README/setup/deploy 일괄 갱신

**Files:** (모두 수정)
- `docs/msalt-prd.md`
- `docs/msalt-trd.md`
- `msalt-nanobot.md`
- `msalt/workspace/SOUL.md`
- `msalt/workspace/USER.md`
- `docs/msalt-setup.md`
- `docs/msalt-rpi-deploy.md`
- `docs/superpowers/specs/2026-04-12-msalt-nanobot-design.md` (deprecated 노트)
- `docs/superpowers/plans/2026-04-12-msalt-nanobot.md` (deprecated 노트)

- [ ] **Step 1: PRD §4.2 재작성**

`docs/msalt-prd.md` §4.2 "생활 습관 관리" 전체를 다음으로 교체:

```markdown
### 4.2 추적 항목 기반 생활 기록

**무엇을.** 사용자가 정의한 추적 항목(수면·음주·영어공부 등)을 자연어로 기록·조회·통계 낸다. agent가 항목별 정해진 시각에 먼저 묻고, 누락된 기록도 알린다.

- **항목 정의**: 4가지 데이터 형식(`freetext`/`duration`/`quantity`/`boolean`) 중 하나로 schema를 지정해 등록. 사용자가 자연어로 추가 의도("음주도 기록할래")를 말하면 LLM이 schema·단위·시각을 추론해 사용자 확인 후 등록.
- **자연어 입력**: "어제 11시에 자서 7시에 일어났어", "지난주 화요일에 영어 1시간 했어" 같은 입력을 LLM(gpt-5-mini)이 시점·값으로 파싱.
- **능동 질문**: 30분마다 디스패처가 돌아 (1) 직전 30분 슬롯에 등록 시각이 든 항목, (2) 시각이 지났는데 오늘 기록이 없는 항목을 텔레그램으로 자동 질문.
- **통계**: schema에 따라 평균/합계/수행률(%) 계산. 자유 텍스트는 최근 기록 나열.

**왜.** 무엇을 추적할지는 시기에 따라 달라진다. 코드 수정 없이 새 습관을 추적하기 시작하고, 잊었을 때 봇이 먼저 챙겨준다.

**성공 기준.**
- 자연어 입력 1건당 LLM 호출 1회로 충분
- 능동 질문은 30분 정밀도 (실용상 충분)
- 30일 연속 누락 없는 기록 (봇 알림으로 보장)
```

- [ ] **Step 2: PRD §8 ADR에 항목 추가**

기존 ADR 표 끝에 4행 추가:

```markdown
| 11 | 할일(todo) 기능 제거 | 유지 | 도메인 미스매치 — msalt 정체성은 기록·통계·분석. 잔소리 도구 회피 |
| 12 | 추적 항목 동적 정의 (4 schema) | 고정 sleep/life 테이블 | 시기별 관심사 변화 수용. SQL만으로 통계 가능 |
| 13 | 30분 디스패처 (systemd timer) | 항목별 cron / nanobot in-process | nanobot core 격리, 동적 변경 단순, ±15분 실용 정밀도 |
| 14 | 모든 자연어 입력 LLM 파싱 | 룰 + LLM 폴백 | gpt-5-mini 비용 미미, 시점·값 추출 정확도 우위 |
```

- [ ] **Step 3: TRD 갱신**

`docs/msalt-trd.md`:

1. §3.3 "라이프스타일 도메인" 헤더를 "**3.3 트래킹 도메인 (L2: `msalt/tracking/`)**"으로 변경하고 본문 전체 교체:

```markdown
**`items.py` — TrackedItemManager**
추적 항목 CRUD와 검증, 빈 DB일 때 기본 시드(수면/음주/영어공부) 삽입을 책임진다. schema(freetext/duration/quantity/boolean)·schedule_time(HH:MM)·unit 일관성 검사도 여기서.

**`records.py` — RecordManager**
기록 upsert(같은 날짜 덮어쓰기)와 schema별 통계 포맷팅. duration → 평균 분, quantity → 합계·평균, boolean → 수행률(%), freetext → 최근 N건 나열.

**`parser.py` — NaturalLanguageParser**
gpt-5-mini 단발 호출로 두 가지를 처리: (1) 기록 입력 자연어 → ParsedRecord(item·날짜·값·신뢰도), (2) 항목 추가 자연어 → ParsedItemIntent(name·schema·unit·schedule_time). LLM 응답 파싱 실패 시 기록은 confidence=0 반환, 항목 의도는 ValueError.

**`dispatcher.py` — Dispatcher**
30분 윈도우 단위로 도는 검출 로직. (1) 직전 30분 슬롯에 schedule_time이 든 항목 → 질문 메시지, (2) 슬롯이 이미 지났는데 오늘 records가 없는 항목 → 누락 알림. 같은 항목이 양쪽에 잡히면 (1) 우선. Telegram 발송 함수는 의존성 주입.

**`cli.py` — main**
`python -m msalt.tracking <cmd>` 엔트리. `dispatch`(systemd timer), `add`/`delete`/`list`/`record`/`summary`(디버깅·시드).
```

2. §4 데이터 모델: `sleep_log`/`todos`/`life_log` 표 3개 제거, `tracked_items` / `records` 표로 교체 (spec §6 그대로 옮김).

3. §5 외부 의존성에 `httpx` 행 추가 항목 갱신:

```markdown
| **httpx** | YouTube API HTTP 호출 + tracking dispatcher의 Telegram 발송 | `youtube.py`, `tracking/cli.py` | — |
```

4. §6 배포 토폴로지 수정: cron 섹션 옆에 추가 행:

```
        ├── (외부) systemd timer: msalt-tracking-dispatch.timer (30min)
        │       └── python -m msalt.tracking dispatch → Telegram 직접 발송
```

- [ ] **Step 4: msalt-nanobot.md 갱신**

1. "주요 기능" §2 "생활 습관 관리"의 본문을 PRD §4.2와 같은 맥락으로 한 단락 요약:

```markdown
### 2. 추적 항목 기반 생활 기록
- 사용자 정의 항목 (수면·음주·영어공부 시드 + 자연어로 추가)
- 4가지 schema: freetext / duration / quantity / boolean
- 30분 단위 디스패처가 시각 도래·누락 항목을 능동 알림
- LLM 기반 자연어 입력 ("어제 11시에 잤어", "지난주 화요일에 영어 1시간")
- 통계: 평균·합계·수행률
```

2. 디렉토리 트리에서 `lifestyle/` 블록을 `tracking/` 블록으로 교체:

```
├── tracking/
│   ├── items.py             # TrackedItem CRUD + 시드
│   ├── records.py           # 기록 upsert + 통계
│   ├── parser.py            # LLM 자연어 파서
│   ├── dispatcher.py        # 30분 디스패처
│   └── cli.py               # CLI (dispatch/add/list/delete/record/summary)
```

스킬 트리에서 `lifestyle/SKILL.md` → `tracking/SKILL.md`.

- [ ] **Step 5: SOUL.md 갱신**

`msalt/workspace/SOUL.md` §주요 역할 §2 전체를 다음으로 교체:

```markdown
### 2. 추적 항목 기반 생활 기록
- **항목 관리**: 사용자가 자연어로 새 항목 제안 → schema·시각 추론 → 사용자 확인 → 등록
- **기록 입력**: 자연어를 LLM으로 파싱해 시점·값 추출 (과거 시점도 가능)
- **능동 질문**: 30분마다 디스패처가 시각 도래·누락 항목을 먼저 알림
- **통계**: 평균·합계·수행률을 단순한 사실로만 전달. 비판·훈계 금지
- `msalt.tracking` CLI 또는 `tracking` 스킬로 실행

기본 시드: 수면(매일 08:00, duration), 음주(매일 22:00, quantity 잔), 영어공부(매일 22:00, duration)
```

- [ ] **Step 6: USER.md 갱신**

루틴 섹션에 추가:

```markdown
- 매일 08:00: 봇이 어젯밤 수면을 자동으로 물음
- 매일 22:00: 봇이 오늘 음주·영어공부를 자동으로 물음
- 누락된 기록은 30분 단위로 봇이 다시 챙김
```

기존 "일요일 밤 주간 생활 리포트" 라인 삭제 (현 구현 범위 외).

- [ ] **Step 7: msalt-setup.md / msalt-rpi-deploy.md 갱신**

두 파일에서 `msalt.lifestyle` 언급 모두 `msalt.tracking`으로 교체. RPi 배포 가이드에는 timer 활성화 단계 명시:

```bash
sudo systemctl status msalt-tracking-dispatch.timer
journalctl -u msalt-tracking-dispatch.service -n 20
```

- [ ] **Step 8: deprecated 노트**

`docs/superpowers/specs/2026-04-12-msalt-nanobot-design.md` 최상단에:

```markdown
> **2026-04-14 업데이트**: 본 spec의 Phase 3 (생활 습관) 섹션은 폐기되고 [2026-04-14-msalt-tracking-redesign.md](2026-04-14-msalt-tracking-redesign.md) spec으로 대체되었다.
```

`docs/superpowers/plans/2026-04-12-msalt-nanobot.md` 최상단에 같은 노트.

- [ ] **Step 9: 커밋**

```bash
git add docs/ msalt-nanobot.md msalt/workspace/
git commit -m "docs(msalt): update PRD/TRD/SOUL/USER/README for tracking redesign"
```

---

## Self-Review

### Spec coverage

| Spec 섹션 | Plan 위치 |
|----------|----------|
| §2 목표: 할일 제거 | Tasks 1, 2 |
| §2 목표: 사용자 정의 항목 | Tasks 5, 7 (parser), 9 (CLI), 11 (skill) |
| §2 목표: 능동 질문 | Tasks 8, 11 (timer) |
| §2 목표: 과거 시점 입력 | Task 7 (parser) |
| §4.1 추적 항목 모델 | Task 4 (storage), 5 (manager) |
| §4.2 기록 모델 (recorded_for vs recorded_at) | Task 4 |
| §4.3 디스패처 우선순위 | Task 8 (test_scheduled_takes_priority_over_missed) |
| §6 데이터 모델 (FK CASCADE) | Task 4 (test_delete_tracked_item_cascades_records) |
| §7 컴포넌트 책임 | Tasks 5, 6, 7, 8, 9 |
| §8 사용자 흐름 | Task 11 (skill 안내) |
| §9 cron 등록 | **Plan에서 변경**: nanobot config 대신 systemd timer (이유 명시함) |
| §10 테스트 전략 | 모든 task에 TDD 단위 테스트 포함 |
| §11 마이그레이션 절차 | Phase A→B→C→D→E 순서로 그대로 매핑 |
| §12 ADR | Task 14 Step 2 |

### Placeholder scan

- TBD/TODO 없음.
- "그 외 적절한 처리" 같은 추상 표현 없음.
- 모든 코드 블록 완전 제공.
- Task 12 (setup-rpi.sh)는 기존 파일 컨텍스트를 모르므로 명시적으로 "파일 먼저 읽고 컨텍스트에 맞게" 지시. 이는 합당한 우회.

### Type consistency

- `Storage.upsert_record` 시그니처: Task 4에 정의 (`item_id, recorded_for, value_text=, value_num=, value_bool=, raw_input=`), Task 6/8/9에서 동일하게 호출 ✓
- `RecordManager.upsert(name, recorded_for, *, raw_input, value_text, value_num, value_bool)`: Task 6 정의, Task 8 dispatcher는 호출 안 하고 storage 직접 사용, Task 9 CLI 호출 시그니처 일치 ✓
- `Dispatcher.run(now)` 반환 `list[DispatchMessage]`: Task 8 정의, Task 9 CLI에서 동일 사용 ✓
- `TrackedItemManager.seed_defaults() -> int`: Task 5 정의, Task 10 호출 ✓
- `ItemAlreadyExists`/`ItemNotFound`: Task 5에 정의, Task 9 CLI에서 import ✓
- `parser.ParsedRecord`/`ParsedItemIntent`: Task 7에 정의. CLI에서는 직접 사용하지 않음 (agent가 추출 결과를 CLI 인자로 변환). 일관됨 ✓

이슈 없음.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-14-msalt-tracking-redesign.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
