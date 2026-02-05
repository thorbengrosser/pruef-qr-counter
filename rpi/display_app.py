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
    sys.exit(1)

DISPLAY_SLOT = 1
DEFAULT_DEVICE_PREFIX = "LED_BLE_"
RECONNECT_COOLDOWN_SEC = 5
DEFAULT_WIDTH, DEFAULT_HEIGHT = 64, 16


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


def render_text_to_image(
    text: str,
    width: int,
    height: int,
    *,
    font_path: str,
    font_size: int = 16,
    font_width: float | None = None,
    y_offset: int = 0,
    crisp: bool = False,
    text_color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 0),
) -> str:
    """Render text to image. Returns path to temp PNG. font_width: variable font width axis (e.g. 100 for Kario)."""
    font = ImageFont.truetype(font_path, min(128, max(6, font_size)))
    apply_variable_font_axes(font, width=font_width)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    draw.text(
        (width // 2, height // 2 + y_offset),
        text, fill=text_color, font=font, anchor="mm"
    )

    if crisp:
        pixels = img.load()
        for y in range(height):
            for x in range(width):
                px = pixels[x, y]
                d_text = sum((a - b) ** 2 for a, b in zip(px, text_color))
                d_bg = sum((a - b) ** 2 for a, b in zip(px, bg_color))
                pixels[x, y] = text_color if d_text <= d_bg else bg_color

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path)
    return path


def save_solid_image(width: int, height: int, color: tuple[int, int, int]) -> str:
    img = Image.new("RGB", (width, height), color)
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path)
    return path


async def scan_led_devices(prefix: str = DEFAULT_DEVICE_PREFIX) -> list[tuple[str, str]]:
    devices = await BleakScanner.discover(timeout=5.0)
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


def fetch_count(api_url: str) -> int | None:
    try:
        r = requests.get(api_url, timeout=5)
        r.raise_for_status()
        write_status(last_error=None, api_ok=True)
        return int(r.json().get("count", 0))
    except Exception as e:
        write_status(last_error=f"API unreachable: {e}", api_ok=False)
        print(f"API error: {e}", file=sys.stderr)
        return None


def disconnect_all(clients: list) -> None:
    for c in clients:
        try:
            c.disconnect()
        except Exception:
            pass


def reconnect_clients(
    addresses: list[str], is_auto: bool, old_clients: list | None = None
) -> tuple[list, list[str]]:
    if old_clients:
        disconnect_all(old_clients)
    if is_auto:
        found = asyncio.run(scan_led_devices())
        addresses = [addr for _name, addr in found]
        if addresses:
            print(f"Re-scan: found {len(addresses)} device(s): {addresses}", file=sys.stderr)
    clients = []
    for addr in addresses:
        try:
            c = pypixelcolor.Client(addr)
            c.connect()
            clients.append(c)
        except Exception as e:
            print(f"Reconnect {addr}: {e}", file=sys.stderr)
    return (clients, addresses)


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


class ReconnectState:
    def __init__(self, addresses: list[str], is_auto: bool):
        self.addresses = addresses
        self.is_auto = is_auto
        self.last_reconnect = time.monotonic()

    def maybe_reconnect(self, clients: list) -> list:
        if len(clients) < len(self.addresses) and (time.monotonic() - self.last_reconnect) >= RECONNECT_COOLDOWN_SEC:
            clients, self.addresses = reconnect_clients(self.addresses, self.is_auto, clients)
            self.last_reconnect = time.monotonic()
        return clients

    def force_reconnect(self, clients: list) -> list:
        if not clients and (time.monotonic() - self.last_reconnect) >= RECONNECT_COOLDOWN_SEC:
            print("Reconnecting...", file=sys.stderr)
            clients, self.addresses = reconnect_clients(self.addresses, self.is_auto, clients)
            self.last_reconnect = time.monotonic()
        return clients


def run_display_loop(config_path: str | None = None, dry_run: bool = False) -> None:
    cfg = load_config(config_path)
    font_path = resolve_font_path(cfg)
    api_url = (cfg.get("api_url") or "https://pruef.st/api/count").strip()
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
            print("No devices configured (devices: auto or comma-separated addresses).", file=sys.stderr)
            sys.exit(1)
        print(f"Connecting to {len(addresses)} device(s)...", file=sys.stderr)
        print(f"API: {api_url}", file=sys.stderr)
        clients, addresses = reconnect_clients(addresses, is_auto)
        if not clients:
            print("Could not connect to any display.", file=sys.stderr)
            sys.exit(1)
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

    def render(txt: str, text_col: tuple, bg_col: tuple) -> str:
        return render_text_to_image(
            txt, w, h,
            font_path=font_path,
            font_size=font_size,
            font_width=font_width,
            y_offset=y_offset,
            crisp=crisp,
            text_color=text_col,
            bg_color=bg_col,
        )

    prev_count: int | None = None
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

                send_and_reconnect(render(text_to_show, text_color, bg_color))

                if count is not None:
                    prev_count = count
                    if dry_run:
                        ble_addrs = []
                        ble_count = 0
                    else:
                        ble_addrs = [c.address for c in clients if hasattr(c, "address")]
                        ble_count = len([c for c in clients if c is not None])
                    write_status(last_count=count, ble_connected=ble_count, ble_addresses=ble_addrs)
            else:
                # API unreachable: show last or "--"
                if prev_count is not None:
                    send_and_reconnect(render(f"{prev_count}{suffix}", text_color, bg_color))
                else:
                    send_and_reconnect(render("--", text_color, bg_color))

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
