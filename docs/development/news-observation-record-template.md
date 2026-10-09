# #7 비공개 뉴스 관찰 기록 양식
저장소 밖 접근 제한된 위치에 복사해 작성한다. 토큰 원문 대신 비밀 저장소 참조만 사용한다. [승인 실행 절차](news-operations-validation.md)와 [공통 비공개 기록](private-operations-record-template.md)을 함께 사용한다.
## 실행 전 기록
- 실제 OCI 대상/checkout·DB·workspace 실체/단일 gateway·추가 writer/수신 chat·thread 대조: 미확인.
- candidate/이전 SHA·gitlink·venv·unit/예약 상태: 미확인.
- 후보 PR 검수 및 구체 작업창·정지/쓰기·API/발송·rollback 승인: 미확보.
- 최신 일관 backup/격리 restore·digest/integrity·기존 4개 테이블 행·키·내용 보존: 미실행.
- 공급자별 hard cost enforcement·최악 비용 reservation·실제 소비 대조: 미확인.
- 관찰 시작/종료 KST 및 UTC, D1–D7 실제 날짜 대응: 미실행.
## 실제 예약 21개
각 단계에 별도 증거를 연결한다. 생성/본문 hash·delivery_id, part별 message_id/API ACK·DB commit, Human 화면 실수신을 구분한다.
| 관찰일 | 예정 KST | 실행 시각 | 생성/수집1회 | part API ACK | 원장 commit | Human 실수신/중복·누락 | 판정 |
|---|---|---|---|---|---|---|---|
| D1 | 07:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D1 | 14:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D1 | 20:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D2 | 07:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D2 | 14:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D2 | 20:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D3 | 07:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D3 | 14:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D3 | 20:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D4 | 07:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D4 | 14:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D4 | 20:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D5 | 07:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D5 | 14:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D5 | 20:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D6 | 07:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D6 | 14:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D6 | 20:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D7 | 07:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D7 | 14:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
| D7 | 20:00 | 미실행 | 미실행 | 미실행 | 미실행 | 미확인 | BLOCKED |
## 추가 표본·한도·예외
- smoke: 미실행(최대 3회), 명시적 수동 재전송: 미실행(최대 1회).
- 누계: 생성/24·summary HTTP/72·configured 검색 HTTP/96·logical delivery/25·part/100·POST/300: 미확인. 실패/timeout/retry 및 agent 오케스트레이션 비용도 포함한다.
- 비용: 미확인/US$5. US$4 신규 뉴스 중지, 진행 중/다음 작업 최악 비용 reservation과 hard 차단 근거를 기록한다. 관찰 재시작에 counter를 초기화하지 않는다.
- 자원: 디스크·메모리·OOM/restart·정지 시간·원래 timer 복귀: 미관찰.
- 소스별 PASS/FAIL/SKIP·빈 안내와 전체 실패 구분: 미관찰.
- known failed/unknown/부분 발송, 저장 payload hash·기존 ACK part skip·수동 resolve/confirm: 미관찰.
- 새 생활 기록 delta 보존·현재 DB 유지 rollback·운영 DB 덮어쓰기 별도 승인: 미확인.
## 공개 결과 / 최종 수용
AC1–6별 실제 명령/exit·검수 SHA·PASS/FAIL/BLOCKED·Human 수용을 비식별 공개 보고서로 옮긴다. 서버/수신자 식별자·본문·로그/설정 원문·토큰 URL은 제외한다. 후보/최종 코드 일치·최종 운영 SHA·명시 merge 승인을 기록한다. 문서 준비로 실수신/상한 enforcement가 적용됐다고 기록하지 않는다.

