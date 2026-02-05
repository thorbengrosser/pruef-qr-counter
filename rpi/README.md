# PRÜF Counter — Raspberry Pi Zero 2 W

Headless Python display daemon for iPixel LED matrices: polls the count API, renders with configurable font/colors/effects, and sends to one or more BLE displays. Configured via a captive portal (AP mode) or at `http://pruf.local` when connected to WiFi or a phone hotspot.

## Target board

- **Raspberry Pi Zero 2 W** (WiFi + BLE required)
- **OS**: Raspberry Pi OS Lite (Bookworm) recommended; headless operation (no display/keyboard)
- **Python**: Requires Python 3.10+ (Raspberry Pi OS Bookworm includes Python 3.11)

## Prerequisites

- Raspberry Pi Zero 2 W with microSD card
- iPixel 64×16 (or compatible) BLE display(s) — name prefix `LED_BLE_`
- Network: primary WiFi and optional backup WiFi (or phone hotspot for setup)

## Local testing (on your machine before deploying)

You can run the config UI and test basic behaviour on your laptop/desktop without a Pi.

1. **Config UI only** (edit settings, see form, test Save):
   ```bash
   cd rpi
   ./run_local.sh config-ui
   ```
   Then open **http://localhost:5050** in your browser. You can change all options and click Save; config is written to `rpi/config.json`. `try_connect.sh` and `systemctl restart` will no-op or fail harmlessly off the Pi.

2. **Scan for iPixel devices** (if you have a BLE dongle and an iPixel nearby):
   ```bash
   ./run_local.sh scan
   ```

3. **Display daemon** (API polling + BLE; BLE will fail without a device):
   ```bash
   ./run_local.sh display
   ```
   Uses `config.json`; polls the API and, if BLE devices are configured and in range, sends to the display. Without any `LED_BLE_*` device you’ll see “Could not connect to any display” and exit, but you can still verify config load and API URL.

4. **Dry run (test behaviour without BLE)**:
   ```bash
   ./run_local.sh dry-run
   ```
   Skips BLE entirely: loads config, polls the API, renders frames with your font/colors/offset, and saves them to **`rpi/preview/`**. Open `rpi/preview/latest.png` to see the current frame (64×16); `count_N.png` is also written for each count. Use this to check API polling, rendering, and flash behaviour before deploying to the Pi. Ctrl+C to stop.

5. **One-off setup** (creates venv and installs deps if needed):
   - `run_local.sh` creates `rpi/venv` and runs `pip install -r requirements.txt` on first run. You only need Python 3 and a terminal in the `rpi` directory.

## Quick install (SD card)

1. **Flash SD card**
   - Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or similar
   - Choose **Raspberry Pi OS Lite** (64-bit or 32-bit for Zero 2 W)
   - Before writing: enable **SSH** (set username/password or allow password auth), set **hostname** to `pruf` if possible, configure WiFi (optional — you can also use the device AP for first config)

2. **Boot and install**
   - Insert SD, power on, wait for boot
   - If you configured WiFi: `ssh pi@pruf.local` (or `pi@<ip>`)
   - If not: connect over USB or serial, or connect to the device AP after first run (see below)
   - Copy this repo onto the Pi (clone or copy the `rpi` folder), then:
   ```bash
   cd /path/to/pruef_counter/rpi
   sudo ./install.sh
   ```
   - The script installs dependencies, creates a venv, sets up systemd units, and writes a default config. On first boot with no WiFi configured, it starts the **PRUF-Setup** AP.

3. **First-time configuration**
   - Connect your phone/laptop to the WiFi network **PRUF-Setup** (password in `install.sh` / config; default `pruef1234` if applicable)
   - Open a browser and go to **http://192.168.4.1** (captive portal will often open this automatically)
   - Enter **primary WiFi** (and optional backup WiFi), **API URL** (e.g. `https://pruef.st/api/count`), and display options (font, text size, y-offset, colors, effect, refresh rate, devices: auto or comma-separated BLE addresses)
   - Click **Save** — the device will reconnect to your WiFi and start the display daemon

4. **Normal operation**
   - The Pi connects to primary WiFi; the display daemon polls the API and updates the iPixel(s). On API errors it keeps the last value and retries. After prolonged failure it tries the backup WiFi, then falls back to starting the AP again so you can reconfigure.

5. **Reconfiguring later**
   - When the Pi is on the same network (e.g. home WiFi or your phone hotspot): open **http://pruf.local** (mDNS) or **http://\<device-ip\>/** and change settings, then Save.

**Captive portal (AP mode)**: When the device starts the **PRUF-Setup** AP (first boot or after repeated WiFi failures), connect to that WiFi and open **http://192.168.4.1** — the config UI is served there. NetworkManager’s AP “shared” mode provides DHCP; the config server listens on port 80.

## Connect to mobile hotspot

- Join the Pi to your phone’s hotspot (set primary WiFi to the hotspot SSID/password, or connect once via PRUF-Setup and set it there). Then open **http://pruf.local** or the IP your hotspot gave the Pi to access the same config UI.

## Project layout

- `README.md` — This file
- `run_local.sh` — Run config UI or display daemon locally for testing (see “Local testing” above)
- `install.sh` — One-time install script (deps, venv, hostapd, dnsmasq, Avahi, systemd)
- `requirements.txt` — Python deps (pypixelcolor, bleak, Pillow, requests, Flask)
- `config.json` — Default/example config (overwritten on first save from UI)
- `display_app.py` — Display daemon (API poll, render, BLE send, multi-display, reconnect)
- `config_ui/` — Flask config server (form GET/POST, write config, restart display service)
- `fonts/` — Optional TTF/OTF (e.g. **Kario39C3Var-Roman.ttf**); add from `../testing/` or document in README
- `network/` — Scripts for NetworkManager (nmcli): start AP, connect STA, primary/backup failover

## Monitoring & Remote Access

When you're away from the Pi, you can monitor its status remotely:

### Web Status Dashboard

- **Status page**: Open **http://pruf.local/status** (or `http://192.168.4.1/status` in AP mode)
  - Shows display status (last count, API status, BLE connections)
  - Shows systemd service status (display, config, network)
  - Shows WiFi connection status
  - Auto-refreshes every 10 seconds

- **JSON API**: **http://pruf.local/status.json** for programmatic access
  - Returns JSON with all status information
  - Useful for scripts or external monitoring tools

### SSH Access

If you have SSH enabled and network access:

```bash
# SSH into the Pi (replace with your Pi's IP or hostname)
ssh pi@pruf.local
# or
ssh pi@<pi-ip-address>
```

**Check logs**:
```bash
# Display daemon logs
journalctl --user -u pruf-display.service -f

# Config server logs
journalctl --user -u pruf-config-server.service -f

# Network service logs
journalctl --user -u pruf-network.service -f

# All PRÜF services
journalctl --user -u pruf-*.service -f
```

**Check service status**:
```bash
systemctl --user status pruf-display.service
systemctl --user status pruf-config-server.service
systemctl --user status pruf-network.service
```

**Restart services**:
```bash
systemctl --user restart pruf-display.service
systemctl --user restart pruf-config-server.service
```

**Check WiFi status**:
```bash
nmcli connection show --active
nmcli device status
```

### Status File

The display daemon writes status to `rpi/status.json`:
- `last_count`: Last successfully fetched count
- `last_error`: Last error message (if any)
- `api_ok`: Boolean indicating if API is reachable
- `ble_connected`: Number of connected BLE devices
- `ble_addresses`: List of connected BLE device addresses
- `last_update`: Unix timestamp of last update

You can read this file directly:
```bash
cat ~/pruef_counter/rpi/status.json
```

## Troubleshooting

- **No BLE devices found**: Ensure iPixel is on and in range; name must start with `LED_BLE_`. Run from command line with `--scan` (see `display_app.py --help`) to list devices.
- **API unreachable**: Check `api_url` in config (full URL to count endpoint). Device will show last value and retry; after repeated failure it will try backup WiFi then start the AP.
- **Can’t open config page**: In AP mode use **http://192.168.4.1**. When on WiFi/hotspot use **http://pruf.local** (requires mDNS/Avahi) or the Pi’s IP address.
- **Font not found**: Put **Kario39C3Var-Roman.ttf** (or your font) in `rpi/fonts/` and select it in the config UI, or set `font` in `config.json` to the filename under `fonts/`.

## Systemd services

- `pruf-display.service` — Runs `display_app.py`; restart on failure.
- `pruf-config-server.service` — Serves the Flask config UI (both in AP and STA mode).

Use `sudo systemctl status pruf-display pruf-config-server` to check status.
