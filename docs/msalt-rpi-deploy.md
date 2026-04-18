# msalt-nanobot 라즈베리파이 배포 가이드

## 요구사항

- Raspberry Pi 3B+
- Raspberry Pi OS Lite (64-bit 권장)
- Python 3.11+
- 인터넷 연결

## 설치 절차

### 1. 저장소 클론

```bash
cd /home/pi
git clone https://github.com/msaltnet/nanobot.git msalt-nanobot
cd msalt-nanobot
```

### 2. 자동 설정 스크립트 실행

```bash
bash deploy/setup-rpi.sh
```

스크립트가 다음 작업을 자동으로 수행합니다:

- swap 1GB 설정 (메모리 부족 방지)
- Python 3.11 설치
- 가상환경 생성 및 패키지 설치
- `.env` 파일 생성 (초기 템플릿)
- systemd 서비스 등록 및 자동 시작 설정

## 설정

### .env 파일

스크립트 실행 후 `/home/pi/msalt-nanobot/.env` 파일을 편집합니다:

```bash
nano /home/pi/msalt-nanobot/.env
```

```env
OPENAI_API_KEY=sk-your-actual-key-here
TELEGRAM_BOT_TOKEN=your-actual-bot-token-here
TELEGRAM_USER_ID=your-telegram-user-id
YOUTUBE_API_KEY=your-youtube-api-key-here
```

### config.json 설정

nanobot 설정 파일은 `.env` 값을 자동 참조하므로 편집이 불필요합니다:

```bash
mkdir -p ~/.nanobot
cp msalt/nanobot-config.example.json ~/.nanobot/config.json
```

### workspace 사전 세팅

봇 페르소나(`SOUL.md`)와 사용자 정보(`USER.md`) 템플릿을 workspace에 복사합니다:

```bash
mkdir -p ~/.nanobot/workspace
cp msalt/workspace/SOUL.md ~/.nanobot/workspace/SOUL.md
cp msalt/workspace/USER.md ~/.nanobot/workspace/USER.md
```

이 파일들은 첫 실행 시 시스템 프롬프트에 주입되며, 이후 대화를 통해 `dream` 시스템이 자동으로 업데이트합니다. 페르소나를 커스터마이즈하려면 복사 후 편집하세요:

```bash
nano ~/.nanobot/workspace/SOUL.md
```

## systemd 서비스 관리

### 서비스 시작

```bash
sudo systemctl start msalt-nanobot
```

### 서비스 중지

```bash
sudo systemctl stop msalt-nanobot
```

### 서비스 재시작

```bash
sudo systemctl restart msalt-nanobot
```

### 서비스 상태 확인

```bash
sudo systemctl status msalt-nanobot
```

### 로그 확인

```bash
# 실시간 로그 스트림
journalctl -u msalt-nanobot -f

# 최근 100줄
journalctl -u msalt-nanobot -n 100
```

### 자동 시작 활성화/비활성화

```bash
# 부팅 시 자동 시작 활성화
sudo systemctl enable msalt-nanobot

# 부팅 시 자동 시작 비활성화
sudo systemctl disable msalt-nanobot
```

## tracking dispatcher 타이머

`setup-rpi.sh`가 30분 주기 추적 디스패처 타이머(`msalt-tracking-dispatch.timer`)도 함께 등록·활성화합니다. 시각이 도래한 항목과 누락 항목을 텔레그램으로 자동 질문합니다.

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

### 메모리 현황 확인

```bash
free -h
```

출력 예시:

```
               total        used        free      shared  buff/cache   available
Mem:           927Mi       450Mi       100Mi        20Mi       376Mi       457Mi
Swap:          1.0Gi        50Mi       974Mi
```

### 상세 프로세스 모니터링

```bash
htop
```

htop이 없는 경우 설치:

```bash
sudo apt-get install -y htop
```

## 트러블슈팅

### swap 관련 문제

서비스가 OOM(Out of Memory)으로 종료되는 경우 swap 크기를 확인합니다:

```bash
swapon --show
```

swap이 비활성화된 경우 수동으로 설정:

```bash
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### API 키 문제

서비스 로그에서 인증 오류가 발생하는 경우:

```bash
journalctl -u msalt-nanobot -n 50 | grep -i "error\|auth\|key"
```

`.env` 파일의 API 키가 올바른지 확인합니다:

```bash
cat /home/pi/msalt-nanobot/.env
```

서비스 재시작으로 변경된 환경변수 적용:

```bash
sudo systemctl restart msalt-nanobot
```

### 텔레그램 연결 문제

봇이 메시지에 응답하지 않는 경우:

1. 봇 토큰이 올바른지 확인합니다.
2. 네트워크 연결 상태를 확인합니다:

```bash
curl -s https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

3. 서비스 로그에서 텔레그램 관련 오류를 확인합니다:

```bash
journalctl -u msalt-nanobot -f
```

4. allowed_users 설정에 본인의 텔레그램 username이 포함되어 있는지 확인합니다.
