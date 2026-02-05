#!/bin/bash
# Start AP "PRUF-Setup" with NetworkManager (nmcli). Creates connection if needed.
# Config server must already be running so captive portal works at 192.168.4.1.

set -e
CON_NAME="${PRUF_AP_NAME:-pruf-ap}"
SSID="${PRUF_AP_SSID:-PRUF-Setup}"
PASS="${PRUF_AP_PASS:-pruef1234}"
IFACE="${PRUF_AP_IFACE:-wlan0}"

if ! nmcli connection show "$CON_NAME" &>/dev/null; then
  echo "Creating AP connection: $CON_NAME" >&2
  nmcli connection add type wifi ifname "$IFACE" con-name "$CON_NAME" autoconnect no ssid "$SSID" 2>/dev/null || true
  nmcli connection modify "$CON_NAME" 802-11-wireless.mode ap 2>/dev/null || true
  nmcli connection modify "$CON_NAME" 802-11-wireless.band bg 2>/dev/null || true
  nmcli connection modify "$CON_NAME" ipv4.method shared 2>/dev/null || true
  nmcli connection modify "$CON_NAME" ipv4.addresses 192.168.4.1/24 2>/dev/null || true
  nmcli connection modify "$CON_NAME" wifi-sec.key-mgmt wpa-psk 2>/dev/null || true
  nmcli connection modify "$CON_NAME" wifi-sec.psk "$PASS" 2>/dev/null || true
fi

echo "Starting AP: $SSID" >&2
nmcli connection up "$CON_NAME" 2>/dev/null || true
echo "AP up. Connect to $SSID and open http://192.168.4.1" >&2
