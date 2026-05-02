# Tracking 알림 smart retry chain 설계

## 배경

현재 `msalt/tracking/dispatcher.py`는 30분 주기 systemd 타이머로 동작하며 두 종류 알림을 보낸다:

1. **첫 알림** — 항목의 `schedule_time`이 직전 30분 윈도우 안에 들어오면 발송
2. **누락 알림** — 슬롯이 지나갔는데 24시간 내 record가 없는 항목에 대해 그날 한 번 발송

문제점:

- **+30분 일괄 재알림이 noise** — 22:00 슬롯이면 22:00 첫 발송, 22:30 tick에서 슬롯이 여전히 30분 윈도우 안이라 누락 알림이 또 fire. 사용자에게는 "30분 뒤 같은 항목으로 한 번 더 알림" 패턴으로 보여 무의미한 반복.
- **누락 후 다음 시도가 너무 늦음** — `last_missed_asked_date` 플래그로 그날 1회만 묻고 끝. 아침에 답이 없어도 저녁에 다시 시도하지 않음. 다음날에야 새 슬롯이 와서 처음부터 다시.
- **여러 항목 미답 시 메시지 분산** — 영어공부, 음주가 동시에 미답이면 메시지 2개가 따로 옴.

## 목표

- dispatcher tick 1회 = 텔레그램 메시지 **최대 1개** (여러 항목은 하나로 묶음)
- 시간대 기반 retry chain (오전 → 오후 → 저녁 → 다음날 첫 슬롯 직전)
- boolean 항목은 사용자의 부정 답("아니", "안 했어")을 N record로 자동 처리, retry 종료

## 비목표

- 항목별 retry 스케줄 커스터마이즈 (글로벌 retry 슬롯 고정)
- "스킵" / "오늘은 패스" 명시 답 (boolean 외 schema에는 도입하지 않음 — YAGNI)
- 알림 채널 변경 (텔레그램 외 추가 안 함)

## 사용자 시나리오

1. **수면 (22:00 schedule)을 답하지 않은 경우**
   - 22:00 첫 알림 1회
   - 다음날 09:00 글로벌 retry 슬롯에서 재질문 (단, 다른 미답 항목이 있으면 묶임)
   - 14:00, 20:00 retry 슬롯에서도 동일
   - 22:00 도달 시 어제 분 폐기, 새 슬롯 시작

2. **영어공부와 음주가 둘 다 미답인 경우**
   - 09:00 retry 슬롯에서 한 메시지에 두 항목을 묶어 발송
   - 사용자가 `"영어 했고 한 잔 마셨어"` 같이 자유 형식으로 한 번에 답하면 LLM 파서가 매칭

3. **boolean 항목 "아니" 답**
   - LLM 파서가 N으로 기록 → record 추가 → 다음 tick에서 `pending_since` 클리어 → retry 종료

## 핵심 모델 변경

`tracked_items` 테이블 컬럼:

| 컬럼 | 변경 | 의미 |
|---|---|---|
| `last_missed_asked_date` | **DROP** | 더 이상 사용 안 함 |
| `pending_since` | **ADD** (TEXT NULL, UTC ISO) | 첫 알림 보낸 시각. record가 들어오거나 다음 schedule_slot 도래 시 NULL |
| `last_asked_at` | **ADD** (TEXT NULL, UTC ISO) | 가장 최근 알림 시각. retry 슬롯 중복 fire 방지 |

"답이 들어왔는가"는 별도 플래그 없이 `records` 테이블에 `pending_since` 이후 시각의 record가 있는지로 판단.

### 마이그레이션

`Storage.initialize()`에서 ALTER TABLE로 처리:

- sqlite ≥ 3.35: `ALTER TABLE tracked_items DROP COLUMN last_missed_asked_date`
- sqlite < 3.35: 옛 컬럼은 그대로 두고 무시 (read/write 안 함)

라즈베리파이 OS의 sqlite 버전이 3.35 미만일 가능성이 있으므로 코드는 두 경로 모두 안전해야 한다 (DROP 시도 → 실패하면 무시).

새 컬럼은 단순 `ALTER TABLE ADD COLUMN ... DEFAULT NULL`로 추가.

## 글로벌 retry 슬롯

```python
GLOBAL_RETRY_SLOTS = ["09:00", "14:00", "20:00"]   # KST
```

- 디스패처 코드 상수로 정의 (config 파일화는 YAGNI)
- 항목별 `schedule_time`은 첫 알림에만 사용
- 글로벌 슬롯은 `pending_since != NULL`인 항목들에만 적용

## Dispatcher 알고리즘

30분 주기 tick 의사코드:

```
SLOT_WINDOW = (now - 30min, now]   # 슬롯 도달 판정용 윈도우 (반-개)
GLOBAL_RETRY_SLOTS = ["09:00", "14:00", "20:00"]

batch = []   # 이번 tick에 알림 보낼 항목들

for item in all_items:
    # 1. record가 pending 이후로 들어왔으면 pending 클리어
    if item.pending_since and records.has_since(item.id, item.pending_since):
        item.pending_since = NULL

    # 2. 다음 schedule_slot 도래 직전인지 확인 → 이전 pending 폐기
    #    (next_schedule_slot 정의는 아래 섹션 참고)
    if item.pending_since and now >= next_schedule_slot_dt(item, item.pending_since):
        item.pending_since = NULL

    # 3. 첫 알림 — 항목의 schedule_time 슬롯이 SLOT_WINDOW에 들어옴
    schedule_slot_today = today @ item.schedule_time   # KST
    if schedule_slot_today in SLOT_WINDOW:
        if not records.has_since(item.id, now - 24h):
            batch.append(item)
        continue   # 첫 알림 발송 항목은 같은 tick에서 retry 분기로 안 감

    # 4. retry — pending이고 글로벌 retry 슬롯이 SLOT_WINDOW에 들어옴
    if item.pending_since:
        retry_slot_dt = SLOT_WINDOW에 들어온 GLOBAL_RETRY_SLOTS 슬롯 (today @ HH:MM, KST)
        if retry_slot_dt and (item.last_asked_at is NULL or item.last_asked_at < retry_slot_dt):
            batch.append(item)

# 5. 한 메시지로 묶어 발송
if batch:
    send_telegram(format_batch(batch))
    for item in batch:
        if not item.pending_since:
            item.pending_since = NOW   # UTC
        item.last_asked_at = NOW       # UTC
```

### `next_schedule_slot_dt(item, pending_since)`의 정의

"이전 pending이 stale인지" 판단하는 기준 시각. 항목의 `schedule_time`을 KST로 해석해, **`pending_since` 시각보다 미래의 가장 가까운 schedule_time 슬롯**을 반환한다.

예: 항목 schedule=22:00, `pending_since=2026-05-01 13:00 UTC` (= 2026-05-01 22:00 KST 직후 첫 알림) → next_schedule_slot_dt = 2026-05-02 22:00 KST. 그 시점 도달 시 어제 분 pending 폐기.

### 자연 cap

"최대 N회 retry" 같은 임의 숫자 없이 다음 schedule_slot 도래로 자연스럽게 retry chain이 종료된다. 22:00 schedule이면 다음 22:00까지 최대 3회 retry (다음날 09:00, 14:00, 20:00) → 22:00에 새 슬롯 시작.

### 같은 슬롯 중복 fire 방지

같은 retry 슬롯이 두 번 다른 tick에서 윈도우 안에 들어올 일은 거의 없지만(SLOT_WINDOW = 30분), `last_asked_at < retry_slot_dt` 비교로 안전하게 중복 fire를 막는다.

### 첫 알림과 retry 슬롯이 우연히 겹치면

예: 항목 schedule_time=09:00 (글로벌 retry 슬롯과 겹침). 09:00 tick에서는 step 3 `continue`로 인해 retry 분기를 건너뛰므로 한 메시지에 한 번만 들어간다. 다른 항목이 같은 tick에 retry로 fire되면 같은 batch에 묶인다.

## 메시지 포맷

### 단일 항목

기존 톤 유지 (schema별 분기):

- `duration` → `⏰ '수면' 기록할 시간이야. 얼마나 잤어?`
- `quantity` → `⏰ '음주' 기록할 시간이야. 몇 잔이야?`
- `boolean` → `⏰ '영어공부' 했어?`
- `freetext` → `⏰ '메모' 한 줄 남겨줘.`

### 복수 항목 (≥ 2)

번호 리스트로 묶음, schema별 힌트 그대로 재사용:

```
📝 기록할 항목 3개:
1. 수면 — 몇 시간 잤어?
2. 음주 — 몇 잔?
3. 영어공부 — 했어?
```

힌트 텍스트는 단일 항목 메시지에서 추출하는 헬퍼로 공유 (`_question_hint(item) -> str`).

## LLM 파서 영향

사용자가 `"7시간 잤어, 2잔, 했어"` 같이 한꺼번에 답할 수 있어야 한다. 기존 LLM 파서가 이미 자연어를 처리하므로:

- **batch context hint** — 파서 호출 시 "최근 알림에서 물어본 항목 목록"을 시스템 프롬프트에 한 줄 추가. 예: `"사용자가 응답 중인 미답 항목: 수면(duration), 음주(quantity), 영어공부(boolean)"`
- **boolean 부정 답 처리** — 시스템 프롬프트에 `"항목이 boolean이고 사용자가 '아니/안 했어/no' 등 부정 의미를 표현하면 N으로 기록하라"` 추가

코드 변경: 파서 진입점에서 항목 목록을 받을 수 있게 시그니처 확장 (옵션 인자). 디스패처가 알림 보낸 항목들의 id를 어딘가에 저장해 둘 필요가 있는데 — `pending_since` 자체로 추론 가능 (NULL이 아닌 항목들). 파서 호출 시 `pending_since != NULL`인 항목 목록을 자동으로 hint에 포함.

## 테스트 전략

`dispatcher.py`는 이미 `now: datetime` 주입형 구조이므로 결정론적 테스트 가능. 시간을 freezing하는 fixture로 다음 시나리오 검증:

| # | 시나리오 | 기대 동작 |
|---|---|---|
| 1 | schedule_time이 윈도우 안, pending 없음 | fire, pending_since 세팅 |
| 2 | 첫 알림 직후 다음 tick (30분 뒤, 슬롯은 윈도우 밖) | fire 안 함 (현재 +30 알림 noise 제거 검증) |
| 3 | 글로벌 retry 슬롯, pending 없음 | fire 안 함 |
| 4 | 글로벌 retry 슬롯, pending 있음 | fire, last_asked_at 갱신 |
| 5 | 다음날 schedule_slot 도달 | 이전 pending 폐기 + 새 fire |
| 6 | record가 들어옴 | 다음 tick에서 pending 클리어, retry 안 함 |
| 7 | 여러 항목 동시 fire | 한 메시지로 묶음 (배치) |
| 8 | boolean "아니" 답 | N record + pending 클리어 (파서 테스트) |
| 9 | sqlite < 3.35 마이그레이션 | DROP COLUMN 실패해도 ADD COLUMN은 적용 |

기존 `test_dispatcher.py`의 `last_missed_asked_date` 관련 케이스는 제거 또는 새 모델로 대체.

## 영향 범위

**변경 파일**:

- `msalt/storage.py` — schema migration, `pending_since`/`last_asked_at` getter/setter
- `msalt/tracking/dispatcher.py` — 알고리즘 전면 재작성
- `msalt/tracking/parser.py` — batch context hint, boolean 부정 답
- `tests/msalt/tracking/test_dispatcher.py` — 새 시나리오로 재작성
- `tests/msalt/tracking/test_parser.py` — boolean 부정 답 케이스 추가

**호환성**:

- 라즈베리파이의 기존 SQLite DB는 `Storage.initialize()`가 자동 ALTER. 데이터 손실 없음.
- 옛 `last_missed_asked_date` 컬럼이 sqlite 버전상 DROP 안 되더라도 무시되므로 동작에 영향 없음.

## Out of Scope (의도적 미포함)

- 항목별 custom retry 슬롯 — 글로벌 09/14/20 고정
- "오늘은 스킵" 답 (boolean 외 schema)
- 알림 우선순위/sort 순서 — 항목 등록 순서 그대로
- 텔레그램 inline button (Yes/No, 시간 선택 등)
