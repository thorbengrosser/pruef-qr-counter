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

# Read all WiFi config values in one Python invocation (saves ~1.5s on Pi Zero 2 W)
# Use venv python if available (has cached .pyc, faster startup)
PYTHON="$RPI_DIR/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"
eval "$($PYTHON -c "
import json, shlex
try:
    with open(r'''$CONFIG''') as f:
        c = json.load(f)
    for k in ('wifi_ssid', 'wifi_pass', 'wifi_ssid2', 'wifi_pass2'):
        print(f'{k.upper()}={shlex.quote((c.get(k) or \"\").strip())}')
except Exception:
    for k in ('WIFI_SSID', 'WIFI_PASS', 'WIFI_SSID2', 'WIFI_PASS2'):
        print(f'{k}=')
" 2>/dev/null)"

if [ -z "$WIFI_SSID" ]; then
  echo "No primary WiFi configured" >&2
  exit 1
fi

# Check if already connected to primary or backup SSID (skip reconnect to avoid radio disruption)
CURRENT_SSID=$(nmcli -t -f active,ssid dev wifi 2>/dev/null | grep '^yes:' | cut -d: -f2)
if [ -n "$CURRENT_SSID" ]; then
  if [ "$CURRENT_SSID" = "$WIFI_SSID" ]; then
    echo "Already connected to primary: $WIFI_SSID" >&2
    exit 0
  fi
  if [ -n "$WIFI_SSID2" ] && [ "$CURRENT_SSID" = "$WIFI_SSID2" ]; then
    echo "Already connected to backup: $WIFI_SSID2" >&2
    exit 0
  fi
fi

echo "Trying primary: $WIFI_SSID" >&2
if nmcli device wifi connect "$WIFI_SSID" password "$WIFI_PASS" 2>/dev/null; then
  echo "Connected to $WIFI_SSID" >&2
  exit 0
fi

if [ -n "$WIFI_SSID2" ]; then
  echo "Trying backup: $WIFI_SSID2" >&2
  if nmcli device wifi connect "$WIFI_SSID2" password "$WIFI_PASS2" 2>/dev/null; then
    echo "Connected to $WIFI_SSID2" >&2
    exit 0
  fi
fi

echo "Connection failed" >&2
exit 1
