#!/bin/bash
# Try to connect to primary WiFi, then backup, then WiFi 3, using nmcli. Reads config from rpi/config.json.
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
    for k in ('wifi_ssid', 'wifi_pass', 'wifi_ssid2', 'wifi_pass2', 'wifi_ssid3', 'wifi_pass3'):
        print(f'{k.upper()}={shlex.quote((c.get(k) or \"\").strip())}')
except Exception:
    for k in ('WIFI_SSID', 'WIFI_PASS', 'WIFI_SSID2', 'WIFI_PASS2', 'WIFI_SSID3', 'WIFI_PASS3'):
        print(f'{k}=')
" 2>/dev/null)"

if [ -z "$WIFI_SSID" ]; then
  echo "No primary WiFi configured" >&2
  exit 1
fi

# Sync NetworkManager profiles from config.json so they win on boot.
# Without this, NM's other saved connections (e.g. from initial Pi setup) often have
# equal/higher autoconnect-priority and get chosen first on reboot.
sync_nm_profile() {
  local ssid="$1" pass="$2" priority="$3"
  [ -n "$ssid" ] || return 0
  if nmcli connection show "$ssid" &>/dev/null; then
    nmcli connection modify "$ssid" connection.autoconnect yes connection.autoconnect-priority "$priority" 2>/dev/null || true
    nmcli connection modify "$ssid" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$pass" 2>/dev/null || true
  else
    nmcli connection add type wifi ifname wlan0 con-name "$ssid" ssid "$ssid" 2>/dev/null && \
    nmcli connection modify "$ssid" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$pass" connection.autoconnect yes connection.autoconnect-priority "$priority" 2>/dev/null || true
  fi
}
sync_nm_profile "$WIFI_SSID" "$WIFI_PASS" 100
sync_nm_profile "$WIFI_SSID2" "$WIFI_PASS2" 50
sync_nm_profile "$WIFI_SSID3" "$WIFI_PASS3" 25

# Check if already connected to primary, backup, or WiFi 3 (skip reconnect to avoid radio disruption)
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
  if [ -n "$WIFI_SSID3" ] && [ "$CURRENT_SSID" = "$WIFI_SSID3" ]; then
    echo "Already connected to WiFi 3: $WIFI_SSID3" >&2
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

if [ -n "$WIFI_SSID3" ]; then
  echo "Trying WiFi 3: $WIFI_SSID3" >&2
  if nmcli device wifi connect "$WIFI_SSID3" password "$WIFI_PASS3" 2>/dev/null; then
    echo "Connected to $WIFI_SSID3" >&2
    exit 0
  fi
fi

echo "Connection failed" >&2
exit 1
