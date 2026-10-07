# R0 공통 배포·검증 준비 — Planning 초안

작성일: 2026-10-05. 상태: **문서 범위 Human 설계 승인 기록 / 상태 라벨 Ready for Implementation**.
계약 본문: [R0 Issue #2](https://github.com/msaltnet/my-nanobot-rpi/issues/2).
GitHub Issue 본문으로 옮기기 위한 보조 자료이며, Ready Issue나 실제 검증 결과를 대체하지 않는다.

## Problem

로드맵 0단계는 후보 SHA의 배포·검수·복구 방법을 요구하지만, 현재 배포 가이드는
설치·기동 중심이며 백업 일관성, 격리 복구, 후보 업데이트와 데이터 복귀 절차가 부족하다.
RPi/OCI의 실제 검증 환경과 미검증 환경을 구분할 기록 형식도 필요하다.

조사 기준 커밋: `867e5aa62cf8e333cd94641b04328b759243bd61`.

- 루트 Python 요구사항은 3.11 이상이다. nanobot은 부모 SHA가 참조하는
  `1bb712d3488915ca4ed9ccc1a93067ff722f5ab9`를 사용한다. 현재 로컬 서브모듈은
  미초기화 상태이므로 nanobot 자체의 Python 호환성·설치를 검증했다고 표시하지 않는다.
- `MsaltConfig`의 기본 DB는 실행 사용자 홈의 `.nanobot/workspace/msalt.db`이다.
  설치 경로를 자유롭게 선택할 수 있다는 사실을 DB 경로 설정 인터페이스가 있다는 뜻으로 해석하지 않는다.
- `deploy/setup-rpi.sh`는 swap·패키지·설정·systemd 유닛을 변경하고
  tracking과 watchdog 타이머를 `enable --now`로 시작한다.
  운영 설정을 복사한 격리 검증 환경에서 그대로 실행하면 발송·재기동 위험이 있다.
- gateway 내부 뉴스 cron, tracking service/timer, watchdog service/timer를 함께 통제해야 한다.
- GitHub 조회에서 열린 Issue #1(Dream 메모리 개선)만 확인했고 열린 PR은 없었다.
  R0는 #1과 별도 범위다. Projects 조회는 `read:project` 권한 부족으로 실패했다.

## Goal / User Experience

운영자는 자신의 Linux 사용자·설치 위치·RPi 또는 OCI 호스트를 선택하고,
현재 버전과 데이터 위치를 확인한 뒤 백업 → 격리 복구 → 후보 업데이트 → smoke →
장애 시 복귀 절차를 수행할 수 있다. 실제 운영 정보는 비공개 기록에 남긴다.
기여자는 Issue 라벨로 승인된 Ready Issue를 조회할 수 있다.

## Requirements

- R1: Python·nanobot SHA·OS/아키텍처·서비스 실행 사용자·설정/DB/workspace 경로를 확인하는 공통 절차를 제공한다.
- R2: RPi와 OCI의 설치·기동·업데이트 차이를 명시하고, 특정 서버 접근을 설치 조건으로 삼지 않는다.
- R3: 설정·workspace·SQLite를 동일한 정지 구간에서 백업한다. DB 외부 경로도 확인한다.
- R4: 운영 데이터와 분리된 복구 공간에서 무결성·내용 보존을 확인한다. 복구 검증은 외부 발송 없이 수행한다.
- R5: 후보 SHA·이전 SHA·submodule·의존성·서비스 설정과 데이터 복귀를 함께 계획한다.
- R6: Telegram 연결과 발송은 승인된 단일 인스턴스만 수행한다.
- R7: 관찰 기준과 플랫폼별 검증 기록 형식을 제공하고, 미실행 항목을 BLOCKED로 남긴다.

## Non-goals

제품 기능·DB 스키마·배포 스크립트 동작 변경, Dream 개선, 새 설정 인터페이스,
자동 배포·예약 Agent·자동 Merge·branch protection은 포함하지 않는다.
Projects 보드는 사용하지 않고 세 Issue 상태 라벨로 관리한다. 서버 접근과 운영 변경은 별도 지정·승인 후 수행한다.

## Design

### Architecture / Components

기존 systemd·gateway cron·tracking 저장소 구조를 유지하며 공통 runbook과
비공개 운영 기록 템플릿을 추가한다. 기존 배포 가이드는 공통 절차로 연결하고
RPi/OCI 차이와 설치 부작용을 명시한다. 런타임·새 의존성·DB 마이그레이션은 없다.

### Data Model / Backup

처음 적용할 백업 방식은 **모든 writer를 정지한 뒤 전체 상태를 보관하는 방식**이다.
SQLite 온라인 backup만으로 다른 workspace 파일과 같은 시점의 스냅샷이 보장되지는 않으므로
온라인 백업은 이번 기본 경로로 선택하지 않는다.

1. 서비스·타이머의 active/enabled 상태, 운영 SHA·submodule SHA, 설치된 의존성을 비공개 기록에 저장한다.
2. tracking·watchdog 타이머를 먼저 정지하고, 실행 중인 각 oneshot 서비스와 gateway를 정지한다.
   수동 CLI·다른 scheduler 등 추가 writer도 확인한다. watchdog이 gateway를 다시 시작하지 않는지 확인한다.
3. 제한된 권한의 백업 공간에 `.env`, nanobot config, 전체 workspace,
   실제 DB 및 필요한 SQLite sidecar, 설치된 유닛과 운영 기록을 보관한다.
   사용자 홈 내 workspace Git 이력·세션·memory도 누락하지 않는다.
4. 원본 경로·파일 목록·권한·체크섬·백업 시각을 기록한다. 비밀 파일 내용을 출력하지 않는다.
5. 백업 완료 또는 실패 시 원래 active/enabled 상태를 기준으로 복원한다.
   실패한 백업으로 후보 업데이트를 계속하지 않는다.

### Restore / Isolation

백업은 별도 디렉터리 또는 분리된 Linux 사용자/호스트에 복원한다.
서비스·타이머를 등록하거나 gateway를 실행하기 전에 운영 토큰·사용자 목적지·cron을 격리한다.
`setup-rpi.sh`는 복구 검증 도구로 사용하지 않는다. `doctor`도 seed와 네트워크 점검이 있어
순수 읽기 검증으로 취급하지 않는다.

우선 복구 사본의 SQLite를 읽기 전용으로 열어 `PRAGMA integrity_check`와
테이블별 행 수를 백업 전 기준과 비교하고, config·workspace의 파일 체크섬을 비교한다.
운영 데이터 사본과 합성 데이터의 검증 결과를 구분한다. 읽기 검증 후 런타임 smoke는
새 테스트 자격증명·분리 데이터 또는 승인된 운영 단일 인스턴스에서만 수행한다.

### Candidate / Rollback

고정 후보 SHA와 해당 submodule을 사용하고 dirty checkout에서 덮어쓰지 않는다.
수동 pull·설치 스크립트 재실행을 후보 검수의 기본 업데이트 방식으로 쓰지 않는다.
gateway와 timer writer를 통제하고 백업한 뒤 의존성 설치·유닛 차이·실행 경로를 확인한다.
정상 기동과 승인 smoke 후 필요한 타이머만 복원한다.

장애 시 발송을 멈추고 실패 시점 데이터를 별도 보관한 뒤 이전 코드·submodule·의존성·설정을 복원한다.
후보 배포 후 기록이 생겼다면 이전 DB 백업 복원에 따른 유실 범위를 먼저 확인한다.
DB/상태 복귀가 필요하면 Human이 수용한 복원 지점으로 복원하고 재발송 가능성을 점검한다.
코드 복귀만으로 마이그레이션이 취소된다고 가정하지 않는다.

### Interface / Integration Points

공개 명령은 운영자가 정한 경로 변수를 사용하며 서버 주소·SSH 별칭·개인 사용자명을 고정하지 않는다.
환경별 가이드는 Debian 계열/systemd 적용 범위, Python 설치 가능 여부,
ARM wheel·메모리/swap·OCI 네트워크 접근 차이를 확인하도록 한다.
현재 설치 스크립트의 swap 변경과 타이머 즉시 활성화는 사전 점검 항목으로 명시한다.

## Implementation Scope

설계 승인 후 문서 변경 순서:

1. `docs/development/operations-runbook.md`: 버전·경로 점검, 백업·격리 복구, 후보 업데이트·복귀, 관찰 기준.
2. `docs/development/private-operations-record-template.md`: 운영자가 저장소 밖에 복사할 비공개 기록 양식.
3. `docs/msalt-rpi-deploy.md`: 공통 절차 연결, RPi/OCI 환경 차이, 설치 부작용과 smoke 구분.
4. `docs/implementation-roadmap.md`: 실제 증거가 확보된 항목만 상태를 갱신한다.

배포 스크립트 변경 필요성이 발견되면 별도 설계/Issue로 다룬다.

## Acceptance Criteria / Test Scenarios

| AC | 기준 | 검증 방법 |
|---|---|---|
| AC1 | 요구 버전·실행 사용자·모든 상태 경로를 확인할 수 있다 | 코드·유닛·submodule과 문서 대조; 실제 호스트 점검 |
| AC2 | RPi/OCI별 설치·기동·업데이트·smoke 순서와 제약이 있다 | 두 환경 각각 실행 결과 또는 미검증 제한 기록 |
| AC3 | 모든 writer가 중지된 구간에 DB·설정·workspace 백업을 확보한다 | 서비스/타이머 상태와 백업 manifest; 백업 실패 시 복귀 시나리오 |
| AC4 | 격리 복구에서 무결성과 내용 보존을 확인한다 | SQLite integrity_check=ok, 행 수·파일 체크섬 비교, 외부 발송 없음 |
| AC5 | 후보·이전 SHA와 데이터 복귀 지점이 명확하다 | 업데이트/롤백 연습; 배포 후 신규 기록 유실·재발송 경계 확인 |
| AC6 | 중복 Telegram 연결·발송을 방지한다 | 운영/검증 인스턴스·token·cron·timer 격리 점검; 승인 smoke 수신 대조 |
| AC7 | 관찰 항목과 검증 한계가 기록된다 | 수집·브리핑 생성/전달·tracking 저장·중복/누락·API 실패·메모리·디스크·비용 기록 |

문서 링크와 명령은 실제 코드에 대조한다. 문서 변경에는 제품 회귀 테스트를 형식적으로 붙이지 않는다.
Linux 실행·복구·Telegram 검증이 없으면 해당 AC는 PASS가 아니다.
테스트·리뷰는 `verification-report-template.md` 형식으로 현재 SHA를 명시한다.

## Observability

시각/시간대, 코드 SHA, 서비스 active 상태, timer 직전/다음 실행,
gateway 연결·오류, 수집/브리핑 결과와 실제 수신, tracking 저장 확인,
중복/누락, API 실패·재시도, RAM/swap·디스크 여유를 기록한다.
호출 비용은 공급자 dashboard/실제 usage 등 확인 가능한 근거만 사용하고
집계 불가능한 항목은 미확인으로 남긴다. 로그 원문·사용자 데이터·키는 공개 보고서에 넣지 않는다.

## Deployment / Dogfooding Plan

이번 문서 PR 자체의 배포·Dogfooding N/A 여부는 Human이 수용한다.
runbook의 실제 검증은 운영자가 선택한 RPi/OCI 대상에서 별도 승인 범위로 진행한다.
승인 기록에는 대상 플랫폼, 후보 SHA, 서비스 중단·백업/복구 영향,
Telegram/API smoke 범위, 실제 데이터 복원 허용 여부를 포함한다.
실제 서버·사용자·경로·backup 위치는 저장소 밖 비공개 기록으로 관리한다.

## Issue 상태 관리

- Human의 “project 보드 없이 진행하자” 지시를 Issue #2에 기록했다.
- Open / Planning / Ready for Implementation 라벨 중 정확히 하나를 사용한다.
- 세 라벨을 실제 생성하고 Issue #2에 Planning을 적용했다. Ready 조회는 정상이며 결과가 비어 있었다.
- 라벨 누락·복수 상태·승인 불일치이면 제품 구현을 시작하지 않는다.
- Ready 전환은 사용자의 “승인할께” 명시 승인 후 완료했다.
  [승인 기록](https://github.com/msaltnet/my-nanobot-rpi/issues/2#issuecomment-5995427906).
  Done 상태·자동 Merge/배포는 추가하지 않는다.

## Design Review / 현재 실행 근거

- Human 요청: “0단계 공통 배포·검증 준비 진행하자”. 준비 조사 근거이며 이 초안 설계의 승인으로 기록하지 않는다.
- Issue 번호: #2. GitHub Issue 본문이 기준이다.
- 현재 상태 라벨: Ready for Implementation 하나. Projects 권한은 요구하지 않는다.
- 실제 수행: 작업 트리 확인(변경 없음), 현재 SHA·submodule 참조 확인,
  로컬 문서·설정·서비스·설치/워치독 스크립트 조사, GitHub Issue/PR 조회.
- 미수행: Linux 설치/기동, 실제 백업/복구, 후보 배포, Telegram/API smoke, PR·Merge.
- 문서 검증: 3f75fb5의 별도 Tester/Reviewer PASS를 확보했다. 보드 없는 변경은 새 SHA에서 재검증한다.
- Human 설계 승인: 위 초안 범위의 Issue 작성과 공통 운영 가이드 보완 요청에
  2026-10-05 사용자가 “승인”이라고 응답했다. 운영 배포·Merge는 포함하지 않는다.
- 다음 결정: 실제 복구 검증 대상과 승인 범위 지정.
