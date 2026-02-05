#!/bin/bash
# Run config UI and optionally display app locally for testing (no Pi required).
# Config UI: http://localhost:5050
# Usage: ./run_local.sh [config-ui|display|scan|all]

set -e
RPI_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$RPI_DIR"

ensure_venv() {
  if [ ! -d "$RPI_DIR/venv" ]; then
    echo "Creating venv and installing dependencies..."
    python3 -m venv "$RPI_DIR/venv"
    "$RPI_DIR/venv/bin/pip" install --upgrade pip
    "$RPI_DIR/venv/bin/pip" install -r "$RPI_DIR/requirements.txt"
  fi
}

ensure_venv

case "${1:-config-ui}" in
  config-ui)
    echo "Starting config UI at http://localhost:5050"
    echo "Open in browser: http://127.0.0.1:5050"
    CONFIG_UI_PORT=5050 CONFIG_UI_HOST=127.0.0.1 FLASK_DEBUG=1 \
      "$RPI_DIR/venv/bin/python" -m config_ui.app
    ;;
  display)
    echo "Starting display daemon (will try API + BLE; BLE may fail without device)"
    "$RPI_DIR/venv/bin/python" display_app.py
    ;;
  dry-run)
    echo "Dry run: no BLE, polling API and saving frames to rpi/preview/"
    echo "Open rpi/preview/latest.png to see the current frame. Ctrl+C to stop."
    "$RPI_DIR/venv/bin/python" display_app.py --dry-run
    ;;
  scan)
    echo "Scanning for LED_BLE_* devices..."
    "$RPI_DIR/venv/bin/python" display_app.py --scan
    ;;
  all)
    echo "Starting config UI at http://localhost:5050 (background) and display daemon (foreground)"
    CONFIG_UI_PORT=5050 CONFIG_UI_HOST=127.0.0.1 \
      "$RPI_DIR/venv/bin/python" -m config_ui.app &
    PID=$!
    sleep 2
    "$RPI_DIR/venv/bin/python" display_app.py || true
    kill $PID 2>/dev/null || true
    ;;
  *)
    echo "Usage: $0 [config-ui|display|dry-run|scan|all]"
    echo "  config-ui  - Run config UI only at http://localhost:5050 (default)"
    echo "  display    - Run display daemon (API + BLE; needs config.json)"
    echo "  dry-run    - Test without BLE: poll API, render frames to rpi/preview/"
    echo "  scan       - Scan for iPixel BLE devices and exit"
    echo "  all        - Run config UI in background + display daemon in foreground"
    exit 1
    ;;
esac
