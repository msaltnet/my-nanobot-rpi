# 비공개 운영 기록 양식

저장소 밖 접근 제한된 위치에 복사해 작성한다. 실제 서버·사용자·경로·데이터는 공개 Issue/PR에
넣지 않는다. 키와 토큰은 양식에도 복사하지 않고 비밀 저장소 참조만 기록한다.
[공통 운영 절차](operations-runbook.md)를 사용한다.

## 대상과 승인

- 기록 시각/시간대, 플랫폼(RPi/OCI), OS/아키텍처/메모리:
- 대상 호스트/연결 방법(비공개), 실행 사용자/home/checkout 실체 경로:
- Issue/PR, 승인 메시지, 승인한 Human:
- 승인 범위: 중단 시간, 백업/복원, 데이터 영향, Telegram/API 호출, 비용:
- 추가 writer/scheduler와 정지 방법:
- 비공개 `.env`의 DEPLOY_PLATFORM/SSH_TARGET/REPO_DIR/RUN_USER/BACKUP_DIR 항목과 실제 대상 일치 확인:
- DEPLOY 항목은 대상 기록이며 실행 승인·앱 자동 배포 설정이 아님을 확인:

## 버전과 경로

- 이전 SHA/submodule SHA, dirty 여부:
- 후보 SHA/submodule SHA:
- Python/nanobot 요구 버전과 설치 버전, pip check 결과:
- 설치 의존성 목록/복원용 lock 또는 wheel 위치:
- `.env`/config/workspace/DB 실제 경로, symlink 대상:
- 세션/memory/cron/skills/workspace Git 이력 위치:
- systemd unit/drop-in 경로·소유자·권한:
- OS/agent timezone, cron과 timer 예약 시각:
- 서비스/timer 원래 active/enabled 상태:

## 백업과 격리 복구

- writer 정지 시작/완료 시각과 확인 근거:
- backup 실체 경로·소유자·모드, 원본과 중첩 없음:
- manifest/체크섬/설정/외부 파일/DB sidecar:
- 원본 DB integrity와 테이블별 행 수:
- 격리 restore 위치/권한, 외부 발송 차단 근거:
- archive digest·복구 파일 digest 비교 결과:
- 복구 DB integrity와 행 수 비교 결과:
- 합성 데이터 / 운영 데이터 사본 구분:
- 실패 시 운영 상태 복원 결과:
- DB 복원 시 기록 유실 범위와 재발송 방지 판단/승인:

## 배포·Smoke·복귀

- 후보 고정 확인, checkout/submodule/의존성/유닛 변경 결과:
- 단일 gateway/Telegram 연결 확인:
- 수집·브리핑 생성·실수신(각각 결과):
- tracking 저장/조회와 dispatch 실제 수신:
- 예정/실제 시각, 중복·누락:
- API 실패/재시도·리소스·비용:
- 재개한 timer와 원래 상태 비교:
- 장애 시점 데이터 보관 위치:
- 이전 코드/설정/데이터 복귀 지점과 실제 연습 결과:
- Human 실제 사용·수용, 미확인 항목:
- Merge 이후 최종 SHA/후보 코드 일치/운영 SHA:

## 공개 보고서로 옮길 결과

플랫폼·검증 SHA·시간대·명령 일반형·종료 코드·AC별 PASS/FAIL/BLOCKED만 정리한다.
미실행은 BLOCKED로 적고 문서 검토·합성 데이터 연습과 실제 운영 검증을 구분한다.
개인 식별 정보, 토큰이 들어간 URL, 로그 원문, 사용자 대화·DB 내용을 제외한다.
