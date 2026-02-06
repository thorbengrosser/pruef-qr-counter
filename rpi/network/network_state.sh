#!/bin/bash
# Network state machine for PRÜF Counter.
#
# IMPORTANT: On Pi Zero 2 W, WiFi and BLE share the same radio (BCM43436S).
# Aggressive WiFi reconnection disrupts BLE operations (display updates).
# This script is intentionally conservative: when WiFi is associated, it does
# NOT try to reconnect even if internet is flaky. Only reconnects when WiFi
# is truly disconnected (no IP on wlan0).
#
# First boot (never connected): aggressive — try every 5s for 30s, then AP.
# After connected once: patient — only reconnect if WiFi drops completely.
# When associated: lightweight check every 30s, no reconnection attempts.
# After AP: keep checking every 60s if a hotspot comes back.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FIRST_BOOT_INTERVAL=5
FIRST_BOOT_TIMEOUT=30
CONNECTED_INTERVAL=30   # check interval when WiFi is up (was 15, increased to reduce radio use)
PATIENCE_TIMEOUT=300     # 5 minutes
AP_RETRY_INTERVAL=60     # check for hotspots while in AP mode
NO_INTERNET_THRESHOLD=10 # consecutive no-internet checks before reconnect attempt

ever_connected=false
in_ap_mode=false
no_internet_count=0

is_wifi_associated() {
  # Check if wlan0 has an IPv4 address (WiFi is associated)
  ip -4 addr show wlan0 2>/dev/null | grep -q "inet " && return 0
  return 1
}

has_internet() {
  # Try multiple methods in parallel — any success means internet is up.
  # Serial fallback took 6s when all failed; parallel takes ~2s max.
  ping -c1 -W2 8.8.8.8 &>/dev/null &
  local p1=$!
  ping -c1 -W2 1.1.1.1 &>/dev/null &
  local p2=$!
  getent hosts pruef.st &>/dev/null &
  local p3=$!
  # Wait for any to succeed (exit 0); if all fail, return 1
  wait $p1 && return 0
  wait $p2 && return 0
  wait $p3 && return 0
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
  if is_wifi_associated; then
    # WiFi is associated (has IP) — do NOT try to reconnect!
    # Reconnecting disrupts the shared WiFi/BLE radio on Pi Zero 2 W.
    if [ "$ever_connected" = false ]; then
      echo "First connection established." >&2
    fi
    ever_connected=true
    if [ "$in_ap_mode" = true ]; then
      stop_ap
    fi

    # Lightweight internet check (no reconnection, just monitoring)
    if has_internet; then
      no_internet_count=0
    else
      no_internet_count=$(( no_internet_count + 1 ))
      if [ "$no_internet_count" -ge "$NO_INTERNET_THRESHOLD" ]; then
        # WiFi associated but no internet for a long time (5+ minutes)
        # This might mean the AP has no upstream — try reconnecting once
        echo "WiFi associated but no internet for ${no_internet_count} checks. Trying reconnect..." >&2
        try_wifi || true
        no_internet_count=0
      fi
    fi
    sleep "$CONNECTED_INTERVAL"

  elif [ "$in_ap_mode" = true ]; then
    # In AP mode — periodically check if a hotspot came back
    if try_wifi; then
      echo "Hotspot found while in AP mode, switching to STA." >&2
      stop_ap
      ever_connected=true
    fi
    sleep "$AP_RETRY_INTERVAL"

  else
    # WiFi completely disconnected (no IP) — try to reconnect
    no_internet_count=0
    if [ "$ever_connected" = true ]; then
      patience="$PATIENCE_TIMEOUT"
    else
      patience="$FIRST_BOOT_TIMEOUT"
    fi
    echo "WiFi disconnected. Trying to reconnect (${patience}s patience)..." >&2
    reconnect_start=$SECONDS
    reconnected=false
    while [ $(( SECONDS - reconnect_start )) -lt "$patience" ]; do
      if try_wifi; then
        echo "Reconnected." >&2
        reconnected=true
        ever_connected=true
        break
      fi
      sleep "$CONNECTED_INTERVAL"
    done
    if [ "$reconnected" = false ]; then
      start_ap
    fi
  fi
done
