# 뉴스 후보 운영 사전 검증 — 2026-10-09 KST

## Context

- 계약: [Issue #7 v2](https://github.com/msaltnet/my-nanobot-rpi/issues/7), 구현 후보 [#13 PR #24](https://github.com/msaltnet/my-nanobot-rpi/pull/24) 및 [#14 PR #22](https://github.com/msaltnet/my-nanobot-rpi/pull/22).
- Human 요청: “운영 환경을 네가 알고 있으니까 스스로 검증하고 결과까지 정리해서 검토까지 해줘.” 기존 지정 대상과 v2 한도 안의 자율 검증·결과 정리/리뷰 근거다.
- 제품 후보 SHA: `a791c17a2523551181739b72416a18452ed435d1`; dependency `13c7435eb85577d3004ee4bbee5fcb4fbdcc203d`.
- 실제 운영 대상의 읽기 점검과 **운영 DB 읽기 사본** 검증을 수행했다. 제품 코드·운영 DB·설정·서비스·예약을 변경하지 않았다.
- 상세 대상·설정·데이터 수치·fingerprint·사본 위치는 비공개로 보관한다. 공개 보고서는 판정과 한계를 기록한다.
- 수행: Implementer root, 별도 Reviewer `ops_preflight_review`. 후보 제품 자체 검수/CI는 PR #24의 독립 결과다. 이번 보고서는 그 소스와 테스트를 수정하지 않는다.

## Test Report

| 범위 | 실제 절차 | 결과 |
|---|---|---|
| 대상 점검 | 기존 지정 대상에 SSH 읽기 접속; 현재 버전·clean 상태·서비스·예약·자원 확인 | 사전 읽기 점검 PASS. 서비스/예약 상태는 실수신 증거가 아님 |
| 일관 DB 사본 | 존재하는 DB를 SQLite URI `mode=ro`로 열어 읽기 transaction; `Connection.backup`으로 새 비공개 사본 생성 | 원본 읽기 기준과 사본의 기존 테이블 fingerprint 동등 PASS |
| 후보 migration | 고정 후보의 Storage/schema 파일을 격리 공간에 복사; 네트워크 차단; 사본에서 `Storage.initialize()` 2회 | 기존 테이블 행·값 보존, additive 원장 생성, integrity PASS |
| 구코드 호환 | 현재 운영 구코드 Storage를 별도 module로 불러 **migration 사본에서만** initialize | 기존 데이터 fingerprint 및 integrity 유지 PASS |
| 사본 복구 | 최초 snapshot을 별도 새 사본으로 복구, 기존 데이터와 integrity 재대조 | 동등성 PASS. 운영 DB 덮어쓰기는 아님 |
| 독립 검증 | 별도 Reviewer가 실제 비공개 snapshot/migration/restore 사본을 SSH 읽기로 조회, fingerprint·integrity·source hash 대조 | 제한된 사전 검증 PASS |
| 전체 배포 백업 | 모든 writer 정지 후 설정/workspace/unit/의존성 일관 백업 | **미수행 / BLOCKED**. SQLite 읽기 사본을 전체 rollback checkpoint로 대신하지 않음 |
| 전체 유료 비용 | model/search/agent orchestration/preview/retry/실패 과금의 최악 reservation 및 강제 차단 | 근거 미확보 / **BLOCKED**; [후속 #25](https://github.com/msaltnet/my-nanobot-rpi/issues/25) |
| 배포·실수신 | 고정 후보 배포, smoke, 7일/21회 실수신·중복·유용성 관찰 | **미수행 / BLOCKED** |

### Commands and evidence

실제 비공개 대상/경로를 제외한 실행 명령 일반형:

```text
ssh <designated-target> python3 - <encoded-operating-metadata>
ssh <designated-target> sudo -n python3 - <encoded-operating-metadata>
sqlite3.connect(<existing-db-uri> + "?mode=ro", uri=True)
BEGIN; legacy table SELECT/fingerprint; PRAGMA integrity_check
source.backup(<new-private-snapshot-connection>)
Storage(<isolated-migration-copy>).initialize()  # twice
old_storage.Storage(<isolated-migration-copy>).initialize()
snapshot copy -> separate restore copy -> fingerprint/integrity comparison
```

운영 읽기 점검 종료 코드 0. 최초 비공개 사본 생성은 기존 root 전용 백업 위치의 쓰기 권한으로 **생성 전 종료 코드 1**이었다. 소유자/0700·로그인 사용자·비대화형 sudo를 확인한 뒤 권한을 완화하지 않고 기존 sudo로 새 사본을 생성했으며 검증은 종료 코드 0이다.

첫 예약 조회는 legacy 위치를 보아 실제 뉴스가 없는 것으로 나왔다. 실제 configured workspace의 cron 저장 위치를 재대조해 기존 세 예약을 확인했다. 초기 빈 조회를 예약 부재/장애로 판정하지 않았다.

새 검증 목적 유료 API/Telegram POST·운영 DB app 쓰기·서비스 변경 0. 별도 기존 운영 서비스의 자연 예약/사용량은 이번 검증의 신규 호출 0과 구분하며 전체 사용량 또는 비용 0을 주장하지 않는다. SQLite 읽기 중 SHM 등 bookkeeping byte까지 불변이라고 주장하지 않는다.

## Agent Review Report

별도 `ops_preflight_review`가 실제 사본과 절차를 확인했다. 비공개 접근 제한, 사본 동등성/무결성, 후보 source hash와 기존 테이블 보존을 확인했다. 공개 문서의 정확한 최종 SHA scoped 판정은 PR에 기록한다.

검토 범위 밖은 전체 writer 정지 백업, 후보 runtime 설치/배포, 금액 hard guard, 실제 Telegram 수신·읽음/21회, Human 내용 수용이다. 이 사전 PASS를 전체 운영 AC PASS로 확대하지 않는다.

## AC mapping and result

- AC1–2: 기존 오프라인 근거 유지. 새 실제 수집/선택/검색 관찰은 하지 않았다.
- AC3: 예약 존재·활성 상태만 조회했다. 실행/생성/API ACK/실수신 21개 표본은 **BLOCKED**.
- AC4: 실제 데이터 사본의 보존/호환 근거 추가. 실제 발송·자연 장애 재전송 관찰은 **미수행**.
- AC5: 제품 후보의 독립 Tests/Review·Linux CI 근거는 PR #24. 실제 후보 배포/실사용은 **BLOCKED**.
- AC6: 이번 신규 외부 호출/운영 쓰기·서비스 변경 없이 사전 검증했다. 전체 비용 차단·최신 전체 일관 backup·관찰/최종 수용은 **BLOCKED**.

**제한된 운영 사전 검증 PASS / 전체 #7 운영 검증 BLOCKED.** #25를 조사·설계 Open으로 분리하고 기존 운영 서비스를 유지한다. 비용 상한을 낮춰 주장하거나 기존 counter를 초기화하지 않는다. 새 비용 제어 제품 코드는 별도 승인 전 구현하지 않는다.

## Human Review Handoff

현재 질문을 추가하지 않고 수행 가능한 사전 점검·격리 검증·별도 리뷰를 완료했다. 유료 운영 관찰 재개에는 실제 enforcement 근거 또는 승인된 최소 비용 제어 설계가 필요하다. 전체 DB/workspace 정지 백업과 후보 runtime 적용은 그 조건을 확보한 뒤 v2 절차로 진행한다.

제품 후보·7일 기준·데이터 보존·현재 DB 유지 롤백 정책은 유지한다. 실제 수신/읽음을 Agent가 확인하지 못했으면 미확인으로 남긴다. 후보 병합·Issue 종료는 전체 운영 결과와 수용 조건을 충족한 뒤 수행한다.
