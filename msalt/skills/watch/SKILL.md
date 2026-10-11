---
name: watch
description: 관심 조건의 등록·조회·수정·중지·재개·삭제, 저장 기사 평가와 결과 조회 요청에 사용한다.
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
- 저장 기사 평가를 제공하며 알림 발송·정기 수집·Watch cron은 제공하지 않는다. 조건을 active로 바꾸거나 평가가 성공했다고 알림 발송 성공을 주장하지 않는다.


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
