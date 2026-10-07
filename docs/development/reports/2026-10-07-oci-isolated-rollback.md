# OCI 최신 백업·격리 데이터 복귀·합성 tracking 검증

## Context

- 계약: [Issue #6](https://github.com/msaltnet/my-nanobot-rpi/issues/6)의 2026-10-07 **OCI 진행 결정** 및 1–6 단계 부분 실행 승인.
- [Human 승인 기록](https://github.com/msaltnet/my-nanobot-rpi/issues/6#issuecomment-6039174915): OCI에서 현재 운영 버전을 유지하며 최대 20분 정지·최신 백업·운영 재개·외부 통신 없는 격리 복귀와 합성 tracking 검증을 승인했다. 실제 수신·유료 API smoke·24시간 관찰·Merge는 포함하지 않는다.
- 브랜치: `codex/issue-6-oci-validation`. 기준 문서 SHA: `d76da7162790d50d8b94f38f66d6cfdbec93c911`. 보고서 후보의 정확한 Git SHA와 최종 독립 검증 판정은 연결 Issue/PR의 기록을 따른다.
- 고정 운영 SHA: `4148191789bf7f17dafbc76f7b88ba6c7db9a730`; 실행 전·후 및 최종 읽기 조회에서 동일. 실제 nanobot SHA: `1bb712d3488915ca4ed9ccc1a93067ff722f5ab9`; 부모와 일치.
- 환경: 운영자가 비공개 DEPLOY 설정으로 선택한 OCI Linux 단일 호스트, Python 3.12.3. 실제 데이터 사본 검사와 합성 DB 검사를 구분한다. RPi는 이번 실행 제외 / 미검증이다.
- 실행자: `root`. 독립 Tester: 별도 컨텍스트 `ops_test`. 독립 사전 Reviewer: `ops_review`; 최종 보고서 커밋은 별도로 리뷰한다.
- 실행한 일회성 절차 SHA256: `6a2272f2384bcdb086a9ba3ef632759352926a32f21b345e4f2dc1c7d9e3e5fd`. 절차·합성 테스트·원본 증거는 비공개 운영 자료로 보관하며 제품 코드나 배포 프로그램으로 추가하지 않았다.
- 공개 기록에는 서버 주소·SSH 별칭·사용자명·절대 경로·설정/로그/생활 기록 원문을 넣지 않는다. archive와 manifest·상태·명령 결과는 접근 제한된 운영 백업 공간에 있다.

## Test Report

### 실제 실행

| 단계 | UTC | KST |
|---|---|---|
| 정지 절차 시작 | 2026-10-07 14:14:09.607 | 2026-10-07 23:14:09.607 |
| 모든 writer 정지 확인 | 2026-10-07 14:14:46.105 | 2026-10-07 23:14:46.105 |
| 원래 운영 상태 재개 확인 | 2026-10-07 14:14:49.311 | 2026-10-07 23:14:49.311 |

정지 절차 시작부터 원래 상태 재개 확인까지 **39.704초**로 승인한 20분 상한 이내다. 최신 백업 확보 후 운영을 먼저 재개하고, 복구·변경·복귀와 합성 기록은 별도 사본에서 수행했다. #4의 과거 백업을 이번 복원 지점으로 사용하지 않았다.

| 관찰 | 실제 근거 |
|---|---|
| 사전 점검 | clean checkout, 실제 submodule 일치, `pip check` 종료 코드 0, 사용자/home/workspace/DB/유닛 실행 경로 대조 |
| 런타임 배포 판단 | main과 운영 SHA 사이의 변경은 문서·템플릿·`.env.example` 및 저녁 시각 테스트 기대값 정정이다. 제품 코드·의존성·submodule·서비스/예약 템플릿 변경이 없어 운영 버전을 유지했다. 버전 간 업데이트/롤백을 검증한 것은 아니다. |
| 예약/추가 writer | 기본 뉴스 cron과 추가 간격 job, tracking timer의 작업창 확인. user crontab 없음, at 부재와 queue 상태 확인, host cron 및 별도 timer/실행 서비스 조사. timer 정지→oneshot 자연 종료→gateway 정지 후 프로세스 cwd와 쓰기 FD 검사 |
| 중단 보호 | 앱 예약 초기 최소 600초/정지 진행 중 최소 540초 여유 조건. 실제 후속 검사 horizon 1,096.120초. 240초 작업 예산 및 210초 detached 복구 guard; 부모 PID와 시작 시각으로 재사용 PID 신호 방지. 실제 guard fallback은 발생하지 않았다. |
| 최신 백업 | 전체 `.nanobot`(config/workspace/memory/sessions/cron/skills/workspace Git 이력), checkout `.env`, 실제 unit/drop-in 파일. pax tar로 numeric owner·ACL·전체 xattr 보존; 새 root 소유 mode 700 공간과 umask 077 |
| 크기/manifest | 원본 33,120,347 bytes, archive 35,194,880 bytes. 1,158항목 / 일반 파일 872개. 정지 중 source manifest와 archive 생성 후 원본 manifest 일치 |
| SQLite | 존재 여부 확인 후 `mode=ro`; 원본 integrity=ok, 사용자 테이블 4개. 실제 원본에 SQLite sidecar 없음. 격리 사본 두 곳의 integrity와 테이블별 행 수가 기준과 일치 |
| 실제 격리 복귀 | 첫 사본 DB에 합성 테이블을 만들고 생성 확인→같은 격리 경로에 archive 재복원→전체 파일/메타데이터와 DB 행 수 복귀 및 합성 테이블 부재 확인. 다른 새 사본에서도 독립 복원을 비교. 운영 원본 덮어쓰기는 없음 |
| 합성 tracking | 운영 venv와 고정 코드에서 명시적 별도 `db_path`를 사용해 boolean 항목 add→2026-10-07 true record→1일 summary. DB의 schema/date/boolean/raw 값 및 `1/1`, `100%` 출력 확인. socket 연결/발송 및 sender/session 경로 차단, dispatch 미호출 |
| 원래/최종 상태 | gateway와 두 timer active/enabled, 두 oneshot inactive/static 일치. 재개 이후 읽기 조회에서도 gateway running, timer waiting, 운영 SHA 동일 |

archive SHA256: `7d7b0635cd6355ac8af6aa88fc986b7c331d71e53f6062227d05958ac9e7875e`.

일반 절차 명령 기록 198개는 모두 종료 코드 0이었다. 별도 소유권 탐색의 대체 경로 조회와 복구 함수는 각 private 기록/상태 근거를 따른다. 이 숫자를 모든 복귀 명령의 완전한 개별 감사 기록이라고 확대하지 않는다.

### 설계 판단과 사전 검사 보완

배포판 OS 통계 timer의 10분 주기를 앱의 최소 600초 작업창에 적용하면 실행 가능한 구간이 없으므로, **확인한 무관한 배포판 유지보수 timer만** 별도로 분류했다. timer/triggered service의 package 소유권, 실제 executable·정확한 argv 역할, 환경 파일/변수 및 drop-in을 대조했고 알 수 없는 custom/runtime 관련 실행은 거부한다. 앱 cron/tracking의 600/540초 안전 구간은 유지했다. 이 환경별 일회성 분류를 공통 설치 서버 요구사항으로 추가하지 않았다.

실제 watchdog은 root의 journal 검사 스크립트를 Bash로 실행하는 기존 override를 사용한다. 그 override의 제한된 세 줄과 고정 SHA의 스크립트 내용·effective 실행 형식을 대조하고 원본 파일/메타데이터를 백업했다. root checker를 gateway/tracking 사용자·venv 실행과 동일하다고 가정하지 않았다. 유닛을 수정하지 않았다.

실행 전 초안은 transient unit 상태, watchdog 실행 형식/override, distro PATH 설정, cron 경로 및 OS timer 표시 형식을 사전 조건으로 정확하게 처리하지 못해 정지 전에 중단했다. 실제 환경과 코드 근거를 확인해 교정했고 변경된 절차마다 재검증했다. 잘못된 사전 조건을 우회하거나 운영 중단을 반복한 결과가 아니다.

### 0단계 분류

| 로드맵 항목 | 문서 / 기존 근거 | 이번 OCI 근거 / 남은 제한 |
|---|---|---|
| 개발 문서·템플릿·Issue 상태 | #2/#3 병합, 세 라벨 조회 및 이번 #6 단일 Ready 확인 | 운영/병합 승인을 자동 강제하는 서버 설정은 아님 |
| DEPLOY 지정 | 비공개 설정, runbook 변수 대응 | 실제 사용자/경로/unit 대조; 공개 개인 식별 정보 제외 |
| 공통 운영 요구·버전·경로 | runbook 및 #4/#5 | 현재 SHA/submodule/의존성/서비스·자원 점검; RPi 실환경 미검증 |
| 두 플랫폼 설치·기동·업데이트 | 설치 가이드 | OCI 기존 운영 기동 상태 확인; 신규 설치·RPi·버전 업데이트 smoke 미수행 |
| 일관 백업·격리 복구 | #4 당시 증거 보존 | 새 백업, 같은 격리 사본의 변경→복귀, checksum/metadata/DB 비교 확인 |
| 후보 배포·중복 방지·복귀 | runbook | 런타임 변경 없음으로 배포 필요 없음. 단일 gateway 원래 상태 재개. 운영 DB 교체·실환경 장애/롤백·새 후보 기동 미수행 |
| 관찰 기준 | runbook | 시각·SHA·상태·용량·합성 저장 확인. 실제 수신/생성/알림·API 비용·장기 관찰은 미검증 |

### 원래 Issue AC와 승인된 부분 범위

| AC | 시나리오 / 일반형 명령 | 실제 결과와 제한 | 판정 |
|---|---|---|---|
| AC1 | roadmap/runbook/#4 대조; 위 분류표 | 문서/당시 OCI/현재 OCI/미검증을 구분 | 현재 문서 분류 확인; 전체 0단계 완료 아님 |
| AC2 | 두 SHA 전체 diff, 운영 `git rev-parse HEAD`/submodule/clean | 런타임 변경 없어 현재 SHA 유지; 실제 후보 업데이트 검증 아님 | 승인된 부분 범위 PASS |
| AC3 | Telegram/news/tracking 실제 입력·수신·저장·알림 | 수동 외부 smoke는 미승인/미수행. 합성 CLI로 실제 사용자 흐름을 대신하지 않음 | BLOCKED |
| AC4 | 최신 archive checksum/manifest/ro SQLite; 격리 mutation→동일 사본 restore; 합성 오류 테스트 | 격리 복구/복귀와 실패 방어 통과. 운영 데이터 교체/실환경 장애 복귀는 제외 | 승인된 부분 범위 PASS |
| AC5 | 플랫폼 선택/검증 구분 | Human OCI 선택. RPi 미검증을 그대로 유지 | RPi BLOCKED / 이번 실행 제외 |
| AC6 | 예약/예산/guard/상태 재개/격리 network 차단 | 39.704초, 원래 상태 복귀, 외부 smoke 없음. 실제 수신/24시간 관찰 예산은 이번 승인 아님 | 중단·격리 제어 PASS; 운영 관찰 BLOCKED |
| AC7 | frozen procedure hash, 실제 명령 기록, 독립 Tester/Reviewer, 보고서 후보 SHA | 아래 독립 검사 완료. 최종 문서 SHA 판정은 Issue/PR 기록에서 확인 | 부분 실행 검증 완료; 전체 이슈 완료 아님 |
| AC8 | Human 결과 수용/명시적 병합 승인 | 이번 메시지는 실행 승인이다. 결과 수용·Merge 승인 아님 | BLOCKED |

### Regression / 독립 Tester

`ops_test`는 실행자의 자기 평가를 근거로 삼지 않고 승인 Issue 스냅샷·실제 절차와 private archive/사본을 직접 검사했다.

- Windows Python 3.13.9에서 별도 합성 파일/SQLite·mock systemctl/signal/guard를 사용한 **22개 테스트**, 종료 코드 0, 경고 없음. 오류/예외/timeout에도 유닛별 복귀 시도 지속, 원래 inactive gateway/oneshot 미기동, PID 재사용 신호 차단, 경로 격리·hardlink 거부, checksum 훼손, missing/corrupt DB 거부와 새 DB 무생성, 예산/예약 거부, 실제 workspace cron 경로 및 알 수 없는 timer 거부를 검사했다. 실제 시스템 명령을 mock했다.
- 별도 OCI 읽기 verifier로 archive SHA를 다시 계산하고 두 복원 사본의 전체 manifest·owner/mode/mtime/xattr 및 env/unit 메타데이터를 비교했다. checkpoint된 사본에 WAL이 없거나 비어 있음을 확인한 뒤 `mode=ro&immutable=1`로 integrity/테이블별 행 수 및 합성 테이블 부재를 검사했다. 운영 절차의 원본 DB 검사에는 `immutable=1`을 사용하지 않았다.
- 실제 verifier 종료 코드 0, `PASS_APPROVED_SUBSET_ONLY`. 원래/최종 상태, 모든 기록된 일반 명령의 종료 코드, resumed marker, guard fallback 부재와 합성 명령 범위/값을 확인했다. 운영 서비스 조작이나 데이터 쓰기는 하지 않았다.
- 제품 `python -m pytest tests/msalt/`는 이번 변경에 N/A: 제품 코드·스키마·의존성을 변경하지 않았고 제품 pytest는 systemd·실제 백업/복귀를 검증하지 않는다. 관련 합성 절차 테스트와 실제 읽기 재검증을 수행했다.

### Result

**승인된 OCI 부분 범위 PASS. 전체 Issue #6은 BLOCKED**다. 실제 수신·RPi·운영 관찰·Human 최종 수용은 별도이며 0단계 전체 PASS나 다음 이슈 설계 승인으로 확대하지 않는다.

## Agent Review Report

사전 Reviewer `ops_review`는 승인 Issue와 정확한 절차 digest를 직접 검토했다. 복귀 timeout/부모 identity, 추가 scheduler, 실제 같은 사본의 복귀, 환경/DB 연결 수명과 실제 unit/argv 분류를 교정한 뒤 위 최종 절차에서 Critical/Major 0으로 static PASS를 기록했다.

사전 절차 리뷰는 최종 보고서 Git SHA의 Agent Review를 대신하지 않는다. 최종 Reviewer는 기준 SHA 대비 본 보고서/index diff, 승인 범위, 실제 읽기 재검증·22개 테스트 근거와 공개 자료의 비식별성을 확인하고 Issue/PR에 현재 후보 SHA와 판정을 기록한다. 전체 Issue의 BLOCKED 항목을 승인된 부분 문서 PASS로 숨기지 않는다.

## Human Review Handoff

- 최신 백업·격리 사본 복귀·39.704초 운영 재개 결과를 검토한다. snapshot digest와 private evidence를 대조할 수 있다.
- 이번에 한 복귀는 격리 데이터 사본의 복귀다. 운영 DB 덮어쓰기/실환경 롤백, 후보 배포·다른 버전 호환성 검증을 한 것은 아니다.
- 실제 Telegram 응답·뉴스 실수신·tracking 저장/알림, API/발송 예산·관찰 기간, RPi 및 #7/#8 운영 전제 수용은 남아 있다. 24시간 관찰은 아직 승인·시작하지 않았다.
- 문서 후보 런타임 배포는 N/A. 보고서 검토·결과 수용·명시적 Merge 승인 전 병합/Issue Close하지 않는다. 현재 운영 버전은 그대로 유지한다.