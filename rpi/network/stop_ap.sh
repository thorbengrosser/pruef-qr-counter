#!/bin/bash
# Bring down AP and optionally try STA again.

CON_NAME="${PRUF_AP_NAME:-pruf-ap}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

nmcli connection down "$CON_NAME" 2>/dev/null || true
echo "AP down." >&2
# Optionally try STA
"$SCRIPT_DIR/try_connect.sh" 2>/dev/null || true
