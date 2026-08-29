# Tracking Missing Follow-up Keyboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 생활 기록 저장 응답 뒤에 최근 7일의 가장 최근 미기록 항목 하나를 질문하고 Telegram reply keyboard를 질문에 맞게 교체한다.

**Architecture:** `RecordManager`가 기준일 이전 7일의 미기록 후보를 결정하고, dispatcher의 기존 단일 항목 문구·버튼 생성기를 재사용해 tracking CLI가 구조화된 후속 지시를 출력한다. 에이전트는 확장된 `MessageTool.reply_keyboard`로 최종 텍스트와 버튼을 함께 보내고, Telegram 채널은 metadata를 `ReplyKeyboardMarkup` 또는 `ReplyKeyboardRemove`로 렌더링한다.

**Tech Stack:** Python 3.11+, SQLite, pytest/pytest-asyncio, python-telegram-bot, nanobot tool schemas

**Spec:** `docs/superpowers/specs/2026-08-30-tracking-missing-followup-keyboard-design.md`

## Global Constraints

- 검색 범위는 방금 저장한 `recorded_for` 날짜를 제외한 직전 7일이다.
- 한 번에 가장 최근 미기록 한 건만 질문한다. 같은 날짜에서는 `TrackedItemManager.list_all()` 순서를 유지한다.
- `false`와 `0` 값도 DB 행이 있으면 기록된 것으로 본다.
- 기존 dispatcher의 정기 알림/retry 정책과 DB 스키마는 변경하지 않는다.
- 미기록이 없으면 이전 Telegram reply keyboard를 제거한다.
- tracking CLI의 구조화 출력과 전체 명령은 사용자에게 노출하지 않는다.
- 기존 일반 `MessageTool` 호출과 Telegram 메시지는 키보드 인자를 생략할 때 동작이 변하지 않아야 한다.

---

## File Structure

- `msalt/tracking/records.py`: 최근 미기록 후보 선택만 담당한다.
- `msalt/tracking/dispatcher.py`: 기존 schema별 질문과 버튼 포맷을 공개 함수로 제공한다.
- `msalt/tracking/cli.py`: 저장 출력 뒤 후속 질문 payload를 출력한다.
- `msalt/skills/tracking/SKILL.md`: CLI payload를 최종 메시지와 키보드로 전달하는 에이전트 계약을 설명한다.
- `tests/msalt/tracking/test_records.py`: 미기록 선택 규칙을 검증한다.
- `tests/msalt/tracking/test_dispatcher.py`: 공개 후속 질문 포맷을 검증한다.
- `tests/msalt/tracking/test_cli.py`: record 명령의 구조화 payload를 검증한다.
- `nanobot/nanobot/agent/tools/message.py`: 선택적 2차원 `reply_keyboard`를 outbound metadata에 전달한다.
- `nanobot/tests/tools/test_message_tool.py`: 메시지 도구 schema와 metadata 전달을 검증한다.
- `nanobot/nanobot/channels/telegram.py`: keyboard metadata를 Telegram reply markup으로 렌더링한다.
- `nanobot/tests/channels/test_telegram_channel.py`: 키보드 생성, 제거, 청크, fallback을 검증한다.

### Task 1: 최근 미기록 후보 선택

**Files:**
- Modify: `msalt/tracking/records.py`
- Test: `tests/msalt/tracking/test_records.py`

**Interfaces:**
- Consumes: `TrackedItemManager.list_all() -> list[dict]`, `Storage.record_exists(item_id: int, recorded_for: str) -> bool`
- Produces: `RecordManager.find_recent_missing(ref_date: str, days: int = 7) -> tuple[dict, str] | None`

- [ ] **Step 1: 가장 최근 날짜와 기존 항목 순서를 고정하는 실패 테스트 작성**

```python
def test_find_recent_missing_prefers_latest_date_and_item_order(setup):
    _, items, records = setup
    items.add("수면", "duration", None, "08:00")
    items.add("영어공부", "boolean", None, "22:00")
    records.upsert("수면", "2026-08-29", value_num=420, raw_input="7시간")

    item, recorded_for = records.find_recent_missing("2026-08-30")

    assert recorded_for == "2026-08-29"
    assert item["name"] == "영어공부"
```

- [ ] **Step 2: 테스트가 메서드 부재로 실패하는지 실행**

Run: `pytest tests/msalt/tracking/test_records.py::test_find_recent_missing_prefers_latest_date_and_item_order -v`

Expected: FAIL with `AttributeError: 'RecordManager' object has no attribute 'find_recent_missing'`.

- [ ] **Step 3: 최소 후보 선택 구현**

```python
from datetime import date, timedelta

def find_recent_missing(
    self, ref_date: str, days: int = 7
) -> tuple[dict, str] | None:
    ref = date.fromisoformat(ref_date)
    for offset in range(1, days + 1):
        recorded_for = (ref - timedelta(days=offset)).isoformat()
        for item in self.items.list_all():
            if not self.storage.record_exists(item["id"], recorded_for):
                return item, recorded_for
    return None
```

- [ ] **Step 4: 경계와 false/0 기록을 검증하는 실패 테스트 추가**

```python
def test_find_recent_missing_excludes_reference_date_and_stops_after_seven_days(setup):
    _, items, records = setup
    items.add("영어공부", "boolean", None, "22:00")
    for day in range(23, 30):
        records.upsert("영어공부", f"2026-08-{day}", value_bool=False, raw_input="안 했어")

    assert records.find_recent_missing("2026-08-30") is None


def test_find_recent_missing_treats_zero_as_recorded(setup):
    _, items, records = setup
    items.add("물", "quantity", "잔", "22:00")
    for day in range(23, 30):
        records.upsert("물", f"2026-08-{day}", value_num=0, raw_input="0잔")

    assert records.find_recent_missing("2026-08-30") is None
```

- [ ] **Step 5: 관련 테스트 전체 실행**

Run: `pytest tests/msalt/tracking/test_records.py -v`

Expected: all tests PASS.

- [ ] **Step 6: Task 1 커밋**

```bash
git add msalt/tracking/records.py tests/msalt/tracking/test_records.py
git commit -m "feat(tracking): find recent missing records"
```

### Task 2: 후속 질문 포맷과 tracking CLI payload

**Files:**
- Modify: `msalt/tracking/dispatcher.py`
- Modify: `msalt/tracking/cli.py`
- Test: `tests/msalt/tracking/test_dispatcher.py`
- Test: `tests/msalt/tracking/test_cli.py`

**Interfaces:**
- Consumes: `RecordManager.find_recent_missing(ref_date: str, days: int = 7) -> tuple[dict, str] | None`
- Produces: `build_missing_follow_up(item: dict, recorded_for: str) -> tuple[str, ReplyKeyboard]`
- Produces: CLI line prefix `FOLLOW_UP_JSON: ` followed by `{"question": str | null, "reply_keyboard": list[list[str]]}`

- [ ] **Step 1: 공개 포맷 함수의 실패 테스트 작성**

```python
def test_build_missing_follow_up_uses_boolean_question_and_keyboard():
    item = {"name": "영어공부", "schema": "boolean", "unit": None}

    question, keyboard = build_missing_follow_up(item, "2026-08-29")

    assert "영어공부" in question
    assert "2026-08-29" in question
    assert "비어 있어" in question
    assert keyboard == [[
        "영어공부 2026-08-29 했어",
        "영어공부 2026-08-29 안 했어",
    ]]
```

- [ ] **Step 2: 포맷 테스트가 import 실패하는지 실행**

Run: `pytest tests/msalt/tracking/test_dispatcher.py::test_build_missing_follow_up_uses_boolean_question_and_keyboard -v`

Expected: FAIL because `build_missing_follow_up` is not defined.

- [ ] **Step 3: 기존 dispatcher 구현을 감싸는 최소 공개 함수 추가**

```python
def build_missing_follow_up(
    item: dict, recorded_for: str
) -> tuple[str, ReplyKeyboard]:
    target = DispatchTarget(kind="retry", item=item, recorded_for=recorded_for)
    return _solo_text(target), _reply_keyboard_for_item(item, recorded_for)
```

- [ ] **Step 4: CLI 통합 실패 테스트 작성**

```python
def test_record_command_outputs_recent_missing_follow_up(db_path, capsys):
    s = Storage(db_path)
    items = TrackedItemManager(s)
    items.add("수면", "duration", None, "08:00")
    items.add("영어공부", "boolean", None, "22:00")
    RecordManager(s, items).upsert(
        "수면", "2026-08-29", value_num=420, raw_input="7시간"
    )
    capsys.readouterr()

    rc = run_command([
        "record", "수면", "--date", "2026-08-30",
        "--num", "360", "--raw", "6시간",
    ], db_path=db_path)

    assert rc == 0
    line = next(
        value for value in capsys.readouterr().out.splitlines()
        if value.startswith("FOLLOW_UP_JSON: ")
    )
    payload = json.loads(line.removeprefix("FOLLOW_UP_JSON: "))
    assert "영어공부" in payload["question"]
    assert payload["reply_keyboard"][0][0] == "영어공부 2026-08-29 했어"
```

- [ ] **Step 5: 후보가 없을 때 빈 키보드를 출력하는 실패 테스트 추가**

```python
def test_record_command_outputs_empty_follow_up_when_recent_records_are_complete(
    db_path, capsys
):
    s = Storage(db_path)
    items = TrackedItemManager(s)
    items.add("수면", "duration", None, "08:00")
    records = RecordManager(s, items)
    for day in range(23, 30):
        records.upsert("수면", f"2026-08-{day}", value_num=420, raw_input="7시간")
    capsys.readouterr()

    run_command([
        "record", "수면", "--date", "2026-08-30",
        "--num", "360", "--raw", "6시간",
    ], db_path=db_path)

    line = next(
        value for value in capsys.readouterr().out.splitlines()
        if value.startswith("FOLLOW_UP_JSON: ")
    )
    assert json.loads(line.removeprefix("FOLLOW_UP_JSON: ")) == {
        "question": None,
        "reply_keyboard": [],
    }
```

- [ ] **Step 6: CLI에 payload 출력을 최소 구현**

```python
missing = records.find_recent_missing(args.date)
payload: dict[str, object] = {"question": None, "reply_keyboard": []}
if missing:
    item, recorded_for = missing
    question, keyboard = build_missing_follow_up(item, recorded_for)
    payload = {"question": question, "reply_keyboard": keyboard}
print(f"FOLLOW_UP_JSON: {json.dumps(payload, ensure_ascii=False)}")
```

Place this after the existing advice output and before returning `0`.

- [ ] **Step 7: 저장 후 후속 처리 실패를 경고로 분리하는 테스트와 구현 추가**

```python
def test_record_command_keeps_save_success_when_follow_up_fails(
    db_path, capsys, monkeypatch
):
    s = Storage(db_path)
    items = TrackedItemManager(s)
    items.add("수면", "duration", None, "08:00")
    monkeypatch.setattr(
        RecordManager,
        "find_recent_missing",
        lambda self, ref_date, days=7: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    rc = run_command([
        "record", "수면", "--date", "2026-08-30",
        "--num", "360", "--raw", "6시간",
    ], db_path=db_path)

    captured = capsys.readouterr()
    assert rc == 0
    assert "기록되었어: 수면 2026-08-30" in captured.out
    assert "warning: follow-up unavailable: boom" in captured.err
    assert s.record_exists(items.get("수면")["id"], "2026-08-30")
```

Define payload generation in a focused helper and guard only the post-save call:

```python
try:
    payload = _follow_up_payload(records, args.date)
except Exception as exc:
    print(f"warning: follow-up unavailable: {exc}", file=sys.stderr)
    payload = {"question": None, "reply_keyboard": []}
print(f"FOLLOW_UP_JSON: {json.dumps(payload, ensure_ascii=False)}")
```

The broad catch is intentionally limited to optional post-save follow-up generation; record upsert errors continue to use the existing failure path.

- [ ] **Step 8: dispatcher와 CLI 관련 테스트 실행**

Run: `pytest tests/msalt/tracking/test_dispatcher.py tests/msalt/tracking/test_cli.py -v`

Expected: all tests PASS.

- [ ] **Step 9: Task 2 커밋**

```bash
git add msalt/tracking/dispatcher.py msalt/tracking/cli.py tests/msalt/tracking/test_dispatcher.py tests/msalt/tracking/test_cli.py
git commit -m "feat(tracking): emit missing-record follow-up"
```

### Task 3: MessageTool reply keyboard 전달

**Files:**
- Modify: `nanobot/nanobot/agent/tools/message.py`
- Test: `nanobot/tests/tools/test_message_tool.py`

**Interfaces:**
- Consumes: `reply_keyboard: list[list[str]] | None` tool argument
- Produces: `OutboundMessage.metadata["reply_keyboard"]` only when the argument is not `None`; an empty list is preserved

- [ ] **Step 1: outbound metadata 전달 실패 테스트 작성**

```python
@pytest.mark.asyncio
async def test_message_tool_passes_reply_keyboard_metadata() -> None:
    sent = []

    async def capture(msg):
        sent.append(msg)

    tool = MessageTool(
        send_callback=capture,
        default_channel="telegram",
        default_chat_id="123",
    )
    keyboard = [["영어공부 2026-08-29 했어", "영어공부 2026-08-29 안 했어"]]

    result = await tool.execute(content="영어공부 했어?", reply_keyboard=keyboard)

    assert result == "Message sent to telegram:123"
    assert sent[0].metadata["reply_keyboard"] == keyboard
```

- [ ] **Step 2: 빈 배열 보존과 기존 호출 호환성 실패 테스트 추가**

```python
@pytest.mark.asyncio
async def test_message_tool_preserves_empty_reply_keyboard() -> None:
    sent = []

    async def capture(msg):
        sent.append(msg)

    tool = MessageTool(capture, "telegram", "123")
    await tool.execute(content="완료", reply_keyboard=[])
    assert sent[0].metadata["reply_keyboard"] == []


def test_message_tool_schema_exposes_nested_reply_keyboard() -> None:
    schema = MessageTool().parameters
    reply_keyboard = schema["properties"]["reply_keyboard"]
    assert reply_keyboard["type"] == "array"
    assert reply_keyboard["items"]["type"] == "array"
    assert reply_keyboard["items"]["items"]["type"] == "string"
```

- [ ] **Step 3: nanobot 테스트가 새 인자/schema 부재로 실패하는지 실행**

Run: `cd nanobot && pytest tests/tools/test_message_tool.py -v`

Expected: FAIL because `reply_keyboard` is not in the schema or outbound metadata.

- [ ] **Step 4: MessageTool schema와 metadata 전달 최소 구현**

```python
reply_keyboard=ArraySchema(
    ArraySchema(StringSchema("Reply keyboard button text")),
    description="Optional reply keyboard rows; [] removes the current keyboard",
),
```

Add `reply_keyboard: list[list[str]] | None = None` to `execute()`, then build metadata without dropping an empty list:

```python
metadata = {"message_id": message_id} if message_id else {}
if reply_keyboard is not None:
    metadata["reply_keyboard"] = reply_keyboard
```

- [ ] **Step 5: MessageTool 관련 테스트 실행**

Run: `cd nanobot && pytest tests/tools/test_message_tool.py tests/tools/test_message_tool_suppress.py -v`

Expected: all tests PASS.

- [ ] **Step 6: nanobot 서브모듈에 Task 3 커밋**

```bash
cd nanobot
git add nanobot/agent/tools/message.py tests/tools/test_message_tool.py
git commit -m "feat(message): pass reply keyboard metadata"
```

### Task 4: Telegram reply keyboard 렌더링

**Files:**
- Modify: `nanobot/nanobot/channels/telegram.py`
- Test: `nanobot/tests/channels/test_telegram_channel.py`

**Interfaces:**
- Consumes: `OutboundMessage.metadata["reply_keyboard"]` as `list[list[str]]`
- Produces: `ReplyKeyboardMarkup` for non-empty rows, `ReplyKeyboardRemove` for an empty list, no `reply_markup` kwarg when metadata is absent

- [ ] **Step 1: 키보드 생성과 제거 실패 테스트 작성**

```python
@pytest.mark.asyncio
async def test_send_applies_reply_keyboard_from_metadata() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", allow_from=["*"]),
        MessageBus(),
    )
    channel._app = _FakeApp(lambda: None)
    keyboard = [["했어", "안 했어"]]

    await channel.send(OutboundMessage(
        channel="telegram", chat_id="123", content="영어공부 했어?",
        metadata={"reply_keyboard": keyboard},
    ))

    markup = channel._app.bot.sent_messages[-1]["reply_markup"]
    assert markup.keyboard[0][0].text == "했어"
    assert markup.one_time_keyboard is True
    assert markup.resize_keyboard is True


@pytest.mark.asyncio
async def test_send_removes_reply_keyboard_for_empty_rows() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", allow_from=["*"]),
        MessageBus(),
    )
    channel._app = _FakeApp(lambda: None)

    await channel.send(OutboundMessage(
        channel="telegram", chat_id="123", content="저장했어.",
        metadata={"reply_keyboard": []},
    ))

    assert channel._app.bot.sent_messages[-1]["reply_markup"].remove_keyboard is True
```

- [ ] **Step 2: 긴 응답 마지막 청크와 HTML fallback 실패 테스트 작성**

```python
@pytest.mark.asyncio
async def test_send_attaches_reply_keyboard_only_to_last_chunk(monkeypatch) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", allow_from=["*"]),
        MessageBus(),
    )
    channel._app = _FakeApp(lambda: None)
    monkeypatch.setattr("nanobot.channels.telegram.split_message", lambda text, limit: ["앞", "질문"])

    await channel.send(OutboundMessage(
        channel="telegram", chat_id="123", content="긴 응답",
        metadata={"reply_keyboard": [["답"]]},
    ))

    assert "reply_markup" not in channel._app.bot.sent_messages[0]
    assert channel._app.bot.sent_messages[1]["reply_markup"].keyboard[0][0].text == "답"
```

Add this concrete fallback test:

```python
@pytest.mark.asyncio
async def test_send_text_preserves_reply_keyboard_on_html_fallback() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", allow_from=["*"]),
        MessageBus(),
    )
    channel._app = _FakeApp(lambda: None)
    calls = []

    async def fail_html(**kwargs):
        calls.append(kwargs)
        if kwargs.get("parse_mode") == "HTML":
            raise BadRequest("bad html")
        return SimpleNamespace(message_id=1)

    channel._app.bot.send_message = fail_html
    markup = ReplyKeyboardMarkup([["답"]], resize_keyboard=True, one_time_keyboard=True)

    await channel._send_text(123, "질문", None, {}, reply_markup=markup)

    assert len(calls) == 2
    assert calls[0]["reply_markup"] is markup
    assert calls[1]["reply_markup"] is markup
```

- [ ] **Step 3: Telegram 테스트가 reply markup 부재로 실패하는지 실행**

Run: `cd nanobot && pytest tests/channels/test_telegram_channel.py -k "reply_keyboard or last_chunk" -v`

Expected: FAIL because `TelegramChannel.send()` ignores `reply_keyboard`.

- [ ] **Step 4: Telegram 렌더링 최소 구현**

Import `ReplyKeyboardMarkup` and `ReplyKeyboardRemove`. In `send()`, distinguish an absent key from an empty list:

```python
reply_markup = None
if "reply_keyboard" in msg.metadata:
    rows = msg.metadata["reply_keyboard"]
    reply_markup = (
        ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)
        if rows
        else ReplyKeyboardRemove()
    )
chunks = split_message(msg.content, TELEGRAM_MAX_MESSAGE_LEN)
for index, chunk in enumerate(chunks):
    await self._send_text(
        chat_id, chunk, reply_params, thread_kwargs,
        render_as_blockquote=render_as_blockquote,
        reply_markup=reply_markup if index == len(chunks) - 1 else None,
    )
```

Add optional `reply_markup=None` to `_send_text()` and pass it to both HTML and plain-text `_call_with_retry()` calls. Omit the `reply_markup` keyword when it is `None` so existing test call dictionaries and behavior remain stable.

- [ ] **Step 5: Telegram 채널 전체 테스트 실행**

Run: `cd nanobot && pytest tests/channels/test_telegram_channel.py -v`

Expected: all tests PASS.

- [ ] **Step 6: nanobot 서브모듈에 Task 4 커밋**

```bash
cd nanobot
git add nanobot/channels/telegram.py tests/channels/test_telegram_channel.py
git commit -m "feat(telegram): render reply keyboards"
```

### Task 5: tracking 스킬 계약과 통합 검증

**Files:**
- Modify: `msalt/skills/tracking/SKILL.md`
- Modify: `nanobot` submodule pointer in the parent repository
- Test: `tests/msalt/tracking/test_cli.py`

**Interfaces:**
- Consumes: CLI `FOLLOW_UP_JSON` payload and `MessageTool.reply_keyboard`
- Produces: 저장 결과 → 조언 → 질문 순서의 한 메시지와 해당 질문의 reply keyboard

- [ ] **Step 1: tracking 스킬 지침 추가**

Add explicit rules under `## 응답 가이드`:

```markdown
- 성공한 `tracking record` 출력의 `FOLLOW_UP_JSON`은 내부 제어 정보다. JSON 자체는 사용자에게 보여주지 않는다.
- 기록 응답은 항상 `message` 도구로 한 번만 보낸다. 순서는 `저장 결과 → 최근 7일/30일 조언 → follow-up question`이다.
- `question`이 문자열이면 응답 마지막에 그대로 붙이고 `reply_keyboard`를 `message` 도구에 전달한다.
- `question`이 `null`이면 질문을 붙이지 않고 빈 `reply_keyboard`를 전달해 기존 Telegram 키보드를 제거한다.
- `message` 도구로 현재 대화에 전송한 뒤 같은 내용을 일반 최종 응답으로 중복 전송하지 않는다.
```

Preserve all pre-existing user changes in this file and edit only the response guide section.

- [ ] **Step 2: CLI 출력 순서 통합 assertion 추가**

Extend `test_record_command_outputs_recent_missing_follow_up`:

```python
lines = capsys.readouterr().out.splitlines()
saved_index = next(i for i, line in enumerate(lines) if line.startswith("기록되었어:"))
follow_up_index = next(i for i, line in enumerate(lines) if line.startswith("FOLLOW_UP_JSON: "))
assert saved_index < follow_up_index
```

- [ ] **Step 3: msalt 전체 테스트 실행**

Run: `pytest tests/msalt -v`

Expected: all tests PASS with no warnings introduced by this change.

- [ ] **Step 4: nanobot 관련 회귀 테스트 실행**

Run: `cd nanobot && pytest tests/tools/test_message_tool.py tests/tools/test_message_tool_suppress.py tests/channels/test_telegram_channel.py -v`

Expected: all tests PASS.

- [ ] **Step 5: lint 실행**

Run: `ruff check msalt/tracking/records.py msalt/tracking/dispatcher.py msalt/tracking/cli.py tests/msalt/tracking/test_records.py tests/msalt/tracking/test_dispatcher.py tests/msalt/tracking/test_cli.py`

Run: `cd nanobot && ruff check nanobot/agent/tools/message.py nanobot/channels/telegram.py tests/tools/test_message_tool.py tests/channels/test_telegram_channel.py`

Expected: both commands exit 0.

- [ ] **Step 6: 부모 저장소에 스킬 변경과 서브모듈 포인터 커밋**

```bash
git add msalt/skills/tracking/SKILL.md nanobot
git commit -m "feat(tracking): send follow-up keyboard after records"
```

- [ ] **Step 7: 최종 상태 검증**

Run: `git status --short`

Expected: no task-created uncommitted files; any pre-existing unrelated user changes remain untouched.

Run: `git -C nanobot status --short`

Expected: clean nanobot submodule worktree.
