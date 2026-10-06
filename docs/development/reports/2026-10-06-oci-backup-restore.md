# OCI 운영 데이터 백업·격리 복구 검증

## Context

- 계약: [Issue #4](https://github.com/msaltnet/my-nanobot-rpi/issues/4)의 R1–R11 및 AC1–AC7.
- 설계·실행 승인: 2026-10-06 KST Human 직접 채팅 “진행해봐”. [승인 기록](https://github.com/msaltnet/my-nanobot-rpi/issues/4#issuecomment-5997402971).
- 브랜치: `codex/issue-4-oci-backup-restore`. 문서 후보의 정확한 SHA와 독립 Tester/Reviewer 판정은 연결 PR의 Tests / Agent Review 기록을 따른다. 이후 문서 변경에는 해당 결과를 재사용하지 않는다.
- 실제 운영 SHA: `4148191789bf7f17dafbc76f7b88ba6c7db9a730`; 실행 전후 동일.
- nanobot SHA: `1bb712d3488915ca4ed9ccc1a93067ff722f5ab9`; 부모와 일치.
- 절차 기준 SHA: `aa7ad13ab1a02611cddb1c2ad1999d6b90af6689`. 서버에 이 문서 후보나 main을 배포하지 않았다.
- 환경: 운영자가 비공개 `.env`로 선택한 OCI Linux 단일 호스트, Python 3.12.3. 실제 운영 데이터 사본을 검사했으며 외부 발송을 검증 목적으로 요청하지 않았다.
- 실행: Implementer `root`. 독립 Tester `tester`, 독립 Reviewer는 PR에 실제 수행자·검증 SHA·판정을 기록한다. 실행 전 별도 `ops_safety_review`가 일회성 절차를 검토했다.
- 실제 주소·SSH 별칭·사용자·원본/복구 절대 경로·설정·DB 내용은 비공개 운영 기록에만 남긴다. 아래 명령은 개인 경로를 제거한 일반형이다.

## Test Report

### 실제 운영 실행 결과

| 시점 | UTC | KST |
|---|---|---|
| writer 정지 시작 | 2026-10-05 15:28:55.937 | 2026-10-06 00:28:55.937 |
| 모든 writer 정지 확인 | 2026-10-05 15:29:11.909 | 2026-10-06 00:29:11.909 |
| 백업·격리 비교 완료 | 2026-10-05 15:29:16.457 | 2026-10-06 00:29:16.457 |
| 원래 운영 상태 재개 확인 | 2026-10-05 15:29:16.909 | 2026-10-06 00:29:16.909 |

정지 시작부터 재개 확인까지 **20.972초**로 승인한 20분 예산 안에 종료했다.
호스트 시간대는 `Etc/UTC`; 내부 뉴스 cron은 `Asia/Seoul`의 07:00·14:00·20:00이며
추가 내부 간격 job과 tracking/watchdog 타이머도 함께 확인했다.
복귀 직전 기록된 내부 cron의 밀린 실행은 0개, 지나간 realtime timer 예약은 0개였다.
oneshot은 자연 종료·inactive를 확인한 뒤 처리했으며 실행 중 발송 작업을 중간 정지하지 않았다.

| 항목 | 결과 |
|---|---|
| 운영 checkout / 의존성 | clean; `pip check` 종료 코드 0 |
| 실제 백업 대상 | 전체 `.nanobot`(config/workspace/memory/sessions/cron/skills/workspace Git 이력), checkout `.env`, 실제 unit/drop-in 원본과 메타데이터 |
| 외부 경로 / symlink | 기본 workspace와 일치, 백업 범위에 별도 실체를 추가해야 하는 symlink 없음 |
| 원본 상태 파일량 / 작업 전 디스크 여유 | 34,405,299 bytes / 37,600,059,392 bytes |
| archive | 34,519,040 bytes; 접근 제한된 전용 경로에 보관 |
| manifest 비교 | 1,152항목, 일반 파일 866개; 파일 내용·종류·권한·소유자·mtime·확장 속성 일치 |
| SQLite | 원본·복구 `integrity_check=ok`; 사용자 테이블 4개의 행 수 일치 |
| 원래·최종 상태 | gateway와 두 timer active/enabled; 두 oneshot inactive/static; 상태 일치 |

archive SHA256: `b13198299f5e129fba66d77e187834bfefb417ff2299c6126f7dfe8a8ba380ad`.

원본 manifest는 정지 구간에 만들었고, 원본 DB 읽기 검사·archive·격리 복구 비교 후에도
원본 파일이 그대로임을 확인했다. 운영 DB sidecar가 없는 상태를 기록했다.
DB는 존재 여부를 먼저 확인하고 `mode=ro`로 열었으며 `immutable=1`은 사용하지 않았다.
archive와 격리 복구 위치는 checkout·운영 workspace 밖의 새 공간이다.
상위 backup/restore 디렉터리는 700, 생성 umask는 077이며 archive는 ACL·전체 xattr·소유자를 보관했다.
복구 파일에는 원본 권한을 유지하되 접근 제한된 복구 루트 밖으로 공개하지 않았다.

### AC별 근거

| AC | 시나리오 / 명령 일반형 | 실제 근거 | 운영 실행 판정 |
|---|---|---|---|
| AC1 | DEPLOY 대조; `systemctl show`; `git rev-parse HEAD`, `git status --porcelain`, `git submodule status --recursive`; `<venv-python> -m pip check`; `timedatectl`, `free -b` | 사용자·checkout·설정·workspace·DB·unit 원본 대조, 버전·자원·일정 확인; 추가 cron/관련 service/프로세스 조사 | PASS |
| AC2 | `systemctl stop <tracking/watchdog timers>` → oneshot inactive 확인 → `systemctl stop <oneshots/gateway>` → unit·process 검사 | 모든 유닛 inactive; command/cwd 및 운영 경로를 쓰기 모드로 연 process FD까지 잔존 writer 없음 확인 | PASS |
| AC3 | `tar --format=pax --acls --xattrs --xattrs-include=* --numeric-owner <sources>`; SHA256·manifest 작성 | 같은 정지 구간의 전체 상태 및 실제 unit 원본 보관; 부분 결과를 완료로 사용하지 않는 guard | PASS |
| AC4 | archive digest 확인 → 빈 격리 경로에 `tar -xpf` → manifest 및 SQLite `mode=ro` 비교 | 1,152항목과 4테이블 일치; 복구 사본에서 app/service/timer 실행 없음 | PASS |
| AC5 | 실패 guard·복귀 절차 검토; 원래 active 유닛만 `systemctl --job-mode=replace start <unit>`; 합성 오류 검사는 독립 Tester 기록 참조 | 정상 경로의 원래 active/enabled 상태 복귀 확인; 실제 운영 장애를 유발한 실패 복귀 실험은 하지 않음 | 정상 복귀 PASS; 합성 검증은 PR 참조 |
| AC6 | 운영 SHA 전후·명령·복구 경로 대조 | 원본 덮어쓰기·코드/패키지 변경·수동 외부 발송·두 번째 gateway 실행 없음 | PASS |
| AC7 | 독립 Tester가 비공개 증거와 격리 사본 직접 검사; Reviewer가 Issue와 후보 diff 검토 | 현재 문서 SHA의 명령·종료 코드·최종 판정은 연결 PR에 기록 | PR의 독립 판정 참조 |

운영 절차 명령은 모두 종료 코드 0이다. 최초 사전 조건 검사에서는 root 권한 검사 프로세스가
설정의 `~`를 root 홈으로 해석하여 **서비스 정지 전에 종료 코드 1로 중단**했다.
대상 서비스 사용자 홈으로 경로를 해석하도록 일회성 절차를 교정하고 재검사한 뒤 실행했다.
저장소 runbook·제품 코드·배포 스크립트는 수정하지 않았다.

### Regression / 실패 대응

- 독립 Tester가 실제 운영 원본을 훼손하지 않고 별도 합성 데이터에서 missing DB 거부·새 파일 무생성, corrupt DB 거부, checksum mismatch 감지, 공백 경로·따옴표 테이블·WAL 데이터의 `mode=ro` 조회를 확인했다. 합성 검사와 실제 운영 데이터 비교를 구분한다.
- 합성 WAL 검사에서 처음에는 모든 sidecar의 바이트 불변을 가정하여 실패했다. 재검사 결과 SHM의 offset 104에서 1바이트 변화가 있었고 DB·WAL digest와 파일 크기는 그대로였다. 이 SHM 변화는 숨기거나 실제 데이터 손상으로 합산하지 않고 별도 결과로 기록한다. 실제 운영 백업 당시에는 sidecar가 없었고 실제 복구 사본은 읽기 검사 후에도 전체 manifest가 일치했다.
- 독립 Tester는 archive·전체 manifest·DB 비교를 직접 재실행하고 현재 운영 SHA·clean checkout·유닛 상태를 조회했다. 현재 읽기 조회 8개와 비공개 기록의 운영 절차 명령 232개는 모두 종료 코드 0이었다. 이미 종료한 writer 정지 구간은 당시의 기록·절차와 비교했으며, 운영 중단을 다시 실행한 것이 아니다.
- 정지 중 검사는 10분 제한 및 SQLite progress handler로 중단할 수 있도록 준비해 운영 복귀 시간을 확보했다. 중단·실패 시 유닛별 복귀를 시도하고 완료하지 못한 백업은 성공으로 표시하지 않는다.
- 재개 전 pending systemd job·Persistent timer·내부 cron의 예약을 검토했다. 원래 inactive였던 oneshot은 수동 실행하지 않았다. 정상 운영 재개의 기존 예약/API 호출 가능성은 Human 승인 범위에 포함된다.
- 제품 pytest는 N/A: 제품 코드·스키마·의존성 변경이 없다. 문서 검증이나 제품 pytest를 실제 백업·복구 증거로 대신하지 않는다.

### Result

OCI 실제 운영 백업·격리 복구·정상 경로의 원래 서비스 상태 복귀를 확인했다.
독립 Tests / Agent Review의 확정 판정과 문서 후보 SHA는 연결 PR의 검증 기록을 따른다.

## Agent Review Report

Reviewer는 Issue 승인 근거·AC, 본 보고서·index·로드맵 diff, 비식별 실행 결과와 독립 Test Report를 확인한다.
실제 Reviewer·현재 SHA·명령·종료 코드·미해결 Critical/Major 여부 및 최종 PASS/FAIL/BLOCKED는 PR에 남긴다.
사전 절차 안전 리뷰를 최종 보고서 SHA의 Agent Review로 대체하지 않는다.

## Human Review Handoff

- 승인된 OCI 대상의 실제 백업·격리 복구 결과와 정상 운영 복귀를 검토한다. 비공개 기록에서 archive·manifest·원본 DB 비교 기준과 소유자/권한을 조회할 수 있다.
- RPi 실제 검증, 후보 코드 배포, 운영 데이터 덮어쓰기/복원·실환경 코드 롤백, 패키지 변경, 수동 Telegram/API smoke는 **미수행**이다.
- 운영 장애를 고의로 유발한 실제 실패 복귀는 미수행이다. 합성 오류 검사·복귀 절차 검토와 성공 경로의 운영 재개를 구분한다.
- 서비스 active 확인은 실제 Telegram 수신이나 뉴스·기록 전체 안정화의 증거가 아니다. 장기 Dogfooding·실사용 수용은 미확인이다.
- 런타임 배포는 문서 PR이므로 N/A. Human PR 검토·결과 수용·명시적 Merge 승인 전에는 병합·Issue Close하지 않는다.
- 이번 OCI 근거를 RPi 검증·두 플랫폼 전체 PASS·0단계 전체 완료로 확대하지 않는다.
