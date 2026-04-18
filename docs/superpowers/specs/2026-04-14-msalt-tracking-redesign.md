# msalt 생활 습관 트래킹 재설계

> **상태**: 설계 확정, 구현 예정
> **작성일**: 2026-04-14
> **이전 설계**: [2026-04-12-msalt-nanobot-design.md](2026-04-12-msalt-nanobot-design.md) (Phase 3 lifestyle 전면 교체)

---

## 1. 배경과 문제

기존 lifestyle 모듈은 세 가지 구조적 한계가 있다.

**할일 관리는 도메인 미스매치.** Todo는 "기록·통계·분석"이 아닌 능동적 작업 관리에 가깝다. msalt-nanobot의 정체성은 "지표 누적과 패턴 가시화"인데 todo가 끼어 들면 봇이 잔소리 도구처럼 느껴진다.

**고정된 기록 도메인.** `sleep_log`(수면 전용 테이블)와 `life_log`(키워드 분류 자유 텍스트) 두 가지로 나뉘어 있어, "음주", "영어 공부 시간" 같은 새 항목을 추가하려면 매번 코드 수정이 필요하다. 사용자가 추적하고 싶은 것은 시기에 따라 달라진다.

**수동 기록 의존.** 사용자가 잊으면 누락된다. 봇은 데이터가 들어왔을 때만 응답할 뿐, 시각이 되었거나 누락이 발생했을 때 먼저 묻지 않는다.

## 2. 목표

- **할일 기능 완전 제거** — 코드·DB 테이블·스킬·CLI·테스트 일괄 삭제
- **사용자 정의 추적 항목** — 자연어로 항목 추가/수정/삭제, LLM이 형식·주기 추론, 사용자 확인 후 등록
- **능동 질문** — agent가 항목별 정해진 시각에 먼저 물어보고, 누락된 항목도 알림
- **과거 시점 입력** — "지난주 화요일에 영어 1시간 했어" 같은 자연어를 LLM으로 파싱

## 3. 비목표

- 다중 사용자 지원, 권한 시스템 — 그대로 1인 가정
- 추적 항목의 그래프·차트 시각화 — 텍스트 통계만 (향후 별도 작업)
- 지난 데이터 자동 마이그레이션 — 기존 sleep/life/todo 데이터는 폐기
- 외부 헬스 플랫폼 연동(Apple Health, Google Fit) — 범위 외

## 4. 핵심 개념

### 4.1 추적 항목 (Tracked Item)

사용자가 정의하는 "기록할 무언가". 항목은 다음을 가진다:

| 속성 | 설명 | 예시 |
|------|------|------|
| `name` | 사용자가 부르는 이름 (한국어 가능) | "수면", "음주", "영어공부" |
| `schema` | 데이터 형식 4종 중 하나 | `duration` |
| `unit` | 단위 (schema=quantity일 때) | "잔", "시간", "회" |
| `schedule_time` | 매일 기록 시각 (HH:MM, KST) | "08:00" |
| `frequency` | 빈도 | `daily` (현재는 daily만 지원) |
| `created_at` | 등록 시각 | — |

**schema 4종:**
- `freetext` — 자유 텍스트. 검색·요약 용도. (예: "감정 메모")
- `duration` — 시작·종료 시각 또는 길이(분). 통계는 평균·합계. (예: 수면, 영어 공부)
- `quantity` — 숫자 + 단위. 통계는 평균·합계. (예: 음주 잔 수)
- `boolean` — 했음/안함. 통계는 수행률(%). (예: 운동 여부)

### 4.2 기록 (Record)

추적 항목에 누적되는 개별 데이터 포인트.

| 속성 | 설명 |
|------|------|
| `item_id` | 어느 항목의 기록인지 |
| `recorded_for` | **데이터가 가리키는 시점** (예: "2026-04-13"의 수면) |
| `recorded_at` | 실제 입력된 시각 (지연 입력 추적용) |
| `value_text` | 자유 텍스트 또는 원본 입력 |
| `value_num` | duration(분) 또는 quantity 숫자 (schema 의존) |
| `value_bool` | boolean 값 |
| `raw_input` | 사용자 원본 발화 (감사·디버깅) |

`recorded_for`와 `recorded_at`을 분리하는 이유: "어제 23시 취침"을 오늘 아침 8시에 입력해도 `recorded_for=2026-04-13`(전날 수면 슬롯), `recorded_at=2026-04-14 08:00`이 정확히 기록된다.

### 4.3 디스패처 (Dispatcher)

매 30분마다 cron으로 실행되는 단일 엔트리포인트. 두 가지 작업을 한다:

1. **시각 도래 검출** — 직전 30분 윈도우 안에 `schedule_time`이 들어가는 항목 찾기 → 사용자에게 "수면 시간 어땠어?" 같은 질문 메시지 전송
2. **미기록 검출** — 시각이 이미 지났는데 오늘(daily 기준) `records`가 없는 항목 → "어제 수면 기록 빠졌네, 지금 입력할래?" 알림

같은 항목이 양쪽에 중복 걸리지 않도록 우선순위는 1번 → 2번 (이번 회차에 1번으로 잡힌 항목은 2번에서 제외).

## 5. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────┐
│  L3 스킬                                             │
│  msalt/skills/                                      │
│    tracking/SKILL.md           ← 대화형: 기록·조회·항목관리│
│    tracking-dispatcher/SKILL.md ← 크론 30분: 능동 질문│
├─────────────────────────────────────────────────────┤
│  L2 도메인 모듈                                      │
│  msalt/tracking/                                    │
│    items.py        — TrackedItem CRUD                │
│    records.py      — Record CRUD + 통계              │
│    dispatcher.py   — 시각 도래/미기록 검출 로직     │
│    parser.py       — LLM 시점·값 추출 (자연어 → 구조)│
│    cli.py          — python -m msalt.tracking 엔트리 │
├─────────────────────────────────────────────────────┤
│  L1 인프라                                           │
│  msalt/storage.py  — tracked_items, records 테이블 추가│
│  msalt/config.py   — 변경 없음                      │
└─────────────────────────────────────────────────────┘
```

**제거되는 것:**
- `msalt/lifestyle/` 디렉토리 전체 (`sleep.py`, `todo.py`, `tracker.py`, `classifier.py`, `cli.py`, `__main__.py`)
- `msalt/skills/lifestyle/` 디렉토리
- `tests/msalt/lifestyle/` 디렉토리 전체
- DB 테이블: `sleep_log`, `todos`, `life_log`

**추가되는 것:**
- 위 L2/L3에 명시된 모듈
- DB 테이블: `tracked_items`, `records`
- nanobot config의 cron 엔트리: 30분 간격 dispatcher 호출

## 6. 데이터 모델

### `tracked_items`

```sql
CREATE TABLE tracked_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    schema TEXT NOT NULL,           -- 'freetext'|'duration'|'quantity'|'boolean'
    unit TEXT,                      -- nullable, schema=quantity일 때만
    schedule_time TEXT NOT NULL,    -- 'HH:MM' (KST)
    frequency TEXT NOT NULL DEFAULT 'daily',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### `records`

```sql
CREATE TABLE records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES tracked_items(id) ON DELETE CASCADE,
    recorded_for TEXT NOT NULL,     -- 'YYYY-MM-DD' (데이터가 가리키는 날짜)
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    value_text TEXT,
    value_num REAL,
    value_bool INTEGER,
    raw_input TEXT NOT NULL,
    UNIQUE(item_id, recorded_for)   -- 같은 날짜 재입력은 덮어쓰기 (upsert)
);

CREATE INDEX idx_records_for ON records(recorded_for);
CREATE INDEX idx_records_item ON records(item_id, recorded_for DESC);
```

### 기본 시드

첫 `Storage.initialize()` 시 빈 `tracked_items`에 자동 삽입:

| name | schema | unit | schedule_time |
|------|--------|------|---------------|
| 수면 | duration | — | 08:00 |
| 음주 | quantity | 잔 | 22:00 |
| 영어공부 | duration | — | 22:00 |

사용자가 삭제하면 다시 시드되지 않는다 (시드 플래그 또는 빈 테이블 검출 기준).

## 7. 컴포넌트 책임

### `tracking/items.py` — TrackedItemManager
항목 CRUD. 메서드: `add(name, schema, unit, schedule_time)`, `get(name)`, `list_all()`, `delete(name)`. UNIQUE(name) 제약 위반 시 `ItemAlreadyExists` 예외.

### `tracking/records.py` — RecordManager
기록 저장·조회·통계. 메서드:
- `upsert(item_id, recorded_for, value_*, raw_input)` — 같은 날짜 덮어쓰기
- `get_recent(item_id, days)` — 최근 N일 기록
- `summarize(item_id, days)` — schema에 따라 평균/합계/수행률 계산해 사람이 읽을 문자열 반환
- `find_missing(item_id, ref_date)` — 해당 날짜에 기록이 있는지

### `tracking/parser.py` — NaturalLanguageParser
LLM(gpt-5-mini) 단발 호출로 자연어 입력에서 다음을 추출:

```python
@dataclass
class ParsedRecord:
    item_name: str | None       # 어느 항목인지 (모호하면 None)
    recorded_for: str           # 'YYYY-MM-DD'
    value_text: str | None
    value_num: float | None
    value_bool: bool | None
    confidence: float           # 0~1
```

또한 항목 추가 의도 추론용 `parse_item_intent(text)`:

```python
@dataclass
class ParsedItemIntent:
    name: str
    schema: str                 # 'freetext'|'duration'|'quantity'|'boolean'
    unit: str | None
    schedule_time: str          # 'HH:MM'
```

### `tracking/dispatcher.py` — Dispatcher
디스패처 진입점. `run(now: datetime)` 한 메서드:

1. `now ± 15분` 윈도우에 `schedule_time` 걸리는 항목 → 질문 메시지 후보
2. `schedule_time < now`이면서 오늘 `records`에 없는 항목 → 누락 알림 후보 (1번 항목과 중복 제거)
3. 양쪽 합쳐 텔레그램으로 전송할 메시지 리스트 반환 (스킬이 message tool로 발송)

`now`를 인자로 받아 테스트 용이성 확보.

### `tracking/cli.py`
`python -m msalt.tracking <command>`:
- `dispatch` — 디스패처 1회 실행 (cron이 호출)
- `add <name> <schema> [--unit X] [--time HH:MM]` — 항목 수동 추가 (디버깅용)
- `list` — 항목 목록
- `record <item> <raw_input>` — 단발 기록 (디버깅용)
- `summary <item> [--days N]` — 통계 출력

운영 중 사용자는 CLI를 거의 안 쓰고 텔레그램 자연어로 처리. CLI는 디버깅·시드·크론용.

### `skills/tracking/SKILL.md`
대화형 진입점. LLM에게 다음 의도들을 안내:
- **기록 입력**: "어제 7시간 잤어" → parser → upsert
- **항목 추가**: "음주도 기록할래" → parse_item_intent → 사용자 확인 → items.add
- **항목 삭제**: "더 이상 영어 공부 기록 안 할래" → 확인 → items.delete
- **조회**: "지난주 수면 평균 알려줘" → records.summarize
- **항목 목록**: "뭐뭐 기록하고 있지?" → items.list_all

### `skills/tracking-dispatcher/SKILL.md`
크론 전용. `metadata: {"always": false}`. 하는 일은 `python -m msalt.tracking dispatch` 실행 결과를 받아 텔레그램 메시지로 전달.

## 8. 사용자 흐름

### 8.1 능동 질문 흐름
```
[08:00] cron → dispatcher
  └─ 수면(08:00 슬롯, 오늘 미기록) 검출
  └─ "어젯밤 잘 잤어? 몇 시간 잤는지 알려줘" 발송

[08:15] 사용자: "11시에 자서 7시에 일어났어"
  └─ tracking 스킬 → parser
  └─ ParsedRecord(item_name="수면", recorded_for="2026-04-13", value_num=480, ...)
  └─ records.upsert
  └─ "기록했어. 8시간이네."
```

### 8.2 항목 추가 흐름
```
사용자: "독서 시간도 매일 자기 전에 기록할래"
  └─ tracking 스킬 → parse_item_intent
  └─ ParsedItemIntent(name="독서", schema="duration", unit=null, schedule_time="22:00")
  └─ "이렇게 등록할게: 독서 / 매일 22:00 / 길이(분). 맞아?"
사용자: "응"
  └─ items.add(...)
  └─ "등록 완료. 오늘 22시부터 물어볼게."
```

### 8.3 과거 시점 입력
```
사용자: "지난주 화요일에 영어 1시간 했어"
  └─ parser
  └─ ParsedRecord(item_name="영어공부", recorded_for="2026-04-08", value_num=60, ...)
  └─ records.upsert (recorded_for=2026-04-08, recorded_at=2026-04-14 ...)
  └─ "2026-04-08 영어공부 1시간으로 기록했어."
```

## 9. nanobot 연동

### Cron 등록
`~/.nanobot/config.json`의 cron 섹션에 항목 추가:

```json
"cron": [
  {"name": "tracking-dispatcher", "schedule": "*/30 * * * *", "skill": "tracking-dispatcher"}
]
```

(news-briefing 기존 cron은 그대로 유지)

### Allowed users
변경 없음. 디스패처가 보내는 메시지도 동일한 단일 사용자 대상.

## 10. 테스트 전략

### 단위 테스트
- `items.py`: CRUD, UNIQUE 충돌, 기본 시드
- `records.py`: upsert(같은 날짜 덮어쓰기), summarize(schema별 계산), find_missing
- `parser.py`: LLM 호출은 모킹, 다양한 자연어 입력 → ParsedRecord 검증
- `dispatcher.py`: `now` 주입해 시각 도래/미기록 검출 검증, 중복 제거 검증

### 통합 테스트
- 시드 → 디스패처 1회 → 미기록 알림 검출 → 기록 입력 → 다음 회차 디스패처 → 미기록 사라짐

### 모킹 정책
이전과 동일. SQLite는 `tmp_path` 실DB, OpenAI/Telegram은 모킹.

## 11. 마이그레이션 절차 (실행 순서)

1. `tests/msalt/lifestyle/` 삭제
2. `msalt/lifestyle/` 삭제
3. `msalt/skills/lifestyle/` 삭제
4. `Storage`에서 `sleep_log`, `todos`, `life_log` 테이블 생성·메서드 제거
5. `msalt/tracking/` 신규 생성 (items, records, parser, dispatcher, cli, __main__)
6. `Storage`에 `tracked_items`, `records` 테이블·메서드 추가, 기본 시드 로직
7. `msalt/skills/tracking/`, `msalt/skills/tracking-dispatcher/` 신규
8. `msalt/nanobot-config.example.json`에 cron 엔트리 추가
9. 신규 테스트 작성 (TDD: 각 모듈 테스트 먼저, 구현 뒤)
10. 문서 갱신: PRD §4.2, TRD §3.3 / §4 / §5, README, SOUL.md, USER.md, msalt-setup.md, msalt-rpi-deploy.md, 기존 design/plan 문서에 "deprecated lifestyle" 노트
11. ADR 추가: PRD §8에 항목(11~14): 할일 제거, 동적 항목, 디스패처, LLM 파서

## 12. 주요 의사결정 (이 spec)

| # | 결정 | 대안 | 이유 |
|---|------|------|------|
| 1 | 할일 기능 완전 제거 | 유지 / 별도 모듈 분리 | 도메인 미스매치, 봇 정체성과 충돌 |
| 2 | tracked_items + records 2테이블 | item별 테이블 동적 생성 | SQLite 동적 DDL은 안티패턴, 일반 SQL로 충분 |
| 3 | schema 4종 고정 | freetext만 / 더 많은 형식 | 통계 비용·복잡도 균형. 4종으로 일상 기록 95% 커버 |
| 4 | LLM 자동 추론 + 사용자 확인 | 자연어만 / CLI만 | 자연스러움 + 안전장치, 빈도 낮은 작업이라 한 번 묻는 마찰 허용 |
| 5 | 단일 cron 디스패처 (30분) | 항목별 cron | 동적 항목 변경 단순, ±15분 정밀도 충분 |
| 6 | 모든 자연어 LLM 파싱 | 룰 + LLM 폴백 | gpt-5-mini 비용 미미, 코드 단순성 우위 |
| 7 | 깨끗한 마이그레이션 (기존 데이터 폐기) | 데이터 보존 마이그레이션 | 개발 단계, 운영 데이터 거의 없음 |
| 8 | recorded_for vs recorded_at 분리 | 단일 timestamp | 지연 입력·과거 시점 입력의 정확한 시계열 보장 |

---

## 부록: 영향 받는 문서 목록

- [docs/msalt-prd.md](../../msalt-prd.md) §4.2, §8 (ADR)
- [docs/msalt-trd.md](../../msalt-trd.md) §3.3, §4, §5
- [msalt-nanobot.md](../../../msalt-nanobot.md) 기능 섹션, 디렉토리 트리
- [msalt/workspace/SOUL.md](../../../msalt/workspace/SOUL.md) §주요 역할
- [msalt/workspace/USER.md](../../../msalt/workspace/USER.md) 루틴
- [docs/msalt-setup.md](../../msalt-setup.md), [docs/msalt-rpi-deploy.md](../../msalt-rpi-deploy.md)
- 기존 design/plan에는 "lifestyle 섹션은 본 spec으로 대체됨" 노트 추가
