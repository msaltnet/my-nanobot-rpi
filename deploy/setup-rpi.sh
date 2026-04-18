#!/usr/bin/env bash
# deploy/setup-rpi.sh
# Raspberry Pi 3B+ 환경 설정 스크립트
set -euo pipefail

echo "=== msalt-nanobot RPi Setup ==="

# 1. swap 설정 (1GB)
echo "Setting up 1GB swap..."
sudo dphys-swapfile swapoff || true
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# 2. Python 3.11+ 설치
echo "Installing Python 3.11..."
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev

# 3. 프로젝트 설정
echo "Setting up project..."
cd /home/pi/msalt-nanobot
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .

# 4. .env 파일 생성 (사용자가 직접 편집)
if [ ! -f .env ]; then
    cat > .env << 'ENVEOF'
OPENAI_API_KEY=sk-your-key-here
TELEGRAM_BOT_TOKEN=your-bot-token-here
ENVEOF
    echo "Created .env file — edit with your API keys!"
fi

# 5. systemd 서비스 등록
echo "Installing systemd service..."
sudo cp deploy/msalt-nanobot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable msalt-nanobot

# 6. tracking dispatcher timer 등록 (30분 주기)
echo "Installing tracking dispatcher timer..."
sudo cp deploy/msalt-tracking-dispatch.service /etc/systemd/system/
sudo cp deploy/msalt-tracking-dispatch.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now msalt-tracking-dispatch.timer

echo "=== Setup complete! ==="
echo "1. Edit .env with your API keys"
echo "2. Edit ~/.nanobot/config.json (see msalt/nanobot-config.example.json)"
echo "3. Start: sudo systemctl start msalt-nanobot"
echo "4. Logs: journalctl -u msalt-nanobot -f"
echo "5. Tracking timer: systemctl list-timers msalt-tracking-dispatch.timer"
