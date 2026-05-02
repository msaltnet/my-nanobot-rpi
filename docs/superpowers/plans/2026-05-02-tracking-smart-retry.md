# Tracking smart retry chain — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dispatcher 알림을 "tick 1회 = 메시지 1개"로 묶고, 시간대 retry chain(09/14/20 KST)으로 미답 항목을 다시 묻도록 한다. boolean 항목의 부정 답은 N record로 자동 처리된다.

**Architecture:** dispatcher에 `pending_since` / `last_asked_at` 상태를 추가해 "이미 물어본 항목"을 추적한다. tick마다 (1) record 들어오면 pending 클리어, (2) schedule_slot 윈도우 안이면 첫 알림, (3) 아니면 글로벌 retry 슬롯 윈도우 + pending 항목에 retry. 모든 fire는 한 batch로 묶여 한 메시지로 발송. boolean 부정 답 처리는 `msalt/skills/tracking/SKILL.md`의 LLM 프롬프트에서 처리 (parser.py는 dead code라 손대지 않음).

**Tech Stack:** Python 3.11+, sqlite3 (ALTER TABLE 마이그레이션), pytest, zoneinfo

---

## File Structure

| 파일 | 역할 | 변경 |
|---|---|---|
| `msalt/storage.py` | sqlite schema + tracked_items getter/setter | ADD COLUMN, getter/setter, 옛 `set_last_missed_asked_date` 제거 |
| `msalt/tracking/dispatcher.py` | 알고리즘 + 메시지 포맷 | 전면 재작성 (batch 발송, retry chain) |
| `msalt/skills/tracking/SKILL.md` | LLM agent 프롬프트 | batch 응답 + boolean 부정 답 처리 가이드 추가 |
| `tests/msalt/tracking/test_dispatcher.py` | dispatcher 테스트 | 옛 `last_missed_asked_date` 시나리오 제거, 새 retry/batch 시나리오 추가 |

---

## 사전 점검

- [ ] **Step 0: 새 worktree에서 시작 (이미 brainstorming 단계에서 만들었다면 생략)**

브랜치: `feat/tracking-smart-retry`. main에서 시작.

```bash
git checkout main
git pull --ff-only
git checkout -b feat/tracking-smart-retry
```

---

## Task 1: storage.py 마이그레이션 — 새 컬럼 추가

**Files:**
- Modify: `msalt/storage.py:27-62` (CREATE TABLE + ALTER TABLE migration)
- Test: `tests/msalt/test_storage_migration.py` (Create)

목표: 기존 DB가 있어도 깨지지 않게 `pending_since`, `last_asked_at` 컬럼을 추가한다. 옛 `last_missed_asked_date`는 DROP 시도하되 sqlite 버전이 낮아 실패하면 무시 (read/write만 끊으면 됨).

- [ ] **Step 1.1: 실패 테스트 작성**

`tests/msalt/test_storage_migration.py` (신규):

```python
import sqlite3

from msalt.storage import Storage


def test_initialize_adds_pending_since_column(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tracked_items)")}
    conn.close()
    assert "pending_since" in cols
    assert "last_asked_at" in cols


def test_initialize_is_idempotent_on_existing_db(tmp_path):
    """이미 last_missed_asked_date가 있는 옛 DB에서도 깨지지 않고 새 컬럼만 추가된다."""
    db = tmp_path / "test.db"
    # 옛 schema로 미리 만든다
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE tracked_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            schema TEXT NOT NULL,
            unit TEXT,
            schedule_time TEXT NOT NULL,
            frequency TEXT NOT NULL DEFAULT 'daily',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_missed_asked_date TEXT
        );
    """)
    conn.commit()
    conn.close()

    s = Storage(str(db))
    s.initialize()  # 두 번 호출해도 OK
    s.initialize()

    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tracked_items)")}
    conn.close()
    assert "pending_since" in cols
    assert "last_asked_at" in cols
```

- [ ] **Step 1.2: 테스트 실패 확인**

```bash
python -m pytest tests/msalt/test_storage_migration.py -v
```

Expected: `pending_since not in cols` 같은 AssertionError 2건 FAIL.

- [ ] **Step 1.3: storage.py에 마이그레이션 추가**

`msalt/storage.py:53-62`의 ALTER 블록을 다음으로 교체:

```python
        cols = {row[1] for row in conn.execute("PRAGMA table_info(tracked_items)")}
        if "last_missed_asked_date" not in cols:
            # 옛 컬럼이 없는 새 DB도 있을 수 있으므로 보존 (DROP은 시도만)
            conn.execute(
                "ALTER TABLE tracked_items ADD COLUMN last_missed_asked_date TEXT"
            )
            cols.add("last_missed_asked_date")
        if "pending_since" not in cols:
            conn.execute(
                "ALTER TABLE tracked_items ADD COLUMN pending_since TEXT"
            )
        if "last_asked_at" not in cols:
            conn.execute(
                "ALTER TABLE tracked_items ADD COLUMN last_asked_at TEXT"
            )
        article_cols = {row[1] for row in conn.execute("PRAGMA table_info(news_articles)")}
        if "published_at" not in article_cols:
            conn.execute("ALTER TABLE news_articles ADD COLUMN published_at TEXT")
        conn.commit()
        conn.close()
```

`last_missed_asked_date`는 일부러 그대로 두고 read/write 코드만 끊는다 (sqlite 버전 호환).

- [ ] **Step 1.4: 테스트 통과 확인**

```bash
python -m pytest tests/msalt/test_storage_migration.py -v
```

Expected: 2 PASSED.

- [ ] **Step 1.5: 커밋**

```bash
git add msalt/storage.py tests/msalt/test_storage_migration.py
git commit -m "feat(msalt): add pending_since and last_asked_at columns to tracked_items"
```

---

## Task 2: storage.py — getter/setter 메서드

**Files:**
- Modify: `msalt/storage.py` (set_last_missed_asked_date 제거, 새 메서드 3개 추가)

목표: dispatcher가 사용할 read/write 인터페이스 추가.

- [ ] **Step 2.1: 실패 테스트 작성**

`tests/msalt/test_storage_migration.py`에 추가:

```python
def test_set_pending_since_persists(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    item_id = s.insert_tracked_item("수면", "duration", None, "22:00")
    s.set_pending_since(item_id, "2026-05-01 13:00:00")
    item = s.get_tracked_item_by_name("수면")
    assert item["pending_since"] == "2026-05-01 13:00:00"


def test_clear_pending_sets_null(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    item_id = s.insert_tracked_item("수면", "duration", None, "22:00")
    s.set_pending_since(item_id, "2026-05-01 13:00:00")
    s.clear_pending(item_id)
    item = s.get_tracked_item_by_name("수면")
    assert item["pending_since"] is None


def test_set_last_asked_at_persists(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    item_id = s.insert_tracked_item("수면", "duration", None, "22:00")
    s.set_last_asked_at(item_id, "2026-05-02 00:00:00")
    item = s.get_tracked_item_by_name("수면")
    assert item["last_asked_at"] == "2026-05-02 00:00:00"
```

- [ ] **Step 2.2: 테스트 실패 확인**

```bash
python -m pytest tests/msalt/test_storage_migration.py -v
```

Expected: AttributeError on `set_pending_since` 등.

- [ ] **Step 2.3: storage.py에 메서드 추가, 옛 setter 제거**

`msalt/storage.py:156-165`의 `set_last_missed_asked_date` 메서드를 다음으로 **교체** (3개 새 메서드):

```python
    def set_pending_since(self, item_id: int, when_utc: str) -> None:
        """첫 알림 발송 시각(UTC ISO)을 기록."""
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE tracked_items SET pending_since = ? WHERE id = ?",
                (when_utc, item_id),
            )
            conn.commit()
        finally:
            conn.close()

    def clear_pending(self, item_id: int) -> None:
        """답이 들어오거나 다음 schedule_slot 도래 시 호출."""
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE tracked_items SET pending_since = NULL WHERE id = ?",
                (item_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def set_last_asked_at(self, item_id: int, when_utc: str) -> None:
        """가장 최근 알림 시각(UTC ISO). retry 슬롯 중복 fire 방지용."""
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE tracked_items SET last_asked_at = ? WHERE id = ?",
                (when_utc, item_id),
            )
            conn.commit()
        finally:
            conn.close()
```

- [ ] **Step 2.4: 옛 setter 호출처 정리**

`msalt/tracking/dispatcher.py`의 `self.records.storage.set_last_missed_asked_date(...)` 호출은 Task 3에서 전면 재작성으로 사라지므로 지금은 그대로 두고 Task 3에서 삭제한다.

- [ ] **Step 2.5: 테스트 통과 확인**

```bash
python -m pytest tests/msalt/test_storage_migration.py -v
```

Expected: 5 PASSED (Task 1의 2 + 새 3).

- [ ] **Step 2.6: 커밋**

```bash
git add msalt/storage.py tests/msalt/test_storage_migration.py
git commit -m "feat(msalt): add pending_since/last_asked_at storage accessors"
```

---

## Task 3: dispatcher.py 전면 재작성 — algorithm + batch message

**Files:**
- Modify: `msalt/tracking/dispatcher.py` (전체)
- Modify: `tests/msalt/tracking/test_dispatcher.py` (전체)

목표: spec에 명시된 알고리즘을 구현한다. 기존 `kind: scheduled|missed`는 유지하되, 한 tick에서 여러 항목이 fire되면 한 메시지로 묶어 보낸다.

### Step 3.1: 새 dispatcher 테스트 작성

기존 `tests/msalt/tracking/test_dispatcher.py`를 다음으로 **완전 교체**:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import pytest

from msalt.storage import Storage
from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager
from msalt.tracking.dispatcher import Dispatcher


KST = ZoneInfo("Asia/Seoul")


@pytest.fixture
def setup(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    s.initialize()
    items = TrackedItemManager(s)
    records = RecordManager(s, items)
    return s, items, records


def _kst(y, m, d, h, mi):
    return datetime(y, m, d, h, mi, tzinfo=KST)


# --- 기본 동작 ---


def test_no_items_no_messages(setup):
    _, items, records = setup
    d = Dispatcher(items, records, telegram_send=MagicMock())
    msgs = d.run(now=_kst(2026, 5, 2, 9, 0))
    assert msgs == []


def test_first_alert_when_schedule_slot_in_window(setup):
    """schedule_time이 [now-30, now] 윈도우에 들어오면 첫 알림 발송 + pending_since 세팅."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    msgs = d.run(now=_kst(2026, 5, 1, 22, 5))
    assert len(msgs) == 1
    assert msgs[0].item_name == "수면"
    assert send.call_count == 1
    item = s.get_tracked_item_by_name("수면")
    assert item["pending_since"] is not None
    assert item["last_asked_at"] is not None


def test_no_double_fire_at_plus_30(setup):
    """첫 알림 30분 뒤에는 schedule_slot이 윈도우 밖 → 추가 알림 없음 (현행 +30 noise 제거)."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # 첫 알림
    msgs2 = d.run(now=_kst(2026, 5, 1, 22, 35))   # +30
    assert msgs2 == []
    assert send.call_count == 1


def test_record_arrived_clears_pending(setup):
    """첫 알림 후 사용자가 record를 입력하면 다음 tick에서 pending이 클리어된다."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))
    records.upsert("수면", "2026-05-01", value_num=480, raw_input="8h")
    # 다음날 09:00 retry 슬롯 → record가 있으니 fire 안 함
    msgs = d.run(now=_kst(2026, 5, 2, 9, 5))
    assert msgs == []
    item = s.get_tracked_item_by_name("수면")
    assert item["pending_since"] is None


# --- retry chain ---


def test_retry_at_09_when_pending(setup):
    """첫 알림 후 답이 없으면 다음날 09:00 retry 슬롯에서 재질문."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # 첫 알림
    msgs = d.run(now=_kst(2026, 5, 2, 9, 5))
    assert len(msgs) == 1
    assert msgs[0].item_name == "수면"
    assert send.call_count == 2


def test_retry_chain_09_14_20(setup):
    """답이 없으면 09 → 14 → 20 모두 retry."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # 첫 알림
    d.run(now=_kst(2026, 5, 2, 9, 5))
    d.run(now=_kst(2026, 5, 2, 14, 5))
    d.run(now=_kst(2026, 5, 2, 20, 5))
    assert send.call_count == 4


def test_retry_does_not_fire_without_pending(setup):
    """pending_since가 없으면 retry 슬롯에서도 fire 안 함."""
    _, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    msgs = d.run(now=_kst(2026, 5, 1, 9, 5))   # 22:00 슬롯 도래 전
    assert msgs == []
    assert send.call_count == 0


def test_retry_slot_no_double_fire_in_same_window(setup):
    """같은 retry 슬롯 윈도우에서 두 번 tick해도 한 번만 fire."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # 첫 알림
    d.run(now=_kst(2026, 5, 2, 9, 5))    # retry 1
    msgs = d.run(now=_kst(2026, 5, 2, 9, 25))   # 같은 09:00 슬롯, 다른 tick
    assert msgs == []
    assert send.call_count == 2


def test_next_schedule_slot_clears_stale_pending(setup):
    """다음날 22:00 schedule_slot 도달 시 어제 pending은 폐기되고 새 알림이 fire된다."""
    s, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # day1 첫 알림
    msgs = d.run(now=_kst(2026, 5, 2, 22, 5))   # day2 첫 알림 (day1 pending은 폐기)
    assert len(msgs) == 1
    item = s.get_tracked_item_by_name("수면")
    # pending_since는 day2 알림 시각
    assert item["pending_since"] is not None
    # day2 첫 알림이 day1 알림(13:00 UTC) 이후
    assert item["pending_since"] > "2026-05-01 13:00:00"


# --- batch ---


def test_multiple_items_batched_into_one_message(setup):
    """같은 tick에 두 항목이 fire되면 한 메시지로 묶임."""
    _, items, records = setup
    items.add("수면", "duration", None, "22:00")
    items.add("음주", "quantity", "잔", "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    msgs = d.run(now=_kst(2026, 5, 1, 22, 5))
    assert len(msgs) == 2   # DispatchMessage 자체는 항목별로 2개
    assert send.call_count == 1   # 그러나 텔레그램 send는 1번
    sent_text = send.call_args.args[0]
    assert "수면" in sent_text
    assert "음주" in sent_text


def test_single_item_uses_solo_format(setup):
    """단일 항목은 기존 솔로 포맷 (번호 리스트 아님)."""
    _, items, records = setup
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))
    sent_text = send.call_args.args[0]
    assert "기록할 항목" not in sent_text   # batch 헤더 아님
    assert "수면" in sent_text


def test_batch_includes_first_alert_and_retry_in_same_tick(setup):
    """09:00에 첫 알림인 항목 + 09:00 retry 슬롯에 걸린 미답 항목이 한 메시지로 묶임."""
    s, items, records = setup
    items.add("아침메모", "freetext", None, "09:00")
    items.add("수면", "duration", None, "22:00")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    d.run(now=_kst(2026, 5, 1, 22, 5))   # 수면 첫 알림 → pending 세팅
    msgs = d.run(now=_kst(2026, 5, 2, 9, 5))
    # 아침메모는 첫 알림, 수면은 retry. 한 메시지에 둘 다 들어가야 함
    assert send.call_count == 2   # day1 첫 알림 + day2 batch
    sent_text = send.call_args.args[0]
    assert "아침메모" in sent_text
    assert "수면" in sent_text


# --- 24h 내 record 있으면 첫 알림 skip ---


def test_first_alert_skipped_if_recent_record(setup):
    """schedule_slot 도래해도 24시간 내 record가 있으면 첫 알림 skip."""
    _, items, records = setup
    items.add("수면", "duration", None, "22:00")
    records.upsert("수면", "2026-05-01", value_num=480, raw_input="이미 입력")
    send = MagicMock()
    d = Dispatcher(items, records, telegram_send=send)
    msgs = d.run(now=_kst(2026, 5, 1, 22, 5))
    assert msgs == []
    assert send.call_count == 0
```

### Step 3.2: 테스트 실패 확인

```bash
python -m pytest tests/msalt/tracking/test_dispatcher.py -v
```

Expected: 다수 FAIL (현 dispatcher가 새 모델 미구현).

### Step 3.3: dispatcher.py 재작성

`msalt/tracking/dispatcher.py` **전체**를 다음으로 교체:

```python
"""디스패처: 시각 도래 / 누락 항목 검출 후 batch로 텔레그램 발송."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal
from zoneinfo import ZoneInfo

from msalt.tracking.items import TrackedItemManager
from msalt.tracking.records import RecordManager


KST = ZoneInfo("Asia/Seoul")
WINDOW_MINUTES = 30
RECENT_HOURS = 24
GLOBAL_RETRY_SLOTS = ["09:00", "14:00", "20:00"]   # KST


@dataclass
class DispatchMessage:
    kind: Literal["scheduled", "retry"]
    item_name: str
    text: str   # 항목 단독 톤 텍스트 (batch 합치기 전 단계)


def _parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _question_hint(item: dict) -> str:
    """schema별 짧은 힌트 — batch 라인에 들어감."""
    schema = item["schema"]
    unit = item.get("unit") or ""
    if schema == "duration":
        return "몇 시간/얼마나?"
    if schema == "quantity":
        return f"몇 {unit}?" if unit else "얼마나?"
    if schema == "boolean":
        return "했어?"
    return "한 줄 메모"


def _solo_text(item: dict) -> str:
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


def _format_batch(items: list[dict]) -> str:
    """단일 항목이면 솔로 톤, 복수면 번호 리스트."""
    if len(items) == 1:
        return _solo_text(items[0])
    lines = [f"📝 기록할 항목 {len(items)}개:"]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {it['name']} — {_question_hint(it)}")
    return "\n".join(lines)


def _next_schedule_slot_after(item: dict, after_utc: str) -> datetime:
    """item.schedule_time(KST)이 after_utc 시각보다 미래의 가장 가까운 KST datetime을 반환."""
    h, m = _parse_hhmm(item["schedule_time"])
    after_dt_utc = datetime.strptime(after_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    after_dt_kst = after_dt_utc.astimezone(KST)
    # 같은 날 슬롯
    candidate = after_dt_kst.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= after_dt_kst:
        candidate = candidate + timedelta(days=1)
    return candidate


def _retry_slot_in_window(now_kst: datetime, window_start_kst: datetime) -> datetime | None:
    """now_kst의 (window_start, now_kst] 윈도우 안에 들어오는 GLOBAL_RETRY_SLOTS 슬롯 KST datetime."""
    for hhmm in GLOBAL_RETRY_SLOTS:
        h, m = _parse_hhmm(hhmm)
        slot = now_kst.replace(hour=h, minute=m, second=0, microsecond=0)
        if window_start_kst < slot <= now_kst:
            return slot
    return None


class Dispatcher:
    def __init__(self, items: TrackedItemManager, records: RecordManager,
                 telegram_send: Callable[[str], None]):
        self.items = items
        self.records = records
        self.send = telegram_send

    def run(self, now: datetime) -> list[DispatchMessage]:
        if now.tzinfo is None:
            now = now.replace(tzinfo=KST)
        now_kst = now.astimezone(KST)
        now_utc = now.astimezone(timezone.utc)
        now_utc_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")

        all_items = self.items.list_all()
        if not all_items:
            return []

        window_start_kst = now_kst - timedelta(minutes=WINDOW_MINUTES)
        recent_since_utc = (
            now_utc - timedelta(hours=RECENT_HOURS)
        ).strftime("%Y-%m-%d %H:%M:%S")

        storage = self.records.storage
        batch_items: list[dict] = []
        batch_messages: list[DispatchMessage] = []
        retry_slot_kst = _retry_slot_in_window(now_kst, window_start_kst)
        retry_slot_utc_str = (
            retry_slot_kst.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if retry_slot_kst else None
        )

        for it in all_items:
            # 1. record가 pending_since 이후로 들어왔으면 pending 클리어
            if it.get("pending_since"):
                if storage.has_record_since(it["id"], it["pending_since"]):
                    storage.clear_pending(it["id"])
                    it["pending_since"] = None

            # 2. 다음 schedule_slot 도래 시 stale pending 폐기
            if it.get("pending_since"):
                next_slot_kst = _next_schedule_slot_after(it, it["pending_since"])
                if now_kst >= next_slot_kst:
                    storage.clear_pending(it["id"])
                    it["pending_since"] = None

            # 3. 첫 알림 — schedule_time이 오늘의 [window_start, now] 윈도우 안
            h, m = _parse_hhmm(it["schedule_time"])
            slot_today_kst = now_kst.replace(hour=h, minute=m, second=0, microsecond=0)
            if window_start_kst < slot_today_kst <= now_kst:
                if not storage.has_record_since(it["id"], recent_since_utc):
                    batch_items.append(it)
                    batch_messages.append(DispatchMessage(
                        kind="scheduled", item_name=it["name"],
                        text=_solo_text(it),
                    ))
                continue

            # 4. retry — pending이고 글로벌 retry 슬롯이 윈도우 안
            if it.get("pending_since") and retry_slot_kst is not None:
                last_asked = it.get("last_asked_at")
                if last_asked is None or last_asked < retry_slot_utc_str:
                    batch_items.append(it)
                    batch_messages.append(DispatchMessage(
                        kind="retry", item_name=it["name"],
                        text=_solo_text(it),
                    ))

        # 5. 한 메시지로 묶어 발송
        if batch_items:
            self.send(_format_batch(batch_items))
            for it in batch_items:
                if not it.get("pending_since"):
                    storage.set_pending_since(it["id"], now_utc_str)
                storage.set_last_asked_at(it["id"], now_utc_str)

        return batch_messages
```

### Step 3.4: 테스트 통과 확인

```bash
python -m pytest tests/msalt/tracking/test_dispatcher.py -v
```

Expected: 13 PASSED.

### Step 3.5: 전체 회귀 테스트

```bash
python -m pytest tests/msalt -v
```

Expected: 모든 테스트 통과 (parser 테스트는 별도 기능이므로 그대로 PASS).

### Step 3.6: 커밋

```bash
git add msalt/tracking/dispatcher.py tests/msalt/tracking/test_dispatcher.py
git commit -m "feat(msalt): batch dispatcher messages and add retry chain"
```

---

## Task 4: SKILL.md — batch 응답 + boolean 부정 답 가이드

**Files:**
- Modify: `msalt/skills/tracking/SKILL.md`

목표: dispatcher가 보낸 batch 메시지에 대해 사용자가 한 번에 답했을 때 LLM agent가 항목별로 분리해 record CLI를 호출하게 한다. boolean의 부정 답("아니/안 했어")을 `--no-bool`로 인식.

**중요**: SKILL.md는 `~/.nanobot/workspace/skills/tracking/SKILL.md`로 seed되지만, **이미 seed된 디렉토리는 새로 복사하지 않는다** ([msalt/cli.py:88-99](msalt/cli.py#L88-L99)). 그래서 운영 중인 라즈베리파이에서는 수동으로 워크스페이스 SKILL.md도 갱신해야 반영된다 (Task 6 배포에서 처리).

- [ ] **Step 4.1: SKILL.md 수정**

`msalt/skills/tracking/SKILL.md`의 "## 처리 절차" 섹션 끝(현재 line 61)과 "## 응답 가이드"(line 63) 사이에 새 섹션을 추가:

```markdown
### 묶음 알림에 답하기

dispatcher가 여러 항목을 한 메시지로 묶어 보낼 수 있다. 예:

```
📝 기록할 항목 3개:
1. 수면 — 몇 시간/얼마나?
2. 음주 — 몇 잔?
3. 영어공부 — 했어?
```

사용자가 `"7시간 잤고 2잔 마셨어, 영어 했어"` 같이 한 번에 답하면 **각 항목별로 record CLI를 한 번씩 호출**한다. 부분 답("수면만 7시간")이면 매칭된 항목만 기록하고 나머지는 건드리지 않는다 (다음 retry 슬롯에서 다시 묻게 됨).

### boolean 부정 답

boolean schema 항목에서 사용자가 "아니" / "안 했어" / "no" / "패스" 등 부정 의미를 표현하면 `--no-bool`로 기록한다. 예: "영어공부 안 했어" → `msalt-nanobot tracking record 영어공부 --date YYYY-MM-DD --no-bool --raw "영어공부 안 했어"`.
```

- [ ] **Step 4.2: 변경 검증 (lint/syntax 무관, 사람 읽기용 문서)**

수동 검토만:

```bash
python -c "from pathlib import Path; print(Path('msalt/skills/tracking/SKILL.md').read_text(encoding='utf-8')[:500])"
```

새 섹션이 들어갔는지 확인.

- [ ] **Step 4.3: 커밋**

```bash
git add msalt/skills/tracking/SKILL.md
git commit -m "docs(msalt): tracking skill — batch reply and boolean negative"
```

---

## Task 5: 회귀 테스트 + main 머지

**Files:** 없음

- [ ] **Step 5.1: 전체 테스트 스위트 실행**

```bash
python -m pytest -q
```

Expected: 모든 테스트 통과.

- [ ] **Step 5.2: main으로 머지**

```bash
git checkout main
git merge --no-ff feat/tracking-smart-retry
git push origin main
```

(squash 선호 시 `git merge --squash` 후 단일 커밋으로 정리. 이 프로젝트는 PR 없이 직접 main 머지하는 패턴이므로 fast-forward 또는 no-ff 둘 다 OK.)

---

## Task 6: 라즈베리파이 배포

**Files:** 없음

목표: 운영 라즈베리파이의 시드된 SKILL.md 갱신, 코드 갱신, 서비스 재시작.

- [ ] **Step 6.1: pull**

```bash
ssh msalt-rpi "cd /home/ubuntu/nanobot && git pull --ff-only"
```

(만약 conflict가 나면 손대지 말고 사용자에게 보고. 이전 작업 같이 응급 hotfix 흔적이 있을 수 있음.)

- [ ] **Step 6.2: 시드된 SKILL.md 갱신**

이미 seed된 워크스페이스의 SKILL.md는 갱신되지 않으므로 수동 복사:

```bash
ssh msalt-rpi "cp /home/ubuntu/nanobot/msalt/skills/tracking/SKILL.md ~/.nanobot/workspace/skills/tracking/SKILL.md && diff /home/ubuntu/nanobot/msalt/skills/tracking/SKILL.md ~/.nanobot/workspace/skills/tracking/SKILL.md && echo 'SKILL.md synced'"
```

Expected: `diff`가 빈 출력이면 OK, `SKILL.md synced` 출력.

- [ ] **Step 6.3: DB 마이그레이션은 자동**

`msalt-nanobot` 재시작 시 `Storage.initialize()`가 ALTER TABLE을 자동 실행하므로 별도 작업 없음.

- [ ] **Step 6.4: 서비스 재시작**

```bash
ssh msalt-rpi "sudo systemctl restart msalt-nanobot && sleep 3 && sudo systemctl is-active msalt-nanobot"
```

Expected: `active`.

- [ ] **Step 6.5: 마이그레이션 검증**

```bash
ssh msalt-rpi "sqlite3 ~/.nanobot/workspace/msalt.db 'PRAGMA table_info(tracked_items);'"
```

Expected: `pending_since`와 `last_asked_at` 컬럼이 출력에 보임.

- [ ] **Step 6.6: dispatch 수동 실행 (선택적)**

새 알림이 의도대로 묶이는지 확인. 미답 항목이 있을 때:

```bash
ssh msalt-rpi "cd /home/ubuntu/nanobot && /home/ubuntu/nanobot/.venv/bin/msalt-nanobot tracking dispatch"
```

Expected: 알림이 발송되거나 (미답 항목이 있고 슬롯이 윈도우 안) `dispatched 0 message(s)` (없을 때).

---

## Self-Review (실행 전 체크리스트)

- **Spec coverage**:
  - 모델 변경 (pending_since, last_asked_at 추가, last_missed_asked_date 제거) → Task 1 ✓
  - storage getter/setter → Task 2 ✓
  - dispatcher 알고리즘 (batch + retry chain + 자연 cap + 중복 fire 방지) → Task 3 ✓
  - 메시지 포맷 (단일/복수) → Task 3의 `_format_batch` ✓
  - LLM 파서 영향 (batch 답 + boolean 부정) → Task 4 (SKILL.md로 위치 이동, parser.py는 dead code) ⚠ spec과 다른 위치이지만 **spec보다 정확한 결정** (parser.py는 코드에서 호출되지 않음)
  - 마이그레이션 (sqlite < 3.35 호환) → Task 1 (DROP 시도 안 함, 옛 컬럼 그대로 둠) ✓
  - 테스트 9개 시나리오 → Task 3에 13개로 확장 ✓
- **Placeholder 스캔**: 모든 step에 실제 코드/명령어 있음 ✓
- **타입 일관성**: `set_pending_since`, `clear_pending`, `set_last_asked_at`, `has_record_since` 모두 일관 ✓
- **DispatchMessage.kind**: 옛 `"missed"` → 새 `"retry"`로 변경 ✓ (테스트도 일치)

## 비고

- spec은 `msalt/tracking/parser.py`도 변경 대상으로 적었지만, 실제로 그 모듈은 어디서도 호출되지 않는다 (LLM agent가 SKILL.md를 통해 직접 LLM에 prompt). 파서 코드를 손대지 않고 SKILL.md에 가이드를 추가하는 것이 정확한 변경 위치다. 이 결정은 self-review에서 발견된 사실에 근거하며, 이미 spec을 한 번 합의했으므로 spec 자체를 수정하지는 않는다.
- 같은 이유로 `tests/msalt/tracking/test_parser.py`에 boolean 부정 답 테스트를 추가하지 않는다.
