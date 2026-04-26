#!/usr/bin/env bash
# deploy/setup-rpi.sh
# Raspberry Pi 3B+ 환경 설정 스크립트
set -euo pipefail

echo "=== msalt-nanobot RPi Setup ==="

# 0. 경로/사용자 자동 탐지
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_USER="${SUDO_USER:-$USER}"
echo "  repo dir : ${REPO_DIR}"
echo "  run user : ${RUN_USER}"

# 1. swap 설정 (1GB)
# RPi OS면 dphys-swapfile, 그 외(Ubuntu 등)는 /swapfile 방식으로 폴백.
echo "Setting up 1GB swap..."
if command -v dphys-swapfile >/dev/null 2>&1; then
    echo "  using dphys-swapfile (Raspberry Pi OS)"
    sudo dphys-swapfile swapoff || true
    sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon
else
    echo "  using /swapfile (generic Debian/Ubuntu)"
    CUR_SWAP_KB=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
    if [ "${CUR_SWAP_KB:-0}" -lt 1000000 ]; then
        sudo swapoff -a || true
        sudo rm -f /swapfile
        sudo fallocate -l 1G /swapfile
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
        sudo swapon /swapfile
        if ! grep -q '^/swapfile' /etc/fstab; then
            echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
        fi
    else
        echo "  swap already >= 1GB, skipping"
    fi
fi

# 2. Python 3.11+ 설치
echo "Installing Python 3.11..."
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev

# 3. 프로젝트 설정
echo "Setting up project..."
cd "${REPO_DIR}"
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .

# 4. .env 파일 생성 (사용자가 직접 편집)
if [ ! -f .env ]; then
    cat > .env << 'ENVEOF'
# 필수
OPENAI_API_KEY=sk-your-key-here
TELEGRAM_BOT_TOKEN=your-bot-token-here
TELEGRAM_USER_ID=your-telegram-user-id-numeric

# 선택 — 웹 검색 provider (~/.nanobot/config.json의 provider와 매칭되는 키만 사용됨)
#TAVILY_API_KEY=tvly-...
#BRAVE_API_KEY=BSA...
ENVEOF
    echo "Created .env file — edit with your API keys!"
else
    echo ".env already exists — preserved. If .env.example added new keys, copy them manually."
fi

# 5. systemd 유닛 설치 (경로/사용자 템플릿 치환)
install_unit() {
    local src="$1"
    local name
    name="$(basename "${src}")"
    local tmp
    tmp="$(mktemp)"
    sed \
        -e "s|^User=.*|User=${RUN_USER}|" \
        -e "s|/home/pi/msalt-nanobot|${REPO_DIR}|g" \
        "${src}" > "${tmp}"
    sudo install -m 0644 "${tmp}" "/etc/systemd/system/${name}"
    rm -f "${tmp}"
}

echo "Installing systemd service..."
install_unit "${REPO_DIR}/deploy/msalt-nanobot.service"
sudo systemctl daemon-reload
sudo systemctl enable msalt-nanobot

# 6. tracking dispatcher timer 등록 (30분 주기)
echo "Installing tracking dispatcher timer..."
install_unit "${REPO_DIR}/deploy/msalt-tracking-dispatch.service"
install_unit "${REPO_DIR}/deploy/msalt-tracking-dispatch.timer"
sudo systemctl daemon-reload
sudo systemctl enable --now msalt-tracking-dispatch.timer

# 7. telegram 채널 좀비 watchdog (5분 주기)
echo "Installing telegram channel watchdog..."
chmod +x "${REPO_DIR}/deploy/check-telegram-channel.sh"
install_unit "${REPO_DIR}/deploy/msalt-nanobot-watchdog.service"
install_unit "${REPO_DIR}/deploy/msalt-nanobot-watchdog.timer"
sudo systemctl daemon-reload
sudo systemctl enable --now msalt-nanobot-watchdog.timer

echo "=== Setup complete! ==="
echo "1. Edit .env with your API keys (TELEGRAM_USER_ID must be numeric)"
echo "2. msalt-nanobot doctor  # verify env, auto-seed config/workspace/skills/cron"
echo "3. sudo systemctl start msalt-nanobot"
echo "4. journalctl -u msalt-nanobot -f"
echo "5. systemctl list-timers msalt-tracking-dispatch.timer"
echo ""
echo "Re-running this script on an existing install:"
echo "  .env is preserved, unit files are refreshed, but running services"
echo "  keep the old definition. Apply unit changes with:"
echo "    sudo systemctl restart msalt-nanobot"
echo "    sudo systemctl restart msalt-tracking-dispatch.timer"
