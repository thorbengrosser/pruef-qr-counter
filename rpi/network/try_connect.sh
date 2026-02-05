#!/bin/bash
# Try to connect to primary WiFi, then backup, using nmcli. Reads config from rpi/config.json.
# Exit 0 if connected, non-zero otherwise.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RPI_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="$RPI_DIR/config.json"

if [ ! -f "$CONFIG" ]; then
  echo "No config.json" >&2
  exit 1
fi

get() {
  local key="$1"
  python3 -c "
import json
try:
    with open(r'''$CONFIG''') as f:
        c = json.load(f)
    print((c.get(r'''$key''') or '').strip())
except Exception:
    print('')
" 2>/dev/null
}

SSID1="$(get wifi_ssid)"
PASS1="$(get wifi_pass)"
SSID2="$(get wifi_ssid2)"
PASS2="$(get wifi_pass2)"

if [ -z "$SSID1" ]; then
  echo "No primary WiFi configured" >&2
  exit 1
fi

echo "Trying primary: $SSID1" >&2
if nmcli device wifi connect "$SSID1" password "$PASS1" 2>/dev/null; then
  echo "Connected to $SSID1" >&2
  exit 0
fi

if [ -n "$SSID2" ]; then
  echo "Trying backup: $SSID2" >&2
  if nmcli device wifi connect "$SSID2" password "$PASS2" 2>/dev/null; then
    echo "Connected to $SSID2" >&2
    exit 0
  fi
fi

echo "Connection failed" >&2
exit 1
