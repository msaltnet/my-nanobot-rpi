#!/usr/bin/env bash
# deploy/check-telegram-channel.sh
# 텔레그램 채널이 timeout으로 좀비 상태인지 검사하고 좀비면 msalt-nanobot을 재시작한다.
#
# 좀비 판정: 최근 LOOKBACK_SEC 안에 'Failed to start channel telegram: Timed out'이
# 마지막 채널 이벤트면 좀비. 그 뒤에 'Telegram bot ... connected'가 있으면 정상.
#
# systemd timer가 5분마다 호출.
set -euo pipefail

LOOKBACK_SEC="${LOOKBACK_SEC:-900}"
SERVICE="msalt-nanobot"
SINCE="${LOOKBACK_SEC} seconds ago"

# 마지막 timeout과 마지막 connected의 timestamp(초) 비교.
last_timeout=$(journalctl -u "${SERVICE}" --since "${SINCE}" --no-pager -o cat 2>/dev/null \
    | grep -F 'Failed to start channel telegram: Timed out' \
    | tail -1 \
    | awk '{print $1" "$2}' \
    | xargs -I{} date -d "{}" +%s 2>/dev/null || true)

last_connected=$(journalctl -u "${SERVICE}" --since "${SINCE}" --no-pager -o cat 2>/dev/null \
    | grep -E 'Telegram bot @[^ ]+ connected' \
    | tail -1 \
    | awk '{print $1" "$2}' \
    | xargs -I{} date -d "{}" +%s 2>/dev/null || true)

# 둘 다 없으면 정상(또는 로그 부족) — 아무 일 없음.
if [ -z "${last_timeout:-}" ]; then
    exit 0
fi

# timeout만 있고 connected가 없으면 좀비.
# 둘 다 있으면 더 최근 쪽으로 판단.
if [ -z "${last_connected:-}" ] || [ "${last_timeout}" -gt "${last_connected}" ]; then
    echo "Telegram channel zombie detected (last_timeout=${last_timeout} last_connected=${last_connected:-none}); restarting ${SERVICE}"
    systemctl restart "${SERVICE}"
    exit 0
fi

exit 0
