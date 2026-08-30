# my-nanobot-rpi 라즈베리파이 배포 가이드

## 현재 운영 대상

현재 운영 서비스는 Raspberry Pi가 아니라 OCI Ubuntu 인스턴스에서 실행한다.

| 항목 | 값 |
|------|----|
| SSH alias | `msalt-oci` |
| 호스트명 | `instance-20251105-0003` |
| 사용자 | `ubuntu` |
| 저장소 | `/home/ubuntu/my-nanobot-rpi` |
| systemd 서비스 | `my-nanobot-rpi` |
| tracking timer | `msalt-tracking-dispatch.timer` |

운영 서버 접속과 기본 상태 확인:

```bash
ssh msalt-oci
cd /home/ubuntu/my-nanobot-rpi
systemctl is-active my-nanobot-rpi
```

이 문서의 Raspberry Pi 설치 절차는 신규 장비 설치용으로 유지한다. 현재 운영 배포와 점검은 위 OCI 대상에서 수행한다.

## 요구사항

- Raspberry Pi 3B+ (1GB RAM)
- Raspberry Pi OS Lite (64-bit 권장)
- Python 3.11+
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

**스크립트 재실행은 안전합니다.** `.env`는 덮어쓰지 않고, 유닛 파일만 새 버전으로 갱신합니다. 단, **이미 실행 중인 서비스는 자동 재시작되지 않으므로** 유닛 변경을 반영하려면 명시적으로:

```bash
sudo systemctl restart my-nanobot-rpi
sudo systemctl restart msalt-tracking-dispatch.timer
sudo systemctl restart my-nanobot-rpi-watchdog.timer
```

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
| `~/.nanobot/workspace/cron/jobs.json` | 07:00/19:00 KST 자동 브리핑 크론 잡 (`${TELEGRAM_USER_ID}` 치환됨) |

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

nanobot 내장 크론이 `~/.nanobot/workspace/cron/jobs.json`을 읽어 평일 07:00/19:00 KST에 `news-briefing` 스킬을 트리거하고, 결과를 텔레그램으로 자동 발송합니다. 별도 systemd 타이머 없이 `my-nanobot-rpi` 프로세스 자체가 처리합니다.

### 잡 확인

```bash
cat ~/.nanobot/workspace/cron/jobs.json
```

`"to": "123456789"` 형태로 숫자 ID가 치환되어 있어야 합니다. `${TELEGRAM_USER_ID}`가 그대로 남아 있으면 `.env`의 `TELEGRAM_USER_ID`가 비어 있었던 것 — `.env`를 고친 뒤 재 seed:

```bash
rm ~/.nanobot/workspace/cron/jobs.json
my-nanobot-rpi doctor
sudo systemctl restart my-nanobot-rpi
```

### 스케줄/메시지 변경

`jobs.json`을 직접 편집하면 됩니다. nanobot이 파일 mtime을 감지해 자동 reload합니다 (서비스 재시작 불필요).

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
cat .env                                # 리포 루트에서 실행
sudo systemctl restart my-nanobot-rpi    # .env 변경 반영
```

### `apt-get update`가 `apt_pkg` 오류로 실패

Ubuntu에서 `deploy/setup-rpi.sh` 실행 중 다음 오류가 나면 `apt-get update` 자체가 아니라
`command-not-found` DB 갱신 훅이 깨진 상태입니다:

```text
ModuleNotFoundError: No module named 'apt_pkg'
E: Problem executing scripts APT::Update::Post-Invoke-Success ...
```

최신 `setup-rpi.sh`는 이 경우 post-update hook을 끄고 자동 재시도합니다. 이미 실패한 장비에서는 최신 변경을 받은 뒤 다시 실행합니다:

```bash
git pull
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
2. 봇 토큰 유효성 확인:
   ```bash
   curl -s https://api.telegram.org/bot<TOKEN>/getMe
   ```
3. `jobs.json`의 `"to"`가 숫자로 치환됐는지 확인

### 이전에 쌓인 `~/.nanobot/` 설정을 리셋하고 싶을 때

다른 nanobot 프로젝트에서 남긴 MCP 서버나 불필요한 설정(예: yfinance)이 에러를 일으킬 수 있습니다. 통째로 초기화:

```bash
sudo systemctl stop my-nanobot-rpi
mv ~/.nanobot ~/.nanobot.bak.$(date +%Y%m%d)
my-nanobot-rpi doctor                        # 깨끗한 msalt 템플릿으로 재 seed
sudo systemctl start my-nanobot-rpi
```

백업(`~/.nanobot.bak.*`)은 며칠 확인 후 `rm -rf`로 삭제.

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
