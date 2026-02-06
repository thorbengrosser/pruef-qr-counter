#!/usr/bin/env python3
"""
PRÜF Counter display daemon for Raspberry Pi Zero 2 W.

Reads config from config.json (or CONFIG_PATH env), connects to iPixel display(s)
via BLE, polls the count API (or shows fixed display_string), and renders with
configured font/size/offset/colors. Multi-display: devices "auto" or comma-separated
addresses; sends to all, reconnects dropped clients.

v2: Hot config reload, parallel BLE, performance logging, emoji flash overlay.
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import pypixelcolor
    import requests
    from PIL import Image, ImageDraw, ImageFont
    from bleak import BleakScanner
except ImportError as e:
    print("Missing dependencies: pip install -r requirements.txt", file=sys.stderr)
    print(f"ImportError: {e}", file=sys.stderr)
    sys.exit(1)

# ── Logging ───────────────────────────────────────────────────────────

log = logging.getLogger("pruf-display")


def setup_logging():
    """Configure structured logging with timing info.

    Set PRUF_DEBUG=1 env var for verbose (DEBUG) output including every
    operation timing. Default is INFO which shows warnings and slow ops.
    """
    fmt = "%(asctime)s %(levelname)-5s %(message)s"
    datefmt = "%H:%M:%S"
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    log.addHandler(handler)
    log.setLevel(logging.DEBUG if os.environ.get("PRUF_DEBUG") else logging.INFO)


class PerfTimer:
    """Context manager that logs how long a block takes.

    Usage:
        with PerfTimer("BLE send"):
            client.send_image(path)

    Logs at DEBUG normally, WARNING if elapsed > warn_ms.
    """

    def __init__(self, label: str, warn_ms: float = 2000):
        self.label = label
        self.warn_ms = warn_ms
        self.elapsed_ms: float = 0

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = (time.monotonic() - self._start) * 1000
        level = logging.WARNING if self.elapsed_ms > self.warn_ms else logging.DEBUG
        log.log(level, "%s: %.0fms", self.label, self.elapsed_ms)


# ── Constants ─────────────────────────────────────────────────────────

DISPLAY_SLOT = 1
DEFAULT_DEVICE_PREFIX = "LED_BLE_"
DEFAULT_WIDTH, DEFAULT_HEIGHT = 64, 16

# Use RAM-backed tmpdir for rendered PNGs (avoids SD card writes on every render)
_TMPDIR = "/dev/shm" if os.path.isdir("/dev/shm") else None

# Thread pool for parallel BLE operations (connect + send to multiple displays)
BLE_THREAD_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ble")

# Backoff for BLE reconnection
BACKOFF_MIN_SEC = 3.0
BACKOFF_MAX_SEC = 60.0
BACKOFF_FAST_RETRIES = 3  # first N retries stay at min backoff


# ── Helpers ───────────────────────────────────────────────────────────


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
        sp = _status_path()
        if os.path.isfile(sp):
            with open(sp, "r", encoding="utf-8") as f:
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
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=0)
    except Exception:
        pass


def load_config(path: str | None = None) -> dict:
    """Load config from JSON file. path defaults to rpi/config.json. Raises on error."""
    if path is None:
        path = os.environ.get("CONFIG_PATH") or os.path.join(get_rpi_dir(), "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Minimal defaults when config.json is missing or invalid (so daemon can start; fix via config UI).
_CONFIG_DEFAULTS = {
    "api_url": "https://pruef.st/api/count",
    "poll_interval_sec": 1.0,
    "display_string": "",
    "suffix": " x",
    "font": "Kario39C3Var-Roman.ttf",
    "font_size": 22,
    "font_width": 100,
    "y_offset": 1,
    "crisp": True,
    "text_color": "ffffff",
    "bg_color": "000000",
    "effect": "invert",
    "flash_duration_sec": 0.15,
    "flash_repeat": 3,
    "flash_text_color": "000000",
    "flash_bg_color": "ffffff",
    "flash_color": "ffffff",
    "flash_color2": "",
    "devices": "auto",
}


def load_config_with_fallback(config_path: str) -> tuple[dict, str]:
    """Load config from config_path; if invalid/missing, try config.json.example then defaults.
    Returns (config_dict, path_used). path_used is config_path so hot-reload watches the right file."""
    rpi_dir = os.path.dirname(config_path)
    example_path = os.path.join(rpi_dir, "config.json.example")

    for path in (config_path, example_path):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if not raw:
                continue
            return (json.loads(raw), config_path)
        except (json.JSONDecodeError, OSError):
            continue

    log.warning("config.json invalid/missing; using defaults. Save from http://pruf.local/ to fix.")
    return (_CONFIG_DEFAULTS.copy(), config_path)


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
                # text is brighter: pixel >= mid -> text color, else bg
                lut = [tc[i] if v >= mid else bc[i] for v in range(256)]
            else:
                # text is darker: pixel <= mid -> text color, else bg
                lut = [tc[i] if v <= mid else bc[i] for v in range(256)]
            result_channels.append(ch.point(lut))
        img = Image.merge("RGB", result_channels)

    fd, path = tempfile.mkstemp(suffix=".png", dir=_TMPDIR)
    os.close(fd)
    img.save(path)
    return path


def render_checkmark_frame(width: int, height: int) -> str:
    """Render green background with large white checkmark for success flash overlay."""
    bg = (0, 204, 68)   # vivid green
    fg = (255, 255, 255) # white
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    # Draw a checkmark scaled to the display (e.g. 64x16)
    cx, cy = width // 2, height // 2
    # Short arm: going down-right to the bottom of the V
    # Long arm: going up-right from the V
    draw.line([(cx - 8, cy), (cx - 2, cy + 5)], fill=fg, width=3)
    draw.line([(cx - 2, cy + 5), (cx + 9, cy - 6)], fill=fg, width=3)
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


def _cleanup_file(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# ── BLE ───────────────────────────────────────────────────────────────


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
        with PerfTimer("BLE scan (auto)"):
            found = asyncio.run(scan_led_devices())
        addrs = [addr for _name, addr in found]
        log.info("Auto-scan found %d device(s): %s", len(addrs), addrs)
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
        with PerfTimer("API poll", warn_ms=1500):
            r = _get_session().get(api_url, timeout=3)
            r.raise_for_status()
        if _last_api_error:
            log.info("API recovered (was: %s)", _last_api_error[:80])
            _last_api_error = ""
        return int(r.json().get("count", 0))
    except Exception as e:
        err_msg = str(e)
        # Only log when error changes (avoid flooding journal with same DNS error every second)
        if err_msg != _last_api_error:
            log.warning("API error: %s", e)
            _last_api_error = err_msg
        return None


def disconnect_all(clients: list) -> None:
    for c in clients:
        try:
            c.disconnect()
        except Exception:
            pass


def _connect_one(addr: str):
    """Connect to a single BLE address. Returns (client, addr) or (None, addr)."""
    try:
        c = pypixelcolor.Client(addr)
        c.connect()
        return (c, addr)
    except Exception as e:
        log.warning("Connect %s failed: %s", addr, e)
        return (None, addr)


def connect_to_addresses(addresses: list[str]) -> list:
    """Connect to all addresses in parallel. Returns connected clients."""
    if not addresses:
        return []
    with PerfTimer(f"BLE connect {len(addresses)} device(s)", warn_ms=10000):
        futures = {BLE_THREAD_POOL.submit(_connect_one, addr): addr for addr in addresses}
        clients = []
        try:
            for fut in as_completed(futures, timeout=15):
                client, addr = fut.result()
                if client is not None:
                    clients.append(client)
                    log.info("Connected: %s", addr)
        except TimeoutError:
            log.warning("BLE connect timed out after 15s")
    return clients


def _send_one(client, path: str, slot: int):
    """Send image to a single client. Returns (client, success)."""
    try:
        client.send_image(path, save_slot=slot)
        client.show_slot(slot)
        return (client, True)
    except Exception as e:
        log.warning("Display send failed (%s): %s",
                    getattr(client, "address", "?"), e)
        try:
            client.disconnect()
        except Exception:
            pass
        return (client, False)


def send_image_to_clients(clients: list, path: str, cleanup: bool = True) -> list:
    """Send image to all clients in parallel. Returns working clients."""
    if not clients:
        if cleanup:
            _cleanup_file(path)
        return []
    with PerfTimer(f"BLE send to {len(clients)} display(s)"):
        futures = {BLE_THREAD_POOL.submit(_send_one, c, path, DISPLAY_SLOT): c for c in clients}
        working = []
        try:
            for fut in as_completed(futures, timeout=15):
                client, ok = fut.result()
                if ok:
                    working.append(client)
        except TimeoutError:
            log.warning("BLE send timed out after 15s")
    if cleanup:
        _cleanup_file(path)
    return working


# ── Reconnect ─────────────────────────────────────────────────────────


class ReconnectState:
    """Manages BLE reconnection with exponential backoff.

    Strategy:
    1. If all clients connected -> do nothing.
    2. If some clients dropped -> try reconnecting to known addresses only (fast, no scan).
    3. If known-address reconnect fails -> do a full BLE scan (addresses may have changed).
    4. First few retries are fast (BACKOFF_MIN_SEC), then exponential backoff.
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
        # First few retries: stay fast for quick recovery
        if self.consecutive_failures <= BACKOFF_FAST_RETRIES:
            self.backoff = BACKOFF_MIN_SEC
        else:
            self.backoff = min(
                BACKOFF_MAX_SEC,
                BACKOFF_MIN_SEC * (2 ** (self.consecutive_failures - BACKOFF_FAST_RETRIES))
            )

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
        log.info("Reconnecting %d display(s) by address...", len(missing))
        new_clients = connect_to_addresses(missing)

        if new_clients:
            clients.extend(new_clients)
            if len(clients) >= len(self.addresses):
                log.info("All %d display(s) reconnected.", len(clients))
                self._reset_backoff()
                return clients

        # Step 2: Known-address reconnect didn't get all — scan if auto
        if self.is_auto:
            still_missing = len(self.addresses) - len(clients)
            log.info("Still missing %d display(s); scanning...", still_missing)
            with PerfTimer("BLE re-scan"):
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
            log.info("Reconnect incomplete (%d/%d); next attempt in %.0fs",
                     len(clients), len(self.addresses), self.backoff)

        return clients

    def force_reconnect(self, clients: list) -> list:
        """Called when all clients are gone. Same logic but always tries."""
        if clients:
            return clients
        if not self._cooldown_elapsed():
            return clients
        # No known addresses (e.g. none found at startup) — scan for devices first
        if not self.addresses and self.is_auto:
            self.last_attempt = time.monotonic()
            log.info("Scanning for LED_BLE_* devices...")
            with PerfTimer("BLE scan (no addresses)"):
                found = asyncio.run(scan_led_devices(timeout=5.0))
            self.addresses = [addr for _name, addr in found]
            if not self.addresses:
                log.warning("No LED_BLE_* devices found; will retry in %.0fs", self.backoff)
                self._increase_backoff()
                return []
        log.info("All displays lost. Reconnecting...")
        return self.maybe_reconnect(clients)


# ── Display Config (hot-reloadable) ──────────────────────────────────


class DisplayConfig:
    """All config-derived display settings. Reloaded when config.json changes."""

    def __init__(self, cfg: dict):
        self.api_url = (cfg.get("api_url") or "https://pruef.st/api/count").strip()
        if self.api_url.startswith("http://pruef.st"):
            self.api_url = self.api_url.replace("http://", "https://", 1)
        self.poll_interval = max(0.5, float(cfg.get("poll_interval_sec", 1.0)))
        self.display_string = (cfg.get("display_string") or "").strip()
        self.suffix = cfg.get("suffix") or " x"
        self.font_size = int(cfg.get("font_size") or 22)
        fw = cfg.get("font_width")
        self.font_width = float(fw) if fw not in (None, "") else None
        self.y_offset = int(cfg.get("y_offset") or 1)
        self.crisp = bool(cfg.get("crisp", True))
        self.text_color = hex_to_rgb(cfg.get("text_color") or "ffffff")
        self.bg_color = hex_to_rgb(cfg.get("bg_color") or "000000")
        self.effect = (cfg.get("effect") or "none").strip().lower()
        self.flash_duration = max(0.05, float(cfg.get("flash_duration_sec") or 0.15))
        self.flash_repeat = int(cfg.get("flash_repeat") or 3)
        self.flash_text_rgb = hex_to_rgb(cfg.get("flash_text_color") or "000000")
        self.flash_bg_rgb = hex_to_rgb(cfg.get("flash_bg_color") or "ffffff")
        self.flash_color_rgb = hex_to_rgb(cfg.get("flash_color") or "ffffff")
        fc2 = (cfg.get("flash_color2") or "").strip()
        self.flash_color2_rgb = hex_to_rgb(fc2) if fc2 else None
        self.devices_raw = (cfg.get("devices") or "auto").strip().lower()

        # Resolve and cache font
        self.font_path = resolve_font_path(cfg)
        self.font = load_font(self.font_path, self.font_size, self.font_width)

    def render(self, txt: str, text_col: tuple, bg_col: tuple, w: int, h: int) -> str:
        """Render text using cached font. Returns path to temp PNG."""
        return render_text_to_image(
            txt, w, h,
            font=self.font,
            y_offset=self.y_offset,
            crisp=self.crisp,
            text_color=text_col,
            bg_color=bg_col,
        )


# ── Main Loop ─────────────────────────────────────────────────────────


def run_display_loop(config_path: str | None = None, dry_run: bool = False) -> None:
    if config_path is None:
        config_path = os.environ.get("CONFIG_PATH") or os.path.join(get_rpi_dir(), "config.json")

    cfg, _ = load_config_with_fallback(config_path)
    dcfg = DisplayConfig(cfg)
    config_mtime = os.path.getmtime(config_path) if os.path.isfile(config_path) else 0.0

    w = DEFAULT_WIDTH
    h = DEFAULT_HEIGHT
    clients: list = []
    reconn: ReconnectState | None = None

    # Clear stale errors from previous run
    write_status(last_error="", api_ok=True, ble_connected=0, ble_addresses=[])

    if dry_run:
        import shutil
        preview_dir = os.path.join(get_rpi_dir(), "preview")
        os.makedirs(preview_dir, exist_ok=True)
        clients = [None]  # sentinel so loop runs
        current_count: list[int | None] = [None]
        log.info("Dry run: no BLE, saving frames to %s/", preview_dir)
        log.info("API: %s", dcfg.api_url)
        log.info("Display: %dx%d | Font: %s", w, h, dcfg.font_path)

        def send_and_reconnect(path: str, cleanup: bool = True) -> list:
            dest = os.path.join(preview_dir, "latest.png")
            shutil.copy2(path, dest)
            n = current_count[0]
            if n is not None:
                shutil.copy2(path, os.path.join(preview_dir, f"count_{n}.png"))
            if cleanup:
                _cleanup_file(path)
            return [None]

        def force_reconnect(c: list) -> list:
            return c
    else:
        addresses, is_auto = resolve_device_addresses(cfg)
        if not addresses:
            log.warning("No devices found yet. Will keep retrying...")
        else:
            log.info("Connecting to %d device(s)...", len(addresses))
        log.info("API: %s", dcfg.api_url)
        if addresses:
            clients = connect_to_addresses(addresses)
        if clients:
            try:
                info = clients[0].get_device_info()
                w, h = info.width, info.height
            except Exception:
                pass
        reconn = ReconnectState(addresses, is_auto)
        log.info("Display: %dx%d | Font: %s | Connected: %d/%d",
                 w, h, dcfg.font_path.split("/")[-1], len(clients), len(addresses))

        def send_and_reconnect(path: str, cleanup: bool = True) -> list:
            nonlocal clients
            clients = send_image_to_clients(clients, path, cleanup=cleanup)
            clients = reconn.maybe_reconnect(clients)
            return clients

        def force_reconnect(c: list) -> list:
            return reconn.force_reconnect(c)

    prev_count: int | None = None
    last_sent_text: str | None = None   # track what's on display to skip redundant sends
    last_status_write: float = 0.0      # throttle status.json writes
    STATUS_WRITE_INTERVAL = 10.0        # write status at most every 10s (unless count changes)
    api_was_down: bool = False           # track API state for error clearing

    try:
        while True:
            loop_start = time.monotonic()

            # ── Hot config reload ─────────────────────────────────────
            try:
                new_mtime = os.path.getmtime(config_path)
                if new_mtime != config_mtime:
                    config_mtime = new_mtime
                    old_devices = dcfg.devices_raw
                    cfg, _ = load_config_with_fallback(config_path)
                    dcfg = DisplayConfig(cfg)
                    log.info("Config reloaded (font=%s size=%d effect=%s poll=%.1fs)",
                             dcfg.font_path.split("/")[-1], dcfg.font_size,
                             dcfg.effect, dcfg.poll_interval)
                    last_sent_text = None  # Force re-render with new settings
                    if not dry_run and dcfg.devices_raw != old_devices:
                        log.info("Device config changed (%s), reconnecting BLE...", dcfg.devices_raw)
                        disconnect_all(clients)
                        addresses, is_auto = resolve_device_addresses(cfg)
                        clients = connect_to_addresses(addresses) if addresses else []
                        reconn = ReconnectState(addresses, is_auto)
            except Exception as e:
                log.debug("Config check: %s", e)

            # ── Reconnect dropped displays ────────────────────────────
            clients = force_reconnect(clients)
            if not clients:
                time.sleep(dcfg.poll_interval)
                continue

            # ── Poll API ──────────────────────────────────────────────
            count = fetch_count(dcfg.api_url)
            if dry_run:
                current_count[0] = count
            text_to_show = dcfg.display_string if dcfg.display_string else (
                f"{count}{dcfg.suffix}" if count is not None else "--"
            )

            if count is not None or dcfg.display_string:
                # ── Clear error on recovery ───────────────────────────
                if api_was_down and count is not None:
                    log.info("API recovered, clearing error status")
                    write_status(last_error="", api_ok=True)
                    api_was_down = False

                count_incremented = (
                    dcfg.effect in ("invert", "screen")
                    and not dcfg.display_string
                    and count is not None
                    and prev_count is not None
                    and count > prev_count
                )

                if count_incremented and dcfg.effect == "invert":
                    with PerfTimer("Flash animation (invert)", warn_ms=5000):
                        flash_img = dcfg.render(text_to_show, dcfg.flash_text_rgb, dcfg.flash_bg_rgb, w, h)
                        normal_img = dcfg.render(text_to_show, dcfg.text_color, dcfg.bg_color, w, h)
                        for _ in range(dcfg.flash_repeat):
                            send_and_reconnect(flash_img, cleanup=False)
                            time.sleep(dcfg.flash_duration)
                            send_and_reconnect(normal_img, cleanup=False)
                            time.sleep(dcfg.flash_duration)
                        _cleanup_file(flash_img)
                        _cleanup_file(normal_img)
                    # Reconnect any display that dropped during the flash, then resend normal frame
                    if not dry_run and reconn is not None:
                        clients = reconn.maybe_reconnect(clients)
                        send_and_reconnect(dcfg.render(text_to_show, dcfg.text_color, dcfg.bg_color, w, h))
                    last_sent_text = text_to_show

                elif count_incremented and dcfg.effect == "screen":
                    with PerfTimer("Flash animation (screen)", warn_ms=5000):
                        normal_img = dcfg.render(text_to_show, dcfg.text_color, dcfg.bg_color, w, h)
                        flash_paths = [save_solid_image(w, h, dcfg.flash_color_rgb)]
                        if dcfg.flash_color2_rgb:
                            flash_paths.append(save_solid_image(w, h, dcfg.flash_color2_rgb))
                        for _ in range(dcfg.flash_repeat):
                            for fp in flash_paths:
                                send_and_reconnect(fp, cleanup=False)
                                time.sleep(dcfg.flash_duration)
                            send_and_reconnect(normal_img, cleanup=False)
                            time.sleep(dcfg.flash_duration)
                        for fp in flash_paths:
                            _cleanup_file(fp)
                        _cleanup_file(normal_img)
                    # Reconnect any display that dropped during the flash, then resend normal frame
                    if not dry_run and reconn is not None:
                        clients = reconn.maybe_reconnect(clients)
                        send_and_reconnect(dcfg.render(text_to_show, dcfg.text_color, dcfg.bg_color, w, h))
                    last_sent_text = text_to_show

                # Only render+send if the displayed text actually changed
                if text_to_show != last_sent_text:
                    send_and_reconnect(dcfg.render(text_to_show, dcfg.text_color, dcfg.bg_color, w, h))
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
                        write_status(last_error="", last_count=count, api_ok=True,
                                     ble_connected=ble_count, ble_addresses=ble_addrs)
                        last_status_write = now
            else:
                # API unreachable: show last or "--"
                api_was_down = True
                fallback_text = f"{prev_count}{dcfg.suffix}" if prev_count is not None else "--"
                if fallback_text != last_sent_text:
                    send_and_reconnect(dcfg.render(fallback_text, dcfg.text_color, dcfg.bg_color, w, h))
                    last_sent_text = fallback_text
                # Throttle error status writes too
                now = time.monotonic()
                if (now - last_status_write) >= STATUS_WRITE_INTERVAL:
                    err_detail = f"API unreachable: {_last_api_error}" if _last_api_error else "API unreachable"
                    write_status(last_error=err_detail, api_ok=False)
                    last_status_write = now

            # ── Loop timing ───────────────────────────────────────────
            elapsed = time.monotonic() - loop_start
            sleep_time = max(0.05, dcfg.poll_interval - elapsed)
            if elapsed > dcfg.poll_interval * 2:
                log.warning("Loop iteration slow: %.0fms (target: %.0fms)",
                            elapsed * 1000, dcfg.poll_interval * 1000)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        log.info("Stopped (KeyboardInterrupt)")
    finally:
        if not dry_run:
            disconnect_all(clients)
        BLE_THREAD_POOL.shutdown(wait=False)


def main() -> None:
    import argparse

    setup_logging()

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
