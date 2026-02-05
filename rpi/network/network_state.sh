#!/bin/bash
# Network state machine: try primary/backup WiFi every 15s; after 8 failures start AP.
# Run as a long-lived script or from a systemd service. Config server runs separately.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INTERVAL=15
FAIL_THRESHOLD=8
fail_count=0

while true; do
  if "$SCRIPT_DIR/try_connect.sh"; then
    fail_count=0
  else
    fail_count=$((fail_count + 1))
    if [ "$fail_count" -ge "$FAIL_THRESHOLD" ]; then
      echo "Repeated failures; starting AP for captive portal." >&2
      "$SCRIPT_DIR/start_ap.sh" || true
      fail_count=0
    fi
  fi
  sleep "$INTERVAL"
done
