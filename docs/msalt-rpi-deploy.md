# my-nanobot-rpi RPi / OCI 배포 가이드

업데이트·후보 배포·백업·격리 복구·롤백은 [공통 운영 절차](development/operations-runbook.md)를 따른다.
실제 대상·버전·경로·검증 결과는 [비공개 운영 기록 양식](development/private-operations-record-template.md)에 기록한다.
문서만으로 RPi/OCI 설치·복구 검증을 통과한 것은 아니다.
배포 대상은 `.env.example`의 `DEPLOY_*` 항목을 비공개 `.env`에 채워 지정할 수 있다.
이 값은 운영 대상 기록용이며 앱/설치 스크립트의 자동 배포 기능이 아니다.
변수 대응과 실행 승인 확인은 [대상 지정 절차](development/operations-runbook.md#env로-운영-대상-지정)를 따른다.

## 지원 환경과 설치 경로

이 프로젝트는 Raspberry Pi와 OCI Cloud Instance의 단일 Linux 호스트에서 실행할 수 있다.
운영자는 자신의 장비, 로그인 사용자, 저장소 설치 위치와 연결 방법을 선택한다.
특정 SSH 별칭·호스트명·계정을 사용해야 하는 것은 아니다.

| 항목 | RPi 예시 | OCI 예시 |
|------|----------|----------|
| 장비 | Raspberry Pi 3B+ | Linux Cloud Instance |
| OS | Raspberry Pi OS / Ubuntu | Ubuntu |
| 사용자·저장소 위치 | 운영자가 지정 | 운영자가 지정 |
| 프로세스 관리 | systemd | systemd |

설치 후 공통 상태 확인:

```bash
systemctl is-active my-nanobot-rpi
systemctl list-timers msalt-tracking-dispatch.timer
```

아래 `/home/pi`와 `pi`는 설치 예시다. OCI 등 다른 환경에서는 실제 사용자와 설치 경로를 사용한다.
`deploy/setup-rpi.sh`는 실행한 저장소 위치와 사용자에 맞춰 서비스 설정을 치환한다.
설정·워크스페이스의 기본 위치는 실행 사용자의 `~/.nanobot/`이므로 설치 및 서비스 실행 사용자를 일치시킨다.
실제 서버 주소·코드 버전·설치 경로·서비스 상태·백업 위치는 각 운영자의 비공개 운영 기록에 남긴다.

## 요구사항

- Raspberry Pi 또는 OCI Cloud Instance의 Linux 호스트
- RPi 예시: Raspberry Pi 3B+ (1GB RAM), Raspberry Pi OS Lite / Ubuntu
- OCI 예시: Ubuntu Linux 인스턴스
- Python 3.11+
- 부모 커밋이 지정한 nanobot submodule의 Python 요구 버전과도 호환되어야 함
- 인터넷 연결
- 시스템 시간대 `Asia/Seoul` 권장 (`sudo timedatectl set-timezone Asia/Seoul`)

## 설치 절차

### 1. 저장소 클론

어디에 클론하든 무방합니다. RPi OS 기본 예시:

```bash
cd /home/pi
git clone --recursive https://github.com/msaltnet/my-nanobot-rpi.git
cd my-nanobot-rpi
```

이미 `--recursive` 없이 클론했다면 submodule을 초기화합니다:

```bash
git submodule update --init --recursive
```

Ubuntu 등 다른 사용자/경로여도 됩니다 (예: `/home/ubuntu/my-nanobot-rpi`). setup 스크립트가 실제 경로와 현재 사용자를 자동 탐지해 systemd 유닛에 반영합니다.

이 저장소는 upstream nanobot 프레임워크를 `nanobot/` submodule로 포함합니다. 배포 전 `nanobot/` 디렉터리가 비어 있으면 설치가 실패하므로, 기존 클론에서는 위 submodule 초기화 명령을 먼저 실행하세요.

### 2. 자동 설정 스크립트 실행

최초 설치용 절차다. 스크립트는 swap·시스템 패키지를 변경하고 tracking·watchdog timer를
즉시 활성화한다. 운영 자격증명과 데이터를 복사한 검증 호스트에서 그대로 실행하지 않는다.
RPi/OCI 이미지가 `python3.11`, `python3.11-venv`, `python3.11-dev`를 제공하는지 먼저 확인한다.
RPi는 ARM 의존성 설치·메모리 피크를, OCI는 이미지 패키지와 outbound 연결을 점검한다.
패키지가 없다면 호환 Python을 준비해 아래 수동 설치를 사용한다.

```bash
bash deploy/setup-rpi.sh
```

스크립트가 수행하는 작업:

- swap 1GB 설정 (메모리 부족 방지)
- Python 3.11 설치
- submodule 초기화 (`git submodule update --init --recursive`)
- 가상환경 생성 및 `pip install -e ./nanobot`, `pip install -e .`
- `.env` 파일 생성 (이미 있으면 보존)
- `~/.nanobot` config/workspace/skills/cron seed 및 `tools.exec.path_append` 패치
- `my-nanobot-rpi.service` systemd 등록 + enable (경로/사용자 자동 치환)
- `msalt-tracking-dispatch.timer` 등록 + enable + start (30분 주기)
- `my-nanobot-rpi-watchdog.timer` 등록 + enable + start (텔레그램 채널 watchdog)

스크립트 재실행은 `.env`를 보존하지만 패키지·swap·venv·seed·유닛·timer를 변경합니다.
기존 운영 업데이트는 공통 절차에 따라 백업과 writer 정지 후 진행합니다.
gateway는 자동 재시작하지 않으므로 승인된 변경을 반영하려면 명시적으로:

```bash
sudo systemctl restart my-nanobot-rpi
sudo systemctl restart msalt-tracking-dispatch.timer
sudo systemctl restart my-nanobot-rpi-watchdog.timer
```

최초 설정 전에는 두 timer와 실행 중인 oneshot/gateway를 정지하고,
설정·수신 대상을 확인한 뒤 필요한 서비스만 시작합니다.

### 수동 설치 (RPi / OCI 공통)

실행 사용자 소유 checkout에서 선택한 호환 Python으로 설치합니다.
아래 `python3.11`을 환경의 호환 실행파일로 바꿀 수 있습니다. 기존 운영은 공통 절차의 백업을 먼저 수행합니다.

```bash
git submodule update --init --recursive
python3.11 -m venv .venv
.venv/bin/python -m pip install -e ./nanobot
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip check
```

`.env`를 비공개로 준비하고 `doctor`로 seed한 다음 아래 PATH 관련 절차로
`tools.exec.path_append`를 지정합니다. `doctor`는 파일 동기화·maintenance와 외부 소스 점검을 수행합니다.
`deploy/`의 다섯 service/timer 템플릿에서 gateway/dispatcher `User`, 저장소·venv·환경 파일 경로와
watchdog `ExecStart`를 실제 값으로 치환해 `/etc/systemd/system/`에 설치합니다.
gateway/dispatcher는 같은 실행 사용자 home을 사용해야 합니다. watchdog은 재기동 권한을 가진
기존 root 서비스 구조를 유지합니다. `daemon-reload` 후 설정·smoke를 확인하고 필요한 unit만 enable/start합니다.

## 설정

### .env 파일

리포 루트의 `.env`를 편집합니다. systemd가 `EnvironmentFile`로 자동 로드합니다 (경로는 setup 스크립트가 실제 클론 위치로 치환해 둡니다).

```bash
nano .env     # 예: /home/pi/my-nanobot-rpi/.env, /home/ubuntu/nanobot/.env
```

```env
# 필수
OPENAI_API_KEY=sk-your-actual-key-here
TELEGRAM_BOT_TOKEN=your-actual-bot-token-here
TELEGRAM_USER_ID=123456789

# 선택 (없으면 DuckDuckGo로 fallback)
TAVILY_API_KEY=tvly-...
BRAVE_API_KEY=BSA...
```

**중요**: `TELEGRAM_USER_ID`는 **숫자 ID**여야 합니다. [@userinfobot](https://t.me/userinfobot)에서 `/start` 치면 `Id: 123456789` 형태로 받을 수 있습니다. 핸들(`@msalt_net`)은 동작하지 않습니다.

**웹 검색 provider**: `~/.nanobot/config.json`의 `tools.web.search.provider`에서 선택(`tavily`/`brave`/`duckduckgo`). 해당 provider의 env var 키가 `.env`에 있으면 자동으로 사용됩니다. 한 번에 하나만 활성.

### 최초 기동 및 seed 점검

`my-nanobot-rpi`을 처음 실행하면 `~/.nanobot/` 전체가 msalt 템플릿으로 자동 생성됩니다:

| 경로 | 내용 |
|------|------|
| `~/.nanobot/config.json` | nanobot 기본 설정 (`${OPENAI_API_KEY}` 등 `.env` 참조) |
| `~/.nanobot/workspace/SOUL.md` | 봇 페르소나 |
| `~/.nanobot/workspace/USER.md` | 사용자 프로필 |
| `~/.nanobot/workspace/skills/{news,news-briefing,tracking}/` | msalt 스킬 |
| `~/.nanobot/workspace/cron/jobs.json` | 07:00/14:00/20:00 KST 자동 브리핑 크론 잡 (`${TELEGRAM_USER_ID}` 치환됨) |

점검 커맨드:

```bash
source .venv/bin/activate
my-nanobot-rpi doctor
```

모든 체크에 녹색 ✓가 떠야 정상. 노란색 ⚠가 나오면 `.env`에 `TELEGRAM_USER_ID` 누락 등이 원인일 수 있습니다.

페르소나 커스터마이즈는 seed 이후에:

```bash
nano ~/.nanobot/workspace/SOUL.md
```

## systemd 서비스 관리

### 주요 명령

```bash
sudo systemctl start my-nanobot-rpi       # 시작
sudo systemctl stop my-nanobot-rpi        # 중지
sudo systemctl restart my-nanobot-rpi     # 재시작 (.env 변경 반영)
sudo systemctl status my-nanobot-rpi      # 상태 확인
```

### 로그

```bash
# 실시간 스트림
journalctl -u my-nanobot-rpi -f

# 최근 100줄
journalctl -u my-nanobot-rpi -n 100
```

### 자동 시작

```bash
sudo systemctl enable my-nanobot-rpi      # 부팅 시 자동 시작 (setup-rpi.sh가 이미 수행)
sudo systemctl disable my-nanobot-rpi
```

## 자동 브리핑 (nanobot cron)

nanobot 내장 크론이 `~/.nanobot/workspace/cron/jobs.json`을 읽어 매일 07:00/14:00/20:00 KST에 `news-briefing` 스킬을 트리거하고, 결과를 텔레그램으로 자동 발송합니다. 별도 systemd 타이머 없이 `my-nanobot-rpi` 프로세스 자체가 처리합니다.

### 잡 확인

```bash
cat ~/.nanobot/workspace/cron/jobs.json
```

`"to": "123456789"` 형태로 숫자 ID가 치환되어 있어야 합니다. `${TELEGRAM_USER_ID}`가 남아 있으면
`.env`의 `TELEGRAM_USER_ID`를 비공개로 확인합니다. 기존 jobs 파일을 삭제해 재생성하면
사용자 정의 job과 실행 상태를 잃을 수 있으므로 삭제하지 않습니다.
[공통 백업 절차](development/operations-runbook.md)로 모든 writer를 정지한 뒤 `.env`와
해당 job 목적지를 비공개로 수정하고, 다른 job·실행 상태가 보존됐는지 확인합니다.
기동 시 관리 job의 seed 동기화가 있으므로 후보 코드의 동기화 정책과 최종 목적지도 확인한 뒤
단일 gateway 및 원래 timer 상태로 복귀합니다.

### 스케줄/메시지 변경

nanobot은 `jobs.json`의 mtime 변경을 감지해 reload합니다. 다만 관리 뉴스 job의 schedule/payload는
다음 gateway/doctor의 seed 동기화에서 저장소 템플릿에 맞춰집니다. 직접 수정은 영구 설정으로
보장되지 않습니다. 변경 전 백업·writer 정지 및 사용자 job/state 보존을 확인하고,
지속적인 관리 job 변경은 템플릿 변경 범위와 Human 승인을 별도로 정합니다.

## tracking dispatcher 타이머

`setup-rpi.sh`가 30분 주기 추적 디스패처 타이머(`msalt-tracking-dispatch.timer`)도 함께 등록·활성화합니다. 시각이 도래한 추적 항목과 누락 항목을 텔레그램으로 자동 질문합니다.

### 타이머 상태 확인

```bash
sudo systemctl status msalt-tracking-dispatch.timer
systemctl list-timers msalt-tracking-dispatch.timer
```

### 직전 실행 로그 확인

```bash
journalctl -u msalt-tracking-dispatch.service -n 20
```

### 수동 실행 (디버깅)

```bash
sudo systemctl start msalt-tracking-dispatch.service
```

## 메모리 모니터링

Raspberry Pi 3B+는 RAM이 1GB이므로 메모리 사용량을 주기적으로 확인합니다.

```bash
free -h
htop   # 없으면 sudo apt-get install -y htop
```

## 트러블슈팅

### 환경변수/API 키 문제

서비스 로그에서 인증 오류가 발생하는 경우:

```bash
journalctl -u my-nanobot-rpi -n 50 | grep -i "error\|auth\|key"
# .env는 비공개 편집기로 확인하고 값을 로그·채팅에 출력하지 않습니다.
sudo systemctl restart my-nanobot-rpi    # .env 변경 반영
```

### `apt-get update`가 `apt_pkg` 오류로 실패

Ubuntu에서 `deploy/setup-rpi.sh` 실행 중 다음 오류가 나면 `apt-get update` 자체가 아니라
`command-not-found` DB 갱신 훅이 깨진 상태입니다:

```text
ModuleNotFoundError: No module named 'apt_pkg'
E: Problem executing scripts APT::Update::Post-Invoke-Success ...
```

`setup-rpi.sh`는 이 경우 post-update hook을 끄고 자동 재시도합니다.
최초 설치 실패 장비는 설치 후보 버전을 확인한 뒤 재실행합니다.
기존 운영 업데이트는 임의 `git pull` 대신 공통 절차의 고정 SHA·백업을 사용합니다:

```bash
bash deploy/setup-rpi.sh
```

수동으로 한 번만 우회하려면:

```bash
sudo apt-get \
  -o APT::Update::Post-Invoke::= \
  -o APT::Update::Post-Invoke-Success::= \
  update
```

### 텔레그램 연결 문제

1. `TELEGRAM_USER_ID`가 **숫자**인지 확인 (핸들 불가)
2. 봇 토큰 유효성은 승인된 단일 gateway 연결과 실제 응답으로 확인합니다.
   토큰이 들어간 URL을 셸 명령·로그·공개 보고서에 남기지 않습니다.
3. `jobs.json`의 `"to"`가 숫자로 치환됐는지 확인

### 이전에 쌓인 `~/.nanobot/` 설정을 리셋하고 싶을 때

다른 프로젝트 설정 때문에 오류가 생겨도 `.nanobot` 전체를 즉시 초기화하지 않습니다.
이 디렉터리는 설정뿐 아니라 생활 기록 DB·세션·memory·예약 job을 포함합니다.
[공통 백업·복구 절차](development/operations-runbook.md)에 따라 모든 writer와 두 timer를
정지하고 일관된 백업·격리 복구를 확인한 뒤, 변경할 설정과 데이터 보존 범위를 정합니다.
`doctor`는 seed/maintenance를 수행하므로 백업 전에 실행하지 않습니다.
데이터를 포함한 전체 초기화는 유실 영향과 복원 지점에 대한 별도 Human 승인 후 수행합니다.
기존 백업은 복구 가능성과 보존 정책을 확인하기 전 삭제하지 않습니다.

### swap 관련 문제

서비스가 OOM(Out of Memory)으로 종료되는 경우 swap 크기를 확인합니다:

```bash
swapon --show
free -h
```

`setup-rpi.sh`는 OS를 감지해 swap을 1GB로 설정합니다:

- **Raspberry Pi OS**: `dphys-swapfile` 사용
- **Ubuntu / 일반 Debian**: `/swapfile` + `/etc/fstab` 등록으로 폴백

수동으로 1GB swap을 추가하려면 (Ubuntu 등):

```bash
sudo swapoff -a
sudo rm -f /swapfile
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Raspberry Pi OS에서 `dphys-swapfile`로:

```bash
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### 브리핑 내용이 비어 있음

- RSS 소스 점검: `my-nanobot-rpi doctor`
- 수동 수집: `my-nanobot-rpi news collect`
- 수동 브리핑: `my-nanobot-rpi news briefing morning`

### LLM이 `my-nanobot-rpi tracking ...` 호출 시 `command not found` (exit 127)

봇이 추적 기록을 시도하다 실패하고 다음 같은 에러를 그대로 보여주는 경우:

```
STDERR:
/usr/bin/bash: line 1: my-nanobot-rpi: command not found
Exit code: 127
```

**원인**: nanobot의 exec 도구는 secrets 누출 방지를 위해 LLM이 만든 명령에 부모 프로세스의 PATH를 전달하지 않습니다. 따라서 venv bin이 자식 bash의 PATH에 들어가지 않아 `my-nanobot-rpi` 실행파일을 못 찾습니다.

**해결**: `~/.nanobot/config.json`의 `tools.exec.path_append`에 venv bin 절대경로를 박습니다. 새 배포는 `setup-rpi.sh`가 자동 처리합니다. 이미 설치된 경우 수동으로:

```bash
# 리포 루트에서 실행
.venv/bin/python - <<'PY'
import json
from pathlib import Path
cfg = Path.home() / '.nanobot' / 'config.json'
data = json.loads(cfg.read_text(encoding='utf-8'))
desired = str(Path.cwd() / '.venv' / 'bin')
data.setdefault('tools', {}).setdefault('exec', {})['path_append'] = desired
cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'patched tools.exec.path_append -> {desired}')
PY
sudo systemctl restart my-nanobot-rpi
```

## Watch 알림 후보 배포와 복귀

Watch 관리/저장 기사 평가/알림은 하나의 SQLite DB를 사용한다. 알림은 새 DB에서
기본 **disabled**다. 기존 DB의 enable 값을 반복 초기화가 덮어쓰지 않는다. 실제 운영 DB를
업그레이드하거나 enable/dispatch할 때는 운영자가 단일 Linux 호스트(RPi 또는 OCI), 고정
후보 SHA, 데이터/비용/Telegram 대상·실행 범위와 작업창을 지정하고 승인한다. 특정 SSH
별칭·서버 사용자·경로를 공통 기본값으로 삼지 않는다. 이번 구현은 Watch timer/unit이나
별도 기사 수집을 설치하지 않는다. 중복 gateway/dispatcher/timer가 없는지 확인한다.

배포 전 모든 writer를 정지하거나 SQLite backup API로 일관된 DB·설정·workspace 백업을
확보한다. 이전 SHA, 현재 후보, 비공개 대상/설정, 복원 검증과 롤백 순서를 운영자 기록에
남긴다. `Storage.initialize`의 동일 BEGIN IMMEDIATE 안에서 기존 news/tracking/Watch
행을 보존하고 알림 settings/deliveries/URL/candidate/attempt/audit 테이블을 additive 생성한다.
기존 news ACK/unknown과 생활 기록/Watch 평가·revision/cursor를 확인하며 이력 삭제는 하지
않는다. 구코드 복귀가 additive DB migration 자체를 되돌린다고 가정하지 않는다.

운영 승인을 받기 전에는 알림을 disabled로 유지한다. 승인된 대상 DB에서
`my-nanobot-rpi watch notify status --json`은 상태를 확인하며 외부 호출은 하지 않는다.
`enable|disable --confirm`은 공유 DB 상태를 바꾸므로 명시적으로 승인된 변경이다.
`dispatch --json`은 현재 allowFrom과 TELEGRAM_USER_ID로 허용된 단일 private recipient에
최대 한 메시지를 보낼 수 있다. 기본 실제 UTC 시간을 사용한다. `--now ISO8601
--diagnostic-time`은 승인된 격리 수동 진단에만 쓰고 production 시간/한도 우회에 쓰지 않는다.

recipient별 KST 09:00 이상 21:00 미만, UTC 시간 슬롯당1개/KST 날짜당6개/최대3기사,
메시지3,500자(UTF-16 단위도 제한)를 적용한다. pending/sending/sent/unknown/rejected와
cancelled 슬롯도 일일 quota를 소비한다. 이미 ACK된 URL은 revision 변경으로 재발송하지
않으며 뉴스 브리핑 이력과는 분리된다. 모델을 다시 생성하지 않고 저장한 평가 입력의
제목·URL과 Watch 이유를 결정적으로 표시한다. 전역 FIFO의 saved URL key를 read-only snapshot에서 한 번에100행씩 읽고, 표시 불가능한
앞 항목을 지나 다음 전달 가능한 기사를 찾는다. 고정된 첫100행 prefix로 뒤 기사 전달을
영구 막지 않는다. URL별 현재 Watch의 가장 오래된 이유를 최대20개씩 읽고 선택 그룹은
최대3개만 유지하며, all-backlog 원문 snapshot을 fetchall하지 않는다. 표시 불가능한 중복
URL은 재검사할 수 있으나 보류 URL 전체를 메모리 set으로 모으지 않는다. 더 긴 URL은
쪼개거나 자르지 않는다. 같은 URL/Watch의 여러 이유는 가장 오래된 article/evaluation ID의
snapshot을 사용한다. 어떤 오래된 항목이 새 메시지에는 들어가지만 현재 남은 공간에는
들어가지 않으면 그 항목을 다음 슬롯의 첫 후보로 남기고 더 젊은 기사로 우회하지 않는다.

모든 후보가 표시 불가능하면 전체 backlog를 읽을 수 있어 CPU와 read-snapshot 시간이
늘어난다. BEGIN IMMEDIATE 쓰기 잠금 안에서 이 전체 스캔/formatting을 하지는 않지만,
SQLite DELETE journal의 SHARED reader는 writer COMMIT을 지연시킬 수 있다. 읽기 스냅샷을
닫은 뒤 쓰기 claim은 선택 evaluation 최대60행/URL 최대3개와 slot/day/shared-state만 재검사한다.
어떤 선택 후보의 자격·입력·이유나 URL claim 상태가 달라지면 전체 준비 결과를 버리고
새 quota/claim/POST 없이 다음 invocation에서 새로 읽는다. 스냅샷 읽기 뒤 새로 완료된
더 오래된 article ID의 평가는 다음 invocation에서 본다. FIFO는 이 coherent read snapshot의
전달 가능한 후보 기준이다. Production time은 final claim과 sending의 BEGIN IMMEDIATE를
획득한 뒤 실제 시계로 다시 읽어 hour/day/quiet 경계를 검사한다. 잠금 대기 전 시간을
재사용하지 않는다. 명시적 diagnostic --now는 고정이다.

발송 전에 slot/day/URL claim·payload/candidate snapshot을 commit하고, 마지막 검사를
통과한 뒤 sending과 attempt를 commit한다. 이 commit도 reader 때문에 기다릴 수 있으므로,
commit 반환 후 HTTP 직전에 실제 시계와 저장한 슬롯/KST 시간 창을 다시 검사한다.
이미 경계를 놓쳤다면 POST0으로 unknown/pre_post_window_missed를 보존한다. 결과 저장이
실패하면 unresolved sending으로 남을 수 있으며, 소비한 attempt·URL claim·quota는
반환하지 않고 자동 재시도하지 않는다. 실제 발송이 없었어도 일일 용량을 소비하며
운영자의 근거 기반 확인이 필요할 수 있다. POST 중 DB transaction을 유지하지 않는다.
같은 슬롯 pending은 재시작 후 재개할 수 있다. 다른 슬롯의 pending은 이전 quota를
보존하며 cancelled로 남기고 새 슬롯에서 재구성한다. 최종 검사에서 어떤 후보든 paused,
deleted, revision 변경 또는 global disabled이면 pending batch 전체를 cancelled로 바꾸고
URL claim만 해제한다. 이미 소비한 URL attempt와 quota는 보존한다. sending은 취소/해제하지
않는다. 이 검사가 끝난 직후 pause/disable과 외부 POST 사이의 race는 제거할 수 없으므로
즉시 중지가 이미 진행된 POST의 미수신을 보장한다고 안내하지 않는다.

HTTP2xx와 JSON 객체 `ok is True` 및 양의 message ID를 확인한 경우만 sent다. JSON 객체
`ok is False`는 HTTP 상태와 무관하게 rejected다. timeout/비객체/malformed/불명확한 HTTP
응답/중단/ACK 저장 실패는 unknown 또는 unresolved sending으로 남긴다. dispatcher 시작 시
sending을 unknown으로 보존하고 자동 만료/재시도하지 않는다. status 조회는 recovery를 하지
않는다. disabled 상태의 명시 dispatch도 DB recovery만 하며 외부 호출하지 않는다. 동시 worker
startup이 진행 중 sending을 unknown으로 바꾸더라도 같은 owner의 늦은 ACK만 반영할 수 있고,
operator resolution은 owner를 제거하여 늦은 결과가 결정을 덮어쓰지 못하게 한다.

unknown을 해결하기 전 관련 worker를 정지하고 실제 수신/미수신을 확인한다. operator
`resolve ID --outcome sent --evidence "수신 확인 근거" --message-id ID --confirm`은 POST0으로
receipt/audit만 저장한다. `--outcome retry --evidence "미수신/재시도 근거" --confirm`은 다음
명시적 dispatch의 새 claim을 허용하며 실제 attempt 총2회·새 slot/day quota를 그대로 적용한다.
rejected 자동 추가 시도도 새 슬롯의 단 한 번이며 SDK/transport 자동 retry는 없다. crash가
POST 직전 일어나면 sending 예약을 보수적으로 소비한다. sending을 operator가 직접 취소/해제하지
않는다. raw payload/recipient와 수신 근거는 private DB에만 보존하고 공개 보고서에 싣지 않는다.

복귀는 **notifier disabled → 모든 관련 worker 중지 → 현재 DB/ACK/unknown/attempt ledger를
보존 → 승인된 이전 코드로 복귀 → 상태/기존 기능 확인** 순서다. 원장을 옛 DB 백업으로
덮어쓰면 ACK/unknown claim을 잃어 중복 발송할 수 있으므로 코드 복귀에 그렇게 하지 않는다.
unknown 자동 retry나 ledger 삭제를 복귀 절차에 넣지 않는다. 실제 데이터 복원은 별도 데이터
영향 승인과 일관된 백업/복원 검증이 필요하다.

W11-6은 실제 승인 대상의 수신, 관련성/중요도 표본, 유용성과 알림 부담을 Human이 직접
확인하고 수용해야 한다. 관찰 시간·알림/모델 비용 상한과 중지 수단을 배포 승인에서 정한다.
합성 fixture PASS와 Bot API ACK가 실제 수신/Human 수용/병합 승인을 대신하지 않는다.
