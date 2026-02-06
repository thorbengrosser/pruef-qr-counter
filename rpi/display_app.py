#!/usr/bin/env python3
"""
PRÜF Counter display daemon for Raspberry Pi Zero 2 W.

Reads config from config.json (or CONFIG_PATH env), connects to iPixel display(s)
via BLE, polls the count API (or shows fixed display_string), and renders with
configured font/size/offset/colors. Multi-display: devices "auto" or comma-separated
addresses; sends to all, reconnects dropped clients.
"""

import asyncio
import json
import os
import sys
import tempfile
import time

try:
    import pypixelcolor
    import requests
    from PIL import Image, ImageDraw, ImageFont
    from bleak import BleakScanner
except ImportError as e:
    print("Missing dependencies: pip install -r requirements.txt", file=sys.stderr)
    print(f"ImportError: {e}", file=sys.stderr)
    sys.exit(1)

DISPLAY_SLOT = 1
DEFAULT_DEVICE_PREFIX = "LED_BLE_"
RECONNECT_COOLDOWN_SEC = 5
DEFAULT_WIDTH, DEFAULT_HEIGHT = 64, 16

# Use RAM-backed tmpdir for rendered PNGs (avoids SD card writes on every render)
_TMPDIR = "/dev/shm" if os.path.isdir("/dev/shm") else None


def get_rpi_dir() -> str:
    """Directory containing this script (rpi/)."""
    return os.path.dirname(os.path.abspath(__file__))


def _status_path() -> str:
    return os.path.join(get_rpi_dir(), "status.json")


def write_status(
    last_error: str | None = None,
    last_count: int | None = None,
    api_ok: bool = True,
    ble_connected: int = 0,
    ble_addresses: list[str] | None = None,
) -> None:
    """Write status for config UI (last error, last count, api_ok, BLE info)."""
    try:
        data = {}
        if os.path.isfile(_status_path()):
            with open(_status_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
        if last_error is not None:
            data["last_error"] = last_error
        if last_count is not None:
            data["last_count"] = last_count
        data["api_ok"] = api_ok
        data["ble_connected"] = ble_connected
        if ble_addresses is not None:
            data["ble_addresses"] = ble_addresses
        data["last_update"] = time.time()
        with open(_status_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=0)
    except Exception:
        pass


def load_config(path: str | None = None) -> dict:
    """Load config from JSON file. path defaults to rpi/config.json."""
    if path is None:
        path = os.environ.get("CONFIG_PATH") or os.path.join(get_rpi_dir(), "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_font_path(cfg: dict) -> str:
    """Resolve font path: rpi/fonts/<font> or pypixelcolor built-in."""
    font = cfg.get("font", "Kario39C3Var-Roman.ttf")
    fonts_dir = os.path.join(get_rpi_dir(), "fonts")
    local = os.path.join(fonts_dir, font)
    if os.path.isfile(local):
        return local
    # pypixelcolor built-in (no .ttf in name for some)
    builtin_dir = os.path.join(os.path.dirname(pypixelcolor.__file__), "fonts")
    for name in (font, font.replace(".ttf", ""), "VCR_OSD_MONO"):
        p = os.path.join(builtin_dir, f"{name}.ttf" if not name.endswith(".ttf") else name)
        if os.path.isfile(p):
            return p
    return os.path.join(builtin_dir, "VCR_OSD_MONO.ttf")


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hex_str}")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def apply_variable_font_axes(font, *, weight=None, width=None, optical_size=None, instance=None):
    try:
        if instance:
            font.set_variation_by_name(instance.encode() if isinstance(instance, str) else instance)
        elif weight is not None or width is not None or optical_size is not None:
            axes = font.get_variation_axes()
            values = []
            for ax in axes:
                n = (ax.get("name") or b"").decode("utf-8", errors="ignore").lower()
                t = (ax.get("tag") or b"").decode("utf-8", errors="ignore").lower()
                if ("weight" in n or t == "wght") and weight is not None:
                    values.append(weight)
                elif ("width" in n or t == "wdth") and width is not None:
                    values.append(width)
                elif ("optical" in n or t == "opsz") and optical_size is not None:
                    values.append(optical_size)
                else:
                    values.append(ax["default"])
            font.set_variation_by_axes(values)
    except (OSError, AttributeError):
        pass


def load_font(font_path: str, font_size: int, font_width: float | None = None) -> ImageFont.FreeTypeFont:
    """Load and configure a font once. Reuse the returned object for rendering."""
    font = ImageFont.truetype(font_path, min(128, max(6, font_size)))
    apply_variable_font_axes(font, width=font_width)
    return font


def render_text_to_image(
    text: str,
    width: int,
    height: int,
    *,
    font: ImageFont.FreeTypeFont | None = None,
    font_path: str = "",
    font_size: int = 16,
    font_width: float | None = None,
    y_offset: int = 0,
    crisp: bool = False,
    text_color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 0),
) -> str:
    """Render text to image. Returns path to temp PNG.
    Pass a pre-loaded `font` object for performance; falls back to loading from font_path."""
    if font is None:
        font = load_font(font_path, font_size, font_width)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    draw.text(
        (width // 2, height // 2 + y_offset),
        text, fill=text_color, font=font, anchor="mm"
    )

    if crisp:
        # Fast crisp: threshold each channel using Pillow's point() (C-level, ~10x faster than Python loop)
        tc = text_color
        bc = bg_color
        channels = img.split()
        result_channels = []
        for i, ch in enumerate(channels):
            mid = (tc[i] + bc[i]) / 2.0
            if tc[i] >= bc[i]:
                # text is brighter: pixel >= mid → text color, else bg
                lut = [tc[i] if v >= mid else bc[i] for v in range(256)]
            else:
                # text is darker: pixel <= mid → text color, else bg
                lut = [tc[i] if v <= mid else bc[i] for v in range(256)]
            result_channels.append(ch.point(lut))
        img = Image.merge("RGB", result_channels)

    fd, path = tempfile.mkstemp(suffix=".png", dir=_TMPDIR)
    os.close(fd)
    img.save(path)
    return path


def save_solid_image(width: int, height: int, color: tuple[int, int, int]) -> str:
    img = Image.new("RGB", (width, height), color)
    fd, path = tempfile.mkstemp(suffix=".png", dir=_TMPDIR)
    os.close(fd)
    img.save(path)
    return path


async def scan_led_devices(prefix: str = DEFAULT_DEVICE_PREFIX, timeout: float = 5.0) -> list[tuple[str, str]]:
    devices = await BleakScanner.discover(timeout=timeout)
    return [
        (d.name or "?", d.address)
        for d in devices
        if d.name and d.name.startswith(prefix)
    ]


def resolve_device_addresses(cfg: dict) -> tuple[list[str], bool]:
    """(addresses, is_auto) from config 'devices'."""
    dev = (cfg.get("devices") or "auto").strip().lower()
    if dev == "auto":
        found = asyncio.run(scan_led_devices())
        addrs = [addr for _name, addr in found]
        return (addrs, True)
    addrs = [a.strip() for a in dev.split(",") if a.strip()]
    return (addrs, False)


_last_api_error: str = ""
_http_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Reuse a requests.Session for HTTP keep-alive (avoids TCP+TLS handshake every poll)."""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
    return _http_session


def fetch_count(api_url: str) -> int | None:
    global _last_api_error
    try:
        r = _get_session().get(api_url, timeout=2)
        r.raise_for_status()
        if _last_api_error:
            print("API recovered.", file=sys.stderr)
            _last_api_error = ""
        return int(r.json().get("count", 0))
    except Exception as e:
        err_msg = str(e)
        # Only log when error changes (avoid flooding journal with same DNS error every second)
        if err_msg != _last_api_error:
            print(f"API error: {e}", file=sys.stderr)
            _last_api_error = err_msg
        return None


def disconnect_all(clients: list) -> None:
    for c in clients:
        try:
            c.disconnect()
        except Exception:
            pass


def connect_to_addresses(addresses: list[str]) -> list:
    """Try to connect to known addresses (no scan). Returns connected clients."""
    clients = []
    for addr in addresses:
        try:
            c = pypixelcolor.Client(addr)
            c.connect()
            clients.append(c)
        except Exception as e:
            print(f"Connect {addr}: {e}", file=sys.stderr)
    return clients


def send_image_to_clients(clients: list, path: str, cleanup: bool = True) -> list:
    working = []
    for c in clients:
        try:
            c.send_image(path, save_slot=DISPLAY_SLOT)
            c.show_slot(DISPLAY_SLOT)
            working.append(c)
        except Exception as e:
            print(f"Display disconnected: {e}", file=sys.stderr)
            try:
                c.disconnect()
            except Exception:
                pass
    if cleanup:
        try:
            os.unlink(path)
        except OSError:
            pass
    return working


# Backoff constants
BACKOFF_MIN_SEC = 5.0
BACKOFF_MAX_SEC = 120.0


class ReconnectState:
    """Manages BLE reconnection with exponential backoff.
    
    Strategy:
    1. If all clients connected -> do nothing.
    2. If some clients dropped -> try reconnecting to known addresses only (fast, no scan).
    3. If known-address reconnect fails -> do a full BLE scan (addresses may have changed).
    4. Exponential backoff between attempts so we don't hammer the BLE radio.
    """

    def __init__(self, addresses: list[str], is_auto: bool):
        self.addresses = addresses
        self.is_auto = is_auto
        self.last_attempt: float = 0.0
        self.backoff: float = BACKOFF_MIN_SEC
        self.consecutive_failures: int = 0

    def _connected_addresses(self, clients: list) -> set[str]:
        return {c.address for c in clients if hasattr(c, "address")}

    def _missing_addresses(self, clients: list) -> list[str]:
        connected = self._connected_addresses(clients)
        return [a for a in self.addresses if a not in connected]

    def _reset_backoff(self) -> None:
        self.backoff = BACKOFF_MIN_SEC
        self.consecutive_failures = 0

    def _increase_backoff(self) -> None:
        self.consecutive_failures += 1
        self.backoff = min(BACKOFF_MAX_SEC, BACKOFF_MIN_SEC * (2 ** self.consecutive_failures))

    def _cooldown_elapsed(self) -> bool:
        return (time.monotonic() - self.last_attempt) >= self.backoff

    def maybe_reconnect(self, clients: list) -> list:
        """Called after every send. Reconnects dropped clients if needed."""
        # All connected? Nothing to do.
        if len(clients) >= len(self.addresses):
            self._reset_backoff()
            return clients

        if not self._cooldown_elapsed():
            return clients

        self.last_attempt = time.monotonic()
        missing = self._missing_addresses(clients)

        if not missing:
            return clients

        # Step 1: Try known addresses directly (fast, no scan)
        print(f"Reconnecting {len(missing)} display(s) by address...", file=sys.stderr)
        new_clients = connect_to_addresses(missing)

        if new_clients:
            clients.extend(new_clients)
            if len(clients) >= len(self.addresses):
                print(f"All {len(clients)} display(s) reconnected.", file=sys.stderr)
                self._reset_backoff()
                return clients

        # Step 2: Known-address reconnect didn't get all — scan if auto
        if self.is_auto:
            still_missing = len(self.addresses) - len(clients)
            print(f"Still missing {still_missing} display(s); scanning...", file=sys.stderr)
            found = asyncio.run(scan_led_devices(timeout=3.0))
            new_addrs = [addr for _name, addr in found]
            if new_addrs:
                # Update address list (devices may have changed BLE address)
                self.addresses = list(set(self.addresses) | set(new_addrs))
                connected = self._connected_addresses(clients)
                scan_missing = [a for a in new_addrs if a not in connected]
                if scan_missing:
                    scan_clients = connect_to_addresses(scan_missing)
                    clients.extend(scan_clients)

        if len(clients) >= len(self.addresses):
            self._reset_backoff()
        else:
            self._increase_backoff()
            print(f"Reconnect incomplete ({len(clients)}/{len(self.addresses)}); "
                  f"next attempt in {self.backoff:.0f}s", file=sys.stderr)

        return clients

    def force_reconnect(self, clients: list) -> list:
        """Called when all clients are gone. Same logic but always tries."""
        if clients:
            return clients
        if not self._cooldown_elapsed():
            return clients
        print("All displays lost. Reconnecting...", file=sys.stderr)
        return self.maybe_reconnect(clients)


def run_display_loop(config_path: str | None = None, dry_run: bool = False) -> None:
    cfg = load_config(config_path)
    font_path = resolve_font_path(cfg)
    api_url = (cfg.get("api_url") or "https://pruef.st/api/count").strip()
    # Upgrade http to https if pointing at pruef.st (HTTPS is fine on Pi, avoids carrier interception)
    if api_url.startswith("http://pruef.st"):
        api_url = api_url.replace("http://", "https://", 1)
    poll_interval = max(0.5, float(cfg.get("poll_interval_sec", 1.0)))
    display_string = (cfg.get("display_string") or "").strip()
    suffix = cfg.get("suffix") or " x"
    font_size = int(cfg.get("font_size") or 22)
    font_width_raw = cfg.get("font_width")
    font_width = float(font_width_raw) if font_width_raw not in (None, "") else None
    y_offset = int(cfg.get("y_offset") or 1)
    crisp = bool(cfg.get("crisp", True))
    text_color = hex_to_rgb(cfg.get("text_color") or "ffffff")
    bg_color = hex_to_rgb(cfg.get("bg_color") or "000000")
    effect = (cfg.get("effect") or "none").strip().lower()
    flash_duration = max(0.05, float(cfg.get("flash_duration_sec") or 0.15))
    flash_repeat = int(cfg.get("flash_repeat") or 3)
    flash_text_rgb = hex_to_rgb(cfg.get("flash_text_color") or "000000")
    flash_bg_rgb = hex_to_rgb(cfg.get("flash_bg_color") or "ffffff")
    flash_color_rgb = hex_to_rgb(cfg.get("flash_color") or "ffffff")
    flash_color2 = (cfg.get("flash_color2") or "").strip()
    flash_color2_rgb = hex_to_rgb(flash_color2) if flash_color2 else None

    w = DEFAULT_WIDTH
    h = DEFAULT_HEIGHT
    clients: list = []
    reconn: ReconnectState | None = None
    current_count: list[int | None] = [None]  # for dry-run preview naming

    if dry_run:
        import shutil
        preview_dir = os.path.join(get_rpi_dir(), "preview")
        os.makedirs(preview_dir, exist_ok=True)
        clients = [None]  # sentinel so loop runs
        print(f"Dry run: no BLE, saving frames to {preview_dir}/", file=sys.stderr)
        print(f"API: {api_url}", file=sys.stderr)
        print(f"Display: {w}x{h} | Font: {font_path}", file=sys.stderr)

        def send_and_reconnect(path: str, cleanup: bool = True) -> list:
            dest = os.path.join(preview_dir, "latest.png")
            shutil.copy2(path, dest)
            n = current_count[0]
            if n is not None:
                shutil.copy2(path, os.path.join(preview_dir, f"count_{n}.png"))
            print(f"  -> {dest}", file=sys.stderr)
            if cleanup:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            return [None]

        def force_reconnect(c: list) -> list:
            return c
    else:
        addresses, is_auto = resolve_device_addresses(cfg)
        if not addresses:
            print("No devices found yet. Will keep retrying...", file=sys.stderr)
        else:
            print(f"Connecting to {len(addresses)} device(s)...", file=sys.stderr)
        print(f"API: {api_url}", file=sys.stderr)
        if addresses:
            clients = connect_to_addresses(addresses)
        if clients:
            try:
                w, h = clients[0].get_device_info().width, clients[0].get_device_info().height
            except Exception:
                pass
        reconn = ReconnectState(addresses, is_auto)
        print(f"Display: {w}x{h} | Font: {font_path}", file=sys.stderr)

        def send_and_reconnect(path: str, cleanup: bool = True) -> list:
            nonlocal clients
            clients = send_image_to_clients(clients, path, cleanup=cleanup)
            clients = reconn.maybe_reconnect(clients)
            return clients

        def force_reconnect(c: list) -> list:
            return reconn.force_reconnect(c)

    # Pre-load font once (avoids re-reading TTF from SD card on every render)
    _cached_font = load_font(font_path, font_size, font_width)

    def render(txt: str, text_col: tuple, bg_col: tuple) -> str:
        return render_text_to_image(
            txt, w, h,
            font=_cached_font,
            y_offset=y_offset,
            crisp=crisp,
            text_color=text_col,
            bg_color=bg_col,
        )

    prev_count: int | None = None
    last_sent_text: str | None = None   # track what's on display to skip redundant sends
    last_status_write: float = 0.0      # throttle status.json writes
    STATUS_WRITE_INTERVAL = 10.0        # write status at most every 10s (unless count changes)

    try:
        while True:
            clients = force_reconnect(clients)
            if not clients:
                time.sleep(poll_interval)
                continue

            count = fetch_count(api_url)
            current_count[0] = count
            text_to_show = display_string if display_string else (f"{count}{suffix}" if count is not None else "--")

            if count is not None or display_string:
                count_incremented = (
                    effect in ("invert", "screen")
                    and not display_string
                    and count is not None
                    and prev_count is not None
                    and count > prev_count
                )

                if count_incremented and effect == "invert":
                    flash_img = render(text_to_show, flash_text_rgb, flash_bg_rgb)
                    normal_img = render(text_to_show, text_color, bg_color)
                    for _ in range(flash_repeat):
                        send_and_reconnect(flash_img, cleanup=False)
                        time.sleep(flash_duration)
                        send_and_reconnect(normal_img, cleanup=False)
                        time.sleep(flash_duration)
                    try:
                        os.unlink(flash_img)
                        os.unlink(normal_img)
                    except OSError:
                        pass
                    last_sent_text = text_to_show  # flash already showed it

                elif count_incremented and effect == "screen":
                    normal_img = render(text_to_show, text_color, bg_color)
                    flash_paths = [save_solid_image(w, h, flash_color_rgb)]
                    if flash_color2_rgb:
                        flash_paths.append(save_solid_image(w, h, flash_color2_rgb))
                    for _ in range(flash_repeat):
                        for fp in flash_paths:
                            send_and_reconnect(fp, cleanup=False)
                            time.sleep(flash_duration)
                        send_and_reconnect(normal_img, cleanup=False)
                        time.sleep(flash_duration)
                    try:
                        for fp in flash_paths:
                            os.unlink(fp)
                        os.unlink(normal_img)
                    except OSError:
                        pass
                    last_sent_text = text_to_show  # flash already showed it

                # Only render+send if the displayed text actually changed
                if text_to_show != last_sent_text:
                    send_and_reconnect(render(text_to_show, text_color, bg_color))
                    last_sent_text = text_to_show

                if count is not None:
                    count_changed = count != prev_count
                    prev_count = count
                    # Write status: immediately on count change, otherwise throttled
                    now = time.monotonic()
                    if count_changed or (now - last_status_write) >= STATUS_WRITE_INTERVAL:
                        if dry_run:
                            ble_addrs = []
                            ble_count = 0
                        else:
                            ble_addrs = [c.address for c in clients if hasattr(c, "address")]
                            ble_count = len([c for c in clients if c is not None])
                        write_status(last_error="", last_count=count, api_ok=True, ble_connected=ble_count, ble_addresses=ble_addrs)
                        last_status_write = now
            else:
                # API unreachable: show last or "--"
                fallback_text = f"{prev_count}{suffix}" if prev_count is not None else "--"
                if fallback_text != last_sent_text:
                    send_and_reconnect(render(fallback_text, text_color, bg_color))
                    last_sent_text = fallback_text
                # Throttle error status writes too
                now = time.monotonic()
                if (now - last_status_write) >= STATUS_WRITE_INTERVAL:
                    write_status(last_error="API unreachable", api_ok=False)
                    last_status_write = now

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\nStopped", file=sys.stderr)
    finally:
        if not dry_run:
            disconnect_all(clients)


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="PRÜF Counter display daemon (iPixel BLE)")
    p.add_argument("--config", metavar="PATH", help="Config JSON path (default: rpi/config.json or CONFIG_PATH)")
    p.add_argument("--scan", action="store_true", help="Scan for LED_BLE_* devices and exit")
    p.add_argument("--dry-run", action="store_true", help="No BLE: poll API, render frames, save to rpi/preview/ for testing")
    args = p.parse_args()

    if args.scan:
        found = asyncio.run(scan_led_devices())
        if found:
            print(f"Found {len(found)} device(s):")
            for name, addr in found:
                print(f"  {name}  {addr}")
        else:
            print("No devices found.")
        return

    run_display_loop(args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
