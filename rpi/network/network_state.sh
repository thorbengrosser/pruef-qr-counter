#!/bin/bash
# Network state machine for PRÜF Counter.
#
# First boot (never connected): aggressive — try every 5s for 30s, then AP.
# After connected once: patient — try every 15s for 5 minutes before AP.
# When connected: do nothing (lightweight check every 15s).
# After AP: keep checking every 60s if a hotspot comes back.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FIRST_BOOT_INTERVAL=5
FIRST_BOOT_TIMEOUT=30
NORMAL_INTERVAL=15
PATIENCE_TIMEOUT=300   # 5 minutes
AP_RETRY_INTERVAL=60   # check for hotspots while in AP mode

ever_connected=false
in_ap_mode=false

is_connected() {
  ip -4 addr show wlan0 2>/dev/null | grep -q "inet " && return 0
  return 1
}

has_internet() {
  ping -c1 -W2 8.8.8.8 &>/dev/null && return 0
  return 1
}

start_ap() {
  echo "Starting AP for captive portal." >&2
  "$SCRIPT_DIR/start_ap.sh" || true
  in_ap_mode=true
}

stop_ap() {
  if [ "$in_ap_mode" = true ]; then
    echo "Stopping AP, switching to STA." >&2
    nmcli connection down pruf-ap 2>/dev/null || true
    in_ap_mode=false
  fi
}

try_wifi() {
  "$SCRIPT_DIR/try_connect.sh" 2>&1
}

# ── Phase 1: First boot ─────────────────────────────────────────────
echo "First boot: trying to connect (${FIRST_BOOT_TIMEOUT}s window)..." >&2
start_time=$SECONDS
while [ $(( SECONDS - start_time )) -lt "$FIRST_BOOT_TIMEOUT" ]; do
  if try_wifi; then
    echo "Connected on first boot." >&2
    ever_connected=true
    break
  fi
  sleep "$FIRST_BOOT_INTERVAL"
done

if [ "$ever_connected" = false ]; then
  echo "First boot: no connection after ${FIRST_BOOT_TIMEOUT}s." >&2
  start_ap
fi

# ── Phase 2: Main loop ──────────────────────────────────────────────
while true; do
  if is_connected && has_internet; then
    # Online — reset state
    if [ "$ever_connected" = false ]; then
      echo "First connection established." >&2
    fi
    ever_connected=true
    if [ "$in_ap_mode" = true ]; then
      stop_ap
    fi
    sleep "$NORMAL_INTERVAL"

  elif [ "$in_ap_mode" = true ]; then
    # In AP mode — periodically check if a hotspot came back
    if try_wifi; then
      echo "Hotspot found while in AP mode, switching to STA." >&2
      stop_ap
      ever_connected=true
    fi
    sleep "$AP_RETRY_INTERVAL"

  else
    # Disconnected — try to reconnect with patience
    if [ "$ever_connected" = true ]; then
      patience="$PATIENCE_TIMEOUT"
    else
      patience="$FIRST_BOOT_TIMEOUT"
    fi
    echo "Disconnected. Trying to reconnect (${patience}s patience)..." >&2
    reconnect_start=$SECONDS
    reconnected=false
    while [ $(( SECONDS - reconnect_start )) -lt "$patience" ]; do
      if try_wifi; then
        echo "Reconnected." >&2
        reconnected=true
        ever_connected=true
        break
      fi
      sleep "$NORMAL_INTERVAL"
    done
    if [ "$reconnected" = false ]; then
      start_ap
    fi
  fi
done
