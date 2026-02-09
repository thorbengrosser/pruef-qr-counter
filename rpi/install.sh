#!/bin/bash
# PRÜF Counter RPi install script. Run once after fresh Raspberry Pi OS on SD.
# Usage: sudo ./install.sh
# Idempotent: safe to run multiple times.

set -e
RPI_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$RPI_DIR"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo $0"
  exit 1
fi

echo "Installing system packages..."
apt-get update
apt-get install -y \
  python3-pip \
  python3-venv \
  libdbus-1-dev \
  libglib2.0-dev \
  libcairo2-dev \
  libopenjp2-7 \
  hostapd \
  dnsmasq \
  avahi-daemon \
  network-manager \
  --no-install-recommends

# Ensure Bluetooth is on (required for BLE / iPixel display)
echo "Enabling Bluetooth (required for BLE display)..."
apt-get install -y bluez --no-install-recommends 2>/dev/null || true
systemctl enable bluetooth 2>/dev/null || true
rfkill unblock bluetooth 2>/dev/null || true
systemctl start bluetooth 2>/dev/null || true
sleep 3
( bluetoothctl power on 2>/dev/null || true )

# Ensure NetworkManager is used for WiFi (disable dhcpcd on interface if conflicting)
if command -v nmcli &>/dev/null; then
  echo "NetworkManager available."
  # Ensure NetworkManager manages wlan0 (disable dhcpcd if it's managing it)
  if [ -f /etc/dhcpcd.conf ] && grep -q "^interface wlan0" /etc/dhcpcd.conf 2>/dev/null; then
    echo "Note: dhcpcd.conf mentions wlan0. NetworkManager should take over, but if WiFi fails, check for conflicts."
  fi
fi

# Configure fallback DNS (Quad9 non-profit + Cloudflare) so DNS works even on flaky hotspots
echo "Configuring fallback DNS (Quad9 9.9.9.9, Cloudflare 1.1.1.1)..."
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/dns-fallback.conf << 'DNSEOF'
[global-dns-domain-*]
servers=9.9.9.9,1.1.1.1
DNSEOF
# Reload NM to pick up DNS config
systemctl reload NetworkManager 2>/dev/null || true

echo "Creating virtualenv and installing Python deps..."
if [ ! -d "$RPI_DIR/venv" ]; then
  python3 -m venv "$RPI_DIR/venv"
fi
"$RPI_DIR/venv/bin/pip" install --upgrade pip
"$RPI_DIR/venv/bin/pip" install -r "$RPI_DIR/requirements.txt"

echo "Creating fonts directory..."
mkdir -p "$RPI_DIR/fonts"
# Optional: copy Kario from testing if present
if [ -f "$RPI_DIR/../testing/Kario39C3Var-Roman.ttf" ]; then
  cp "$RPI_DIR/../testing/Kario39C3Var-Roman.ttf" "$RPI_DIR/fonts/" 2>/dev/null || true
fi

echo "Installing systemd units..."
DISPLAY_SERVICE="pruf-display.service"
CONFIG_SERVICE="pruf-config-server.service"

cat > /etc/systemd/system/$DISPLAY_SERVICE << EOF
[Unit]
Description=PRÜF Counter display daemon (iPixel BLE)
After=network-online.target bluetooth.target
Wants=network-online.target bluetooth.target

[Service]
Type=simple
WorkingDirectory=$RPI_DIR
ExecStartPre=/usr/sbin/rfkill unblock bluetooth
ExecStartPre=/bin/sleep 3
ExecStart=$RPI_DIR/venv/bin/python $RPI_DIR/display_app.py
Restart=always
RestartSec=5
TimeoutStopSec=15
User=root
Group=root
# Performance logging: set PRUF_DEBUG=1 for verbose timing output
# Environment=PRUF_DEBUG=1

[Install]
WantedBy=multi-user.target
EOF

# Config server on port 80 (run as root so we can bind 80 without cap_net_bind)
cat > /etc/systemd/system/$CONFIG_SERVICE << EOF
[Unit]
Description=PRÜF Counter config UI (Flask)
After=network.target

[Service]
Type=simple
WorkingDirectory=$RPI_DIR
Environment=CONFIG_UI_PORT=80
ExecStart=$RPI_DIR/venv/bin/python -m config_ui.app
Restart=always
RestartSec=3
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF

# Network state machine: try primary/backup every 15s; after 8 failures start AP
cat > /etc/systemd/system/pruf-network.service << EOF
[Unit]
Description=PRÜF Counter network state (nmcli try primary/backup, AP fallback)
After=network.target NetworkManager.service
Before=$DISPLAY_SERVICE

[Service]
Type=simple
WorkingDirectory=$RPI_DIR
ExecStart=$RPI_DIR/network/network_state.sh
Restart=always
RestartSec=5
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $DISPLAY_SERVICE
systemctl enable $CONFIG_SERVICE
systemctl enable pruf-network.service

# Ensure config exists (copy from example template if missing)
if [ ! -f "$RPI_DIR/config.json" ]; then
  echo "Creating default config.json from config.json.example..."
  cp "$RPI_DIR/config.json.example" "$RPI_DIR/config.json"
fi

# Set hostname for mDNS (pruf.local)
CURRENT=$(hostname)
if [ "$CURRENT" != "pruf" ]; then
  echo "Setting hostname to pruf (for mDNS: http://pruf.local)"
  hostnamectl set-hostname pruf 2>/dev/null || true
  if [ -f /etc/hosts ] && ! grep -q 'pruf' /etc/hosts; then
    sed -i "s/127.0.1.1.*/127.0.1.1\tpruf/" /etc/hosts 2>/dev/null || true
  fi
fi

# Ensure Avahi (mDNS) is enabled for pruf.local
systemctl enable avahi-daemon 2>/dev/null || true
systemctl start avahi-daemon 2>/dev/null || true

echo "Starting config server (always on for captive + STA)..."
systemctl start $CONFIG_SERVICE

echo "Starting network state (try WiFi, AP fallback)..."
systemctl start pruf-network.service || true

echo "Starting display daemon..."
systemctl start $DISPLAY_SERVICE || true

# Fix ownership: install.sh runs as root but the pi user needs to write fonts/, config, etc.
if id pi &>/dev/null; then
  echo "Fixing file ownership for pi user..."
  chown -R pi:pi "$RPI_DIR/fonts" 2>/dev/null || true
  chown pi:pi "$RPI_DIR/config.json" 2>/dev/null || true
  chown pi:pi "$RPI_DIR/status.json" 2>/dev/null || true
fi

echo ""
echo "Install done. Config UI: http://$(hostname -I | awk '{print $1}')/ or http://pruf.local/"
echo "If no WiFi configured, connect to AP PRUF-Setup and open http://192.168.4.1 (after network/AP setup)."
echo "See rpi/README.md and rpi/network/ for AP + captive portal setup."
