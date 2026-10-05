# 공통 배포·백업·검증 절차

[R0 승인 설계](https://github.com/msaltnet/my-nanobot-rpi/issues/2)를 위한 운영 절차다.
RPi/OCI 단일 Linux 호스트에서 운영자가 지정한 사용자·설치 경로를 사용한다.
문서 작성은 실제 설치·복구·배포 검증 결과가 아니다. 결과는
[비공개 기록 양식](private-operations-record-template.md)과
[검증 보고서](verification-report-template.md)에 환경별로 남긴다.

## 요구사항과 환경 차이

| 항목 | 공통 | RPi | OCI |
|---|---|---|---|
| OS | systemd와 Debian 계열 패키지 도구를 사용하는 Linux | Raspberry Pi OS/Ubuntu | Ubuntu 등; 다른 배포판은 수동 설치 |
| Python | 루트 요구사항 3.11+와 후보 nanobot 요구사항의 교집합 | ARM wheel·메모리 부족 확인 | 이미지의 Python 패키지 제공 여부 확인 |
| nanobot | 후보 부모 커밋이 지정한 submodule SHA | 같은 SHA 사용 | 같은 SHA 사용 |
| 자원 | 디스크·RAM·swap 여유 확인 | 저메모리 장비는 설치/기동 피크 확인 | 인스턴스 사양·볼륨 여유 확인 |
| 네트워크 | RSS/검색/LLM/Telegram outbound 연결 | 장비 연결 상태 | egress·DNS·호스트 방화벽 확인 |
| 시간 | OS와 agent timezone·예약 시각 대조 | `Asia/Seoul` 기준 seed 확인 | UTC 이미지 기본값과 seed 차이 확인 |

Python 호환 버전은 upstream 최신 버전이 아니라 후보 submodule의 `pyproject.toml`로 확인한다.
호환 의존성 설치 성공은 `pip check`와 실제 기동까지 확인한다.

## .env로 운영 대상 지정

`.env.example`의 `DEPLOY_*` 항목을 비공개 `.env`에 채워 검증 대상을 기록한다.
앱 설치 필수 설정은 아니며 앱/설치 스크립트가 이 값으로 자동 접속·배포하지 않는다.
운영자 또는 배포 Agent가 해당 값만 비공개로 확인하고, 원격 대상에 접속한 뒤 아래 변수에 대응시킨다.
`.env` 전체를 shell에서 source하거나 내용을 출력하지 않는다. 비밀번호·토큰을 SSH 대상 값에 넣지 않는다.

| .env 항목 | 의미와 운영 절차의 대응 |
|---|---|
| `DEPLOY_PLATFORM` | `rpi` 또는 `oci`; 플랫폼별 점검 기준 선택 |
| `DEPLOY_SSH_TARGET` | 운영자가 정한 SSH 별칭/접속 대상; 접근 방법은 비공개 기록에 보관 |
| `DEPLOY_REPO_DIR` | 대상 호스트 checkout 절대 경로 → 대상 shell의 `REPO_DIR` |
| `DEPLOY_RUN_USER` | 대상 서비스 실행 사용자 → `RUN_USER`; 실제 home은 대상에서 조회 |
| `DEPLOY_BACKUP_DIR` | 대상의 비공개 백업 루트 절대 경로 → `BACKUP_ROOT` |

비어 있거나 대상·경로·사용자가 실제 유닛과 맞지 않으면 접속·백업·업데이트를 진행하지 않는다.
백업 위치는 checkout/workspace와 겹치지 않는 실체 경로여야 한다.
배포 대상 지정은 대상 선택일 뿐 실행 승인이 아니다. 후보 SHA·정지 시간·데이터 영향·
Telegram/API 호출·복구 범위는 Issue/PR의 Human 승인과 별도로 대조한다.
새 설정 인터페이스나 원격 배포 프로그램이 필요해지면 별도 Issue로 설계한다.

## 사전 점검과 경로

아래 값은 실제 운영 환경으로 지정한다. 실행 사용자와 해당 사용자의 홈을 systemd 유닛과 대조한다.
경로 변수는 이 문서의 shell 변수이며 앱에 새 설정 옵션을 추가하는 것이 아니다.
명령 예제는 같은 Bash 세션의 변수 값을 사용한다. 실패하면 즉시 중단하고 원인을 확인한다.
`exit 1`은 현재 shell을 종료하므로 별도 작업용 shell에서 실행한다.

```bash
set -euo pipefail
REPO_DIR='/absolute/path/to/checkout'
RUN_USER='service-user'
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
test -n "$RUN_HOME" && test -d "$REPO_DIR" || { echo 'Invalid home/checkout' >&2; exit 1; }
NANOBOT_DIR="$RUN_HOME/.nanobot"
WORKSPACE_DIR="$NANOBOT_DIR/workspace"
DB_PATH="$WORKSPACE_DIR/msalt.db"
cd "$REPO_DIR"
git status --short
git rev-parse HEAD
git submodule status --recursive
uname -m
cat /etc/os-release
timedatectl
free -h
df -h "$REPO_DIR" "$RUN_HOME"
systemctl show my-nanobot-rpi.service msalt-tracking-dispatch.service \
  -p User -p WorkingDirectory -p FragmentPath
systemctl list-timers --all msalt-tracking-dispatch.timer my-nanobot-rpi-watchdog.timer
```

미초기화(`-`), 부모와 불일치(`+`), 충돌(`U`) 상태의 submodule은 해결하고 진행한다.
`msalt/config.py`와 `msalt/tracking/cli.py`는 실행 사용자 홈을 기준으로 DB를 선택한다.
nanobot config의 workspace를 변경해도 msalt DB/dispatcher workspace가 자동으로 따라가지 않는다.
사용자 정의 구성·symlink·외부 DB가 있으면 실체 경로를 비공개 기록과 백업 대상에 추가한다.
`.env`는 checkout 직하, nanobot config는 위 home 아래가 기본 위치다.
`config.json`, `.env`, cron, unit 환경값과 로그 본문을 공개 보고서에 복사하지 않는다.

## 최초 설치와 기동

RPi는 Raspberry Pi OS/Ubuntu, OCI는 선택한 Ubuntu 이미지에서
`python3.11`·venv·dev 패키지 제공 여부를 사전 확인한다. 제공되지 않으면
환경에 맞는 호환 Python을 준비하는 수동 절차를 선택한다.
[설치 가이드](../msalt-rpi-deploy.md)에 따라 recursive clone하고 실행 사용자로 작업한다.

`setup-rpi.sh`는 swap·apt·venv·설정·systemd를 변경하고 tracking·watchdog timer를 즉시 시작한다.
기존 운영 업데이트·복원이나 운영 자격증명이 있는 복제 호스트에서 실행하지 않는다.
최초 설치용 새 데이터와 자격증명을 사용하고 setup 후 설정 완료까지 두 timer와 service를 정지한다.
gateway가 의도치 않게 시작되지 않았는지도 확인한다.

```bash
set -euo pipefail
sudo systemctl stop msalt-tracking-dispatch.timer my-nanobot-rpi-watchdog.timer
sudo systemctl stop my-nanobot-rpi-watchdog.service msalt-tracking-dispatch.service my-nanobot-rpi.service
"$REPO_DIR/.venv/bin/python" --version
"$REPO_DIR/.venv/bin/python" -m pip check
```

`.env`와 config/cron 목적지를 비공개로 확인한 다음 `doctor`와 gateway를 기동한다.
`doctor`는 seed·스킬 갱신·runtime maintenance·RSS/검색 접속을 수행한다.
종료 코드 0만으로 모든 소스 정상이라고 판단하지 않고 개별 점검 결과를 확인한다.
정상 접속과 승인 smoke 후 운영할 timer만 시작한다.

## 일관된 정지 백업

운영자가 정지 시간과 데이터 영향을 승인한 뒤 실행한다. 다른 scheduler·수동 CLI와
workspace를 변경하는 프로세스도 정지한다. 프로세스가 남으면 진행하지 않는다.
백업 위치는 checkout/workspace 밖, 실체 경로가 겹치지 않고 접근이 제한된 곳을 선택한다.
백업에는 비밀값·개인 데이터가 있으므로 공개 저장소에 보관하지 않는다.

```bash
set -euo pipefail
umask 077
BACKUP_ROOT='/absolute/private/backup-root'
BACKUP_DIR="$BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$BACKUP_DIR" || { echo 'Backup already exists' >&2; exit 1; }
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
for unit in my-nanobot-rpi.service msalt-tracking-dispatch.service \
  msalt-tracking-dispatch.timer my-nanobot-rpi-watchdog.service my-nanobot-rpi-watchdog.timer; do
  printf '%s active=' "$unit"
  systemctl is-active "$unit" || true
  printf '%s enabled=' "$unit"
  systemctl is-enabled "$unit" || true
done > "$BACKUP_DIR/unit-state.txt"
git rev-parse HEAD > "$BACKUP_DIR/previous-sha.txt"
git submodule status --recursive > "$BACKUP_DIR/submodules.txt"
"$REPO_DIR/.venv/bin/python" -m pip freeze > "$BACKUP_DIR/packages.txt"
sudo systemctl stop msalt-tracking-dispatch.timer my-nanobot-rpi-watchdog.timer
sudo systemctl stop my-nanobot-rpi-watchdog.service msalt-tracking-dispatch.service my-nanobot-rpi.service
```

각 유닛이 inactive이고 실행 프로세스가 남지 않았는지 확인한다.
정지 전후 시각과 수동 writer 정지 근거를 기록한다.
기본 `.nanobot` 전체를 저장하고 외부 workspace/DB/symlink 실체도 추가한다.
DB의 `-wal`·`-shm`·`-journal`이 있으면 동일 정지 구간에 포함한다.
실행 중 SQLite 파일 단독 복사를 사용하지 않는다.

```bash
set -euo pipefail
tar -cpf "$BACKUP_DIR/nanobot.tar" -C "$RUN_HOME" .nanobot
cp -p "$REPO_DIR/.env" "$BACKUP_DIR/environment.env"
mkdir "$BACKUP_DIR/units"
for unit in my-nanobot-rpi.service msalt-tracking-dispatch.service \
  msalt-tracking-dispatch.timer my-nanobot-rpi-watchdog.service my-nanobot-rpi-watchdog.timer; do
  sudo systemctl cat "$unit" > "$BACKUP_DIR/units/$unit.txt"
done
find "$NANOBOT_DIR" -type f -exec sha256sum {} + > "$BACKUP_DIR/source-files.sha256"
sha256sum "$BACKUP_DIR/nanobot.tar" "$BACKUP_DIR/environment.env" \
  > "$BACKUP_DIR/archive.sha256"
```

`systemctl cat`은 drop-in을 포함한 복원 참고 자료다. 재설치용 실제 unit/drop-in 파일도
원래 경로·소유자·모드와 함께 별도로 보관한다. symlink 실체·외부 DB/workspace·ACL 등이 있으면
대상별 추가 백업과 복원 방법을 기록한다.
필수 파일을 읽지 못하거나 archive/checksum/DB 검사가 실패하면 백업 실패다.
부분 백업으로 업데이트하지 않고 원래 unit-state에 따라 서비스 상태를 되돌린다.
원래 inactive였던 gateway/timer나 oneshot을 일괄 시작하지 않는다.
oneshot은 중간 정지 시 발송 결과를 확인한 뒤 다음 예약을 재개한다.

아래 읽기 전용 DB 검사로 정지 중 DB integrity와 행 수를 비공개 기록에 저장한다.
격리 복구 비교 기준과 manifest가 확보되면 백업만 수행한 경우 원래 운영 상태로 복귀한다.
후보 업데이트를 계속할 경우 정지를 유지한다.

## 격리 복구와 내용 비교

복구 위치는 운영 경로와 다른 빈 디렉터리를 선택한다. 여기서 app·gateway·doctor·setup·
systemd timer를 실행하지 않는다. 운영 비밀 정보의 접근 제한을 유지한다.
기본 layout 예시:

```bash
set -euo pipefail
RESTORE_ROOT='/absolute/private/restore-check'
test ! -e "$RESTORE_ROOT" || { echo 'Restore path already exists' >&2; exit 1; }
mkdir -m 700 "$RESTORE_ROOT"
sha256sum -c "$BACKUP_DIR/archive.sha256"
tar -xpf "$BACKUP_DIR/nanobot.tar" -C "$RESTORE_ROOT"
```

archive 체크섬은 저장 시 절대 경로를 사용한다. 다른 호스트로 옮겼다면
보관한 digest와 이동한 파일을 대조한다. 복구 후 source manifest의 상대 경로별로
복구 파일 SHA256을 비교하고 외부 실체와 설정 파일도 비교한다.
SQLite 외에 memory·sessions·cron·skills·workspace Git 이력도 검사한다.

아래 코드를 표준 라이브러리 Python으로 실행해 정지 중 원본 DB와 복구 DB 결과를 비교한다.
개별 레코드 내용은 출력하지 않는다. `mode=ro`는 DB가 없을 때 새 파일을 만들지 않는다.
sidecar가 필요한 DB는 복구 공간 권한도 유지하고 WAL을 무시하는 `immutable=1`을 사용하지 않는다.

```bash
python3 - "$DB_PATH" <<'PY'
import json, sqlite3, sys
from pathlib import Path
path = Path(sys.argv[1]).resolve(strict=True)
with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
    integrity = [row[0] for row in conn.execute('PRAGMA integrity_check')]
    if integrity != ['ok']:
        raise SystemExit('integrity_check failed')
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    counts = {name: conn.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
              for name in tables}
    print(json.dumps({'integrity': integrity, 'counts': counts}, sort_keys=True))
PY
```

같은 코드의 인자를 `"$RESTORE_ROOT/.nanobot/workspace/msalt.db"`로 바꿔 비교한다.
운영 DB가 없는 신규 환경은 DB 복구 확인 완료라고 하지 않고 N/A와 근거를 기록한다.
합성 DB 연습은 합성 데이터라고 명시하고 운영 데이터 복구 결과를 대체하지 않는다.

실행을 동반한 검증은 별도 Linux 사용자/호스트와 독립 자격증명·데이터를 준비한다.
복구한 운영 토큰과 목적지를 사용하지 않고 cron/timer 활성화 전 발송 대상을 확인한다.
같은 bot token의 gateway 두 개를 시작하지 않는다. 복사 데이터의 예약 job을 꺼도
기동 seed로 동기화될 수 있어 실행 시 격리를 설정 편집에만 의존하지 않는다.

## 후보 SHA 업데이트

Human이 지정한 대상·후보 SHA·정지/발송/API 호출 범위에서 수행한다.
dirty checkout과 submodule을 보존하고 위 백업·복구 검사 후 정지를 유지한다.

```bash
set -euo pipefail
CANDIDATE_SHA='approved-full-commit-sha'
cd "$REPO_DIR"
test -z "$(git status --porcelain)" || { echo 'Dirty checkout; stop' >&2; exit 1; }
git fetch origin
git cat-file -e "$CANDIDATE_SHA^{commit}"
git checkout --detach "$CANDIDATE_SHA"
git submodule update --init --recursive
"$REPO_DIR/.venv/bin/python" -m pip install -e "$REPO_DIR/nanobot"
"$REPO_DIR/.venv/bin/python" -m pip install -e "$REPO_DIR"
"$REPO_DIR/.venv/bin/python" -m pip check
git rev-parse HEAD
git submodule status --recursive
```

의존성은 이전 버전 목록과 복원 가능한 wheel/lock 등을 확보한다.
`pip freeze`만으로 이후 완전한 재설치를 보장할 수 없다.
유닛 변경이 있으면 실행 사용자·working directory·venv/환경 파일·drop-in을 대조해
환경에 맞게 설치하고 `daemon-reload`한다. 기존 운영에서는 setup 전체를 재실행하지 않는다.
기동 시 maintenance와 스킬/cron 동기화가 있으므로 gateway/doctor 전에 백업한다.
후보의 데이터 변경을 Issue 승인 설계와 대조하고 알 수 없는 변경이 있으면 중지한다.

## Smoke와 관찰

gateway를 단일 인스턴스로 시작하고 watchdog/tracking timer는 정지를 유지한다.

```bash
set -euo pipefail
sudo systemctl start my-nanobot-rpi.service
systemctl is-active my-nanobot-rpi.service
systemctl show my-nanobot-rpi.service -p MainPID -p NRestarts
journalctl -u my-nanobot-rpi.service --since '10 minutes ago' --no-pager
free -h
df -h "$REPO_DIR" "$RUN_HOME"
```

로그는 비공개로 확인하고 공개 시 비밀값·개인 정보를 제외한다. 승인 범위에서 다음을 확인한다.

| 관찰 | 성공 근거와 주의점 |
|---|---|
| Telegram | 단일 접속과 1회 왕복 실제 수신; service active만으로 미확인 |
| 뉴스 | 소스별 수집 결과, 생성과 실제 수신을 구분 |
| 수동 CLI | `news collect`는 외부 통신/DB 쓰기, `news briefing morning`은 생성·이력 쓰기를 동반하며 Telegram 수신을 증명하지 않음 |
| tracking | 합성 항목으로 기록→목록/summary 확인; CLI list도 초기화/seed하므로 순수 읽기가 아님 |
| dispatch | 수동 oneshot은 실제 발송을 동반; 필요한 승인 범위에서만 실행 |
| 중복/누락 | 예정 시각·job/대상·생성/발송/수신을 비공개로 대조; timer `Persistent=true`의 밀린 실행 주의 |
| API 실패 | 인증/timeout/제한 구분; 실패/재시도가 자동으로 안전하다고 가정하지 않음 |
| 자원 | RAM/swap, OOM, 재기동 횟수, 디스크와 백업 용량 |
| 비용 | 실제 usage/dashboard 등 확인 범위; 불명확하면 미확인 |

성공 후 정지 전에 active였던 승인 timer만 되돌린다. 뉴스 cron은 gateway 내부에 있으므로
예약 시각을 지나는 smoke는 자동 발송까지 승인 범위에 포함한다.
매일/주간 기능의 실제 사용 기간은 Issue별로 정하고 미관찰 예약 실행을 PASS로 표시하지 않는다.

## 장애 시 복귀

1. 두 timer, 두 oneshot, gateway와 추가 writer를 정지한다.
2. 실패 시점 DB/workspace를 별도 접근 제한된 저장 위치에 보관한다.
3. 이전 SHA/submodule·의존성·설정·유닛을 복원한다. 이전 코드가 새 DB를 읽을 수 있는지 확인한다.
4. DB 복원이 필요하면 백업 이후 기록 유실과 재발송 가능성을 Human에게 확인한다.
   코드 복귀만으로 DB 마이그레이션이 취소되지 않는다. 백업 시점·운영 재개 시점을 기록한다.
5. 운영 DB 위에 파일을 덮어 겹치지 않는다. 정지 상태에서 현재 상태를 먼저 보관하고,
   선택한 백업의 DB와 sidecar·설정/workspace를 원래 실체 경로에 복원해 소유자·권한을 되돌린다.
   백업에 없던 새 sidecar를 남겨 이전 DB와 섞지 않는다.
6. DB integrity/행 수·상태 파일, 이전 SHA/submodule, pip check를 확인한다.
7. 단일 gateway의 승인 smoke 후 원래 timer 상태를 복원한다. 이상이 남으면 정지를 유지하고 보고한다.

실패 시점의 새 기록을 단순 DB 병합으로 다시 넣지 않는다. 복구 방침·중복 억제 방법을 별도로 확인한다.
PR Merge 후 squash/rebase의 최종 SHA와 후보 코드 일치, 운영 버전과 필요한 최종 배포를 확인한다.
