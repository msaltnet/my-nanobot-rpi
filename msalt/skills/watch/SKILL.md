---
name: watch
description: 관심 조건의 등록·조회·수정·중지·재개·삭제, 저장 기사 평가·결과 조회·알림 상태와 운영 제어 요청에 사용한다.
---

# Watch 조건과 저장 기사 평가

사용자가 관심 조건을 등록하거나 관리하려는 경우 사용한다. 예시는 합성 fixture이며 실제 관심사로 추측하지 않는다.

## 사용자 확인과 실행

1. 관심 조건의 이름, 설명, literal 포함 키워드, 제외 키워드를 정리하고 사용자에게 요약해 확인한다. 기존 대화에서 같은 범위를 명확히 승인했으면 반복 확인하지 않는다.
2. 등록은 paused 상태다. 사용자에게 아직 활성화하지 않았음을 알린다. 재개하려는 의도가 확인되면 `show` 결과의 현재 revision으로 `resume`한다.
3. 수정·중지·재개·삭제 전 `show ID --json`으로 상태와 revision을 확인한다. 삭제는 대상 이름과 삭제 의도를 명시적으로 확인한 뒤에만 `--confirm`을 사용한다. 중지는 삭제가 아니다.
4. `my-nanobot-rpi watch ...` 명령만 사용한다. 임의 파일 편집, Python 인터프리터 폴백, 직접 SQL 쓰기로 우회하지 않는다. 사용자 값은 JSON 직렬화하고 안전한 셸 인수 quoting으로 전달하며 코드로 해석하지 않는다.
5. 성공 exit0의 실제 출력으로 결과를 안내한다. exit2는 입력 오류/없는 ID/중복 이름/revision 충돌이다. 충돌이면 다시 조회하고 사용자 의도를 확인한다. exit1은 DB 실패다. 실패를 저장 성공으로 안내하거나 자동 재시도하지 않는다.

```bash
my-nanobot-rpi watch add "조건 이름" --description "조건 설명" --keywords-json '["키워드"]' --excluded-json '["제외어"]' --json
my-nanobot-rpi watch list --json
my-nanobot-rpi watch list --all --json
my-nanobot-rpi watch show 1 --json
my-nanobot-rpi watch update 1 --expected-revision 1 --description "새 설명" --keywords-json '[]' --json
my-nanobot-rpi watch resume 1 --expected-revision 2 --json
my-nanobot-rpi watch pause 1 --expected-revision 3 --json
my-nanobot-rpi watch delete 1 --expected-revision 4 --confirm --json
```

`update`의 선택 인수는 `--name`, `--description`, `--keywords-json`, `--excluded-json`이다. 변경할 필드만 전달한다. ID와 revision은 예시를 복사하지 말고 실제 조회 값으로 대체한다.

## 조건의 의미와 상한

- 이름 1–80자, 설명 1–2,000자. 포함/제외 키워드는 각각 최대20개의 문자열, 각1–100자이며 공백만 있는 값은 거절한다. 빈 배열은 허용한다.
- 포함 키워드는 literal substring OR, 제외 키워드는 OR veto다. 비교는 NFKC+casefold이며 정규식/명령/임의 코드 해석은 없다. 포함 배열이 비면 후보 필터를 생략한다. 표시에는 원문을 유지한다.
- active 최대20개, 미삭제 최대100개다. 이름은 normalize 결과가 같으면 중복이고, 삭제한 이름도 재사용할 수 없다. 새 이름으로 등록한다.
- 생성은 paused/revision1. 재개와 실제 수정은 revision을 증가시키고 현재 저장 기사 최대 ID를 시작점으로 잡는다. 중지·삭제는 revision만 증가하고 시작점을 보존한다. 같은 상태로 중지/재개하거나 동일 필드로 수정하면 현재 revision 검증 후 변경하지 않는다.
- 재개 이후 들어오는 기사만 다음 평가의 대상이다. 중지 동안의 기사와 이전 revision의 backlog는 재개 후 알림에서 제외된다. 삭제는 조건 이력과 과거 결과를 보존하는 soft delete다. `list --all`과 `show`로 삭제된 조건을 볼 수 있다.
- 저장 기사 평가와 명시적 알림 dispatcher를 제공한다. 기본 알림은 disabled이며 정기 수집·Watch cron은 설치하지 않는다. 조건을 active로 바꾸거나 평가가 성공했다고 알림 발송 성공을 주장하지 않는다.


## 저장 기사 평가와 결과 조회

- 결과 조회 요청에는 `evaluations`를 사용한다. 이미 저장된 평가 결과를 보여주며 모델을 호출하지 않는다. 상태, 판단 이유, 실제 제목/요약의 근거, 원문 발행일, stale 여부를 안내한다. `error`는 판단 실패이며 관련 없음으로 설명하지 않는다. 과거 revision의 결과는 이력이며 현재 알림 후보가 아니다.
- 실제 평가에는 모델 호출과 API 비용이 발생할 수 있다. 사용자가 실제 모델 호출과 비용을 승인한 평가 요청에서만 `evaluate`를 실행한다. 조건 등록·재개나 결과 조회만으로 자동 평가하지 않는다. 반복 실행이나 timer도 설치하지 않는다.
- 평가는 현재 DB에 저장된 기사만 소비한다. 등록 후 재개/수정 시점의 기사 시작점 이후 새 ID를 오래된 발행일이어도 대상으로 삼는다. 추가 기사 수집과 발송은 하지 않는다.
- 한 실행의 상한은 전체 후보 100개와 모델 요청 예약 10회다. `--max-articles`는 1–100, `--max-calls`는 0–10으로 요청 범위에 맞게 지정한다. 호출 0은 모델 호출 없이 literal 필터 결과만 기록할 수 있다. 모델 출력 최대500 tokens, 요청20초다.
- 실패는 자동 재시도하지 않는다. 사용자가 실패 재평가를 요청한 경우에만 `--retry-errors`를 사용한다. 후보별 최대3회의 예약만 허용하며 중단된 예약도 한 번으로 센다. 재시도에는 저장한 입력과 근거를 사용한다.
- relevant와 high 결과라도 실제 판정 품질은 사용자 표본 확인이 필요하다. 평가 완료 개수와 예약 호출 수를 실행 결과대로 안내하며 수신·발송 성공으로 설명하지 않는다.

```bash
my-nanobot-rpi watch evaluations --watch-id 1 --status relevant --limit 20 --json
my-nanobot-rpi watch evaluate --max-articles 100 --max-calls 10 --json
my-nanobot-rpi watch evaluate --max-articles 100 --max-calls 10 --retry-errors --json
```

조회의 `--watch-id`와 `--status`는 선택 사항이다. status는 pending/evaluating/relevant/irrelevant/error이며 limit은 1–1,000이다. 예시 평가 명령을 실제 호출 승인 없이 실행하지 않는다.


## Watch 알림과 운영자 제어

- 알림 상태를 묻는 요청은 `notify status --json`으로 조회한다. 상태·시간·비식별 오류·확인된 message ID만 안내하며 저장한 원문 payload나 recipient를 출력하거나 다시 전송하지 않는다. 상태 조회 자체는 외부 호출/복구/발송이 없다.
- 실제 `notify dispatch`는 Telegram 발송을 할 수 있다. 사용자가 승인한 배포 대상·고정 코드·발송 범위에서만 실행한다. 조건 등록·재개·평가·상태 조회만으로 dispatcher를 호출하거나 enable하지 않는다. enable과 실제 발송 승인은 서로 다른 범위다. 기본 disabled이며 timer/unit/정기 수집은 이번 MVP에 설치하지 않는다.
- `notify enable|disable --confirm`은 대상 DB의 공유 상태를 바꾼다. 명시적 사용자 의도를 확인한 경우에만 `--confirm`을 사용한다. disable은 신규 예약을 막는다. 이미 시작한 POST의 취소나 미수신을 보장하지 않는다. 검사 직후 중지와 POST 사이의 race는 남는다.
- active·현재 revision의 relevant+high만 대상이다. 같은 URL의 여러 Watch는 한 기사 항목으로 이유를 합친다. 저장한 평가 입력의 제목/URL/이유를 결정적으로 표시하고 모델을 다시 호출하지 않는다. 전역 오래된 article ID 우선이며 recipient별 KST 09:00 이상 21:00 미만, 시간 슬롯당1·KST 일일6·메시지3기사·3,500자 이하(UTF-16 단위도 보수적으로 제한)다. 길면 제목/이름/이유를 줄이고 URL은 보존한다. 쪼개지 못하는 원문은 보류한다.
- 전역 FIFO의 평가 URL key를 한 번에100행씩 읽고 표시 불가능한 앞 항목을 지나 다음 후보까지 진행한다. 어떤 invocation도 같은 첫100행에서 끝나며 뒤 기사를 영구 보류하지 않는다. URL별 현재 Watch 이유는 최대20개, 선택 article snapshot은 최대3개 그룹만 메모리에 유지한다. 이미 채운 메시지의 남은 공간에 들어가지 않지만 새 메시지에는 들어가는 오래된 기사는 다음 슬롯의 첫 항목이 되며, 더 젊은 기사로 우회하지 않는다. 모든 항목이 표시 불가능하면 전체 backlog를 읽을 수 있어 CPU·읽기 스냅샷 시간이 늘어난다. SQLite DELETE journal의 SHARED 읽기 잠금은 writer commit을 지연시킬 수 있다. 읽기 snapshot을 닫은 뒤 짧은 쓰기 transaction에서 모든 선택 후보/URL claim과 실제 시간을 재검사한다. 읽기 이후 새로 완료된 이전 article ID의 평가 결과는 다음 invocation에 보인다. 뉴스 브리핑과 알림의 URL 이력은 분리되므로 두 기능 사이 같은 기사 전달은 가능하다.
- pending만 확실히 POST 전 상태다. dispatcher 재시작은 같은 시간 슬롯의 pending을 재개할 수 있다. 슬롯이 바뀌면 옛 pending을 cancelled로 보존하고 새 슬롯/day quota로 새 payload를 예약한다. 최종 검사에서 어떤 조건이라도 중지·삭제·revision 변경 또는 disabled이면 batch 전체를 취소하고 URL 예약을 해제하되 quota와 이미 소비한 attempt는 반환하지 않는다.
- `sending`은 POST가 시작했을 수 있고, dispatcher 시작 시 `unknown`으로 보존한다. unknown은 자동 만료/재전송하지 않으며 URL claim을 유지한다. HTTP2xx + JSON 객체의 정확한 `ok=true` + 양의 message ID만 sent다. 객체의 정확한 `ok=false`는 HTTP 상태와 무관하게 rejected다. 그 밖의 응답/timeout/취소/ACK 저장 실패는 unknown 또는 unresolved sending이다. ACK는 실제 사용자 수용을 뜻하지 않는다.
- rejected는 새 슬롯에서 한 번 더 시도할 수 있다. URL별 실제 sending 예약은 총2회이며 중단 직전 예약도 보수적으로 소비한다. manual retry에도 같은 attempt·slot·day cap이 적용된다. 이미 ACK된 URL은 새 revision에서도 자동 재알림하지 않는다.
- `notify resolve ID --outcome sent|retry --confirm`은 운영자만 수행한다. 먼저 관련 worker가 멈췄는지 확인하고 실제 수신/미수신 근거를 확인한다. sent는 `--evidence`와 실제 양의 `--message-id`가 필수이며 새로운 POST 없이 receipt/audit만 저장한다. retry는 `--evidence`와 재전송 의도 확인이 필수이며 다음 명시적 dispatcher에서 새 예약·attempt·quota를 사용한다. sending을 해결/해제하지 않는다. 이미2회를 쓴 URL retry는 거절한다.
- `--now`는 실제 production 시간을 덮어쓰는 수동 진단 인수다. `--diagnostic-time`을 함께 명시한 격리/승인 진단에서만 쓴다. 시간 우회로 한도를 늘리지 않는다. 입력 오류 exit2, DB 실패 exit1을 성공으로 안내하지 않는다.

```bash
my-nanobot-rpi watch notify status --json
# 아래 변경/발송은 실제 해당 범위를 승인받은 운영자만 실행한다.
my-nanobot-rpi watch notify enable --confirm --json
my-nanobot-rpi watch notify dispatch --json
my-nanobot-rpi watch notify disable --confirm --json
my-nanobot-rpi watch notify resolve DELIVERY_ID --outcome sent --evidence "확인한 수신 근거" --message-id MESSAGE_ID --confirm --json
my-nanobot-rpi watch notify resolve DELIVERY_ID --outcome retry --evidence "확인한 미수신과 재시도 근거" --confirm --json
```

실수신·유용성·알림 부담(W11-6)은 별도 승인 운영에서 Human이 수용해야 한다. fixture 테스트나 sent 상태만으로 실제 사용 PASS를 주장하지 않는다.
