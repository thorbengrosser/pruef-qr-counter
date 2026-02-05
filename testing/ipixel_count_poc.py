#!/usr/bin/env python3
"""
Display count on iPixel LED matrix, updating from web-app API.

Usage:
  export BLE_DEVICE_ADDRESS="xx:xx:xx:xx:xx:xx"   # Single device (legacy)
  python ipixel_count_poc.py --devices auto       # Auto-discover LED_BLE_* devices
  python ipixel_count_poc.py -d "addr1,addr2"     # Multiple explicit addresses
  python ipixel_count_poc.py --scan               # List LED_BLE_* devices and exit
  python ipixel_count_poc.py --font-path Kario39C3Var-Roman.ttf --font-size 22 --y-offset 1 --crisp
  python ipixel_count_poc.py --list-variations Kario39C3Var-Roman.ttf  # List variable font axes
"""

import argparse
import asyncio
import os
import shutil
import sys
import tempfile
import time

try:
    import pypixelcolor
    import requests
    from PIL import Image, ImageDraw, ImageFont
    from bleak import BleakScanner
except ImportError as e:
    print("Missing dependencies: pip install -r requirements.txt")
    sys.exit(1)

# Config from environment
BLE_ADDRESS = os.environ.get("BLE_DEVICE_ADDRESS", "")
DEFAULT_DEVICE_PREFIX = "LED_BLE_"
API_BASE_URL = os.environ.get("API_BASE_URL", "https://pruef.st").rstrip("/")
UPDATE_INTERVAL_SEC = 1
DISPLAY_SLOT = 1
FLASH_DURATION_SEC = 0.15
FLASH_REPEAT = 3


def resolve_font_path(path: str) -> str:
    """Resolve font path (absolute, cwd, or relative to script)."""
    for p in (
        os.path.abspath(os.path.expanduser(path)),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), path),
    ):
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(f"Font not found: {path}")


def get_builtin_font_path(name: str) -> str:
    """Path to pypixelcolor built-in font."""
    fonts_dir = os.path.join(os.path.dirname(pypixelcolor.__file__), "fonts")
    p = os.path.join(fonts_dir, f"{name}.ttf")
    return p if os.path.exists(p) else os.path.join(fonts_dir, "VCR_OSD_MONO.ttf")


def scan_led_devices(prefix: str = DEFAULT_DEVICE_PREFIX) -> list[tuple[str, str]]:
    """Scan for BLE devices whose name starts with prefix. Returns [(name, address), ...]."""

    async def _scan():
        devices = await BleakScanner.discover(timeout=5.0)
        return [
            (d.name or "?", d.address)
            for d in devices
            if d.name and d.name.startswith(prefix)
        ]

    return asyncio.run(_scan())


def resolve_device_addresses(args) -> tuple[list[str], bool]:
    """Resolve list of BLE addresses from args and env. Returns (addresses, is_auto)."""
    devices_arg = getattr(args, "devices", None)
    if devices_arg:
        if str(devices_arg).strip().lower() == "auto":
            found = scan_led_devices()
            addrs = [addr for _name, addr in found]
            if not addrs:
                print("No devices found with name prefix LED_BLE_. Run --scan to verify.")
                sys.exit(1)
            print(f"Auto-discovered {len(addrs)} device(s): {addrs}")
            return (addrs, True)
        return ([a.strip() for a in str(devices_arg).split(",") if a.strip()], False)
    if BLE_ADDRESS:
        return ([BLE_ADDRESS], False)
    return ([], False)


def fetch_count(api_url: str) -> int | None:
    """Fetch count from API. Returns None on error."""
    try:
        r = requests.get(api_url, timeout=5)
        r.raise_for_status()
        return int(r.json().get("count", 0))
    except Exception as e:
        print(f"API error: {e}")
        return None


def list_variable_font_info(font_path: str) -> None:
    """Print axes and named instances for a variable font."""
    try:
        path = resolve_font_path(font_path)
        font = ImageFont.truetype(path, 16)
        axes = font.get_variation_axes()
        names = font.get_variation_names()
    except FileNotFoundError as e:
        print(e)
        return
    except Exception as e:
        print(f"Error: {e}")
        return

    if not axes and not names:
        print("Not a variable font")
        return

    print("Axes:")
    for ax in axes:
        n = (ax.get("name") or b"").decode("utf-8", errors="ignore")
        print(f"  {n} {ax['minimum']}–{ax['maximum']}, default {ax['default']}")

    if names:
        print("\nNamed instances:")
        for n in names:
            print(f"  {n.decode('utf-8', errors='ignore')}")


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert hex color (e.g. ffffff or #ffffff) to RGB tuple."""
    h = hex_str.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hex_str}")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _apply_variable_font_axes(font, *, weight=None, width=None, optical_size=None, instance=None):
    """Apply variable font axes. No-op for non-variable fonts."""
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
    font_weight: float | None = None,
    font_width: float | None = None,
    font_optical_size: float | None = None,
    font_instance: str | None = None,
    y_offset: int = 0,
    crisp: bool = False,
    text_color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 0),
) -> str:
    """Render text to image. Returns path to temp PNG."""
    font = ImageFont.truetype(font_path, min(128, max(6, font_size)))
    _apply_variable_font_axes(
        font, weight=font_weight, width=font_width,
        optical_size=font_optical_size, instance=font_instance
    )

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    draw.text(
        (width // 2, height // 2 + y_offset),
        text, fill=text_color, font=font, anchor="mm"
    )

    if crisp:
        # Color-aware binarization: each pixel → text_color or bg_color (no luminance threshold)
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


def _save_solid_image(width: int, height: int, color: tuple[int, int, int]) -> str:
    """Create solid color image, save to temp file, return path."""
    img = Image.new("RGB", (width, height), color)
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path)
    return path


RECONNECT_COOLDOWN_SEC = 5


def _disconnect_all(clients: list) -> None:
    """Safely disconnect all clients."""
    for c in clients:
        try:
            c.disconnect()
        except Exception:
            pass


def _reconnect_clients(addresses: list[str], is_auto: bool, old_clients: list | None = None) -> tuple[list, list[str]]:
    """Re-scan (if auto) or reuse addresses, create clients, connect. Returns (clients, addresses)."""
    if old_clients:
        _disconnect_all(old_clients)
    if is_auto:
        found = scan_led_devices()
        addresses = [addr for _name, addr in found]
        if addresses:
            print(f"Re-scan: found {len(addresses)} device(s): {addresses}")
        else:
            print("Re-scan: no devices found")
    clients = []
    for addr in addresses:
        try:
            c = pypixelcolor.Client(addr)
            c.connect()
            clients.append(c)
        except Exception as e:
            print(f"Reconnect {addr}: {e}")
    return (clients, addresses)


def _send_image_to_clients(clients: list, path: str, cleanup: bool = True) -> list:
    """Send image to all clients. Returns list of clients that succeeded (failed ones removed)."""
    working = []
    for c in clients:
        try:
            c.send_image(path, save_slot=DISPLAY_SLOT)
            c.show_slot(DISPLAY_SLOT)
            working.append(c)
        except Exception as e:
            print(f"Display disconnected: {e}")
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
    """Tracks reconnection state and handles reconnect logic."""

    def __init__(self, addresses: list[str], is_auto: bool):
        self.addresses = addresses
        self.is_auto = is_auto
        self.last_reconnect = time.monotonic()

    def maybe_reconnect(self, clients: list) -> list:
        """Reconnect if clients dropped and cooldown passed. Returns updated clients."""
        if len(clients) < len(self.addresses) and self._cooldown_passed():
            clients, self.addresses = _reconnect_clients(self.addresses, self.is_auto, clients)
            self.last_reconnect = time.monotonic()
        return clients

    def force_reconnect(self, clients: list) -> list:
        """Force reconnect if cooldown passed. Returns updated clients."""
        if not clients and self._cooldown_passed():
            print("Reconnecting...")
            clients, self.addresses = _reconnect_clients(self.addresses, self.is_auto, clients)
            self.last_reconnect = time.monotonic()
        return clients

    def _cooldown_passed(self) -> bool:
        return (time.monotonic() - self.last_reconnect) >= RECONNECT_COOLDOWN_SEC


def parse_args():
    p = argparse.ArgumentParser(description="Display count on iPixel from web-app API")
    p.add_argument("--list-variations", metavar="FONT", help="List variable font info and exit")
    p.add_argument("--scan", action="store_true", help="Scan for LED_BLE_* devices and exit")
    p.add_argument("-d", "--devices", metavar="ADDRS",
                   help="Devices: 'auto' to discover LED_BLE_*, or comma-separated addresses (e.g. addr1,addr2)")

    # Display
    p.add_argument("--suffix", default=" x", help="Suffix after count")
    p.add_argument("--text", metavar="STR", help="Override text (runs once)")
    p.add_argument("--text-color", default="ffffff", metavar="HEX", help="Text color (hex, default: ffffff)")
    p.add_argument("--bg-color", default="000000", metavar="HEX", help="Background color (hex, default: 000000)")
    p.add_argument("--inverse", action="store_true", help="Swap text and background colors")

    # Mode
    p.add_argument("--use-text", action="store_true", help="Use send_text instead of image")

    # Font
    p.add_argument("--font", default="VCR_OSD_MONO", choices=["CUSONG", "SIMSUN", "VCR_OSD_MONO"])
    p.add_argument("--font-path", help="Custom .ttf/.otf path")
    p.add_argument("--font-size", type=int, help="Font size in px")
    p.add_argument("--font-weight", type=float, help="Variable font weight axis")
    p.add_argument("--font-width", type=float, help="Variable font width axis (e.g. 100 for Kario)")
    p.add_argument("--font-optical-size", type=float, help="Variable font optical size axis")
    p.add_argument("--font-instance", help="Variable font named instance")

    # Image mode only
    p.add_argument("--y-offset", type=int, default=2, help="Vertical offset (default: 2)")
    p.add_argument("--crisp", action="store_true", help="Binarize for hard edges")
    p.add_argument("--char-height", type=int, help="[--use-text] Character height")
    p.add_argument("--flash", choices=["invert", "screen"], help="Flash on increment: invert colors or full-screen")
    p.add_argument("--flash-duration", type=float, default=0.15, metavar="SEC", help="Duration of each flash state (default: 0.15)")
    p.add_argument("--flash-color", default="ffffff", metavar="HEX", help="Screen flash color (default: ffffff)")
    p.add_argument("--flash-color2", metavar="HEX", help="Screen flash: alternate color (e.g. red+blue with ff0000,0000ff)")
    p.add_argument("--flash-text-color", metavar="HEX", help="Invert flash: text color (default: swapped bg)")
    p.add_argument("--flash-bg-color", metavar="HEX", help="Invert flash: background color (default: swapped text)")

    # Timing
    p.add_argument("--interval", type=float, default=1.0, metavar="SEC", help="Update interval in seconds (default: 1.0)")

    # Debug
    p.add_argument("--save-png", metavar="PATH", help="Render and save PNG to file (no BLE), use with --text")
    p.add_argument("--send-png", metavar="PATH", help="Send PNG file to display via BLE (e.g. esp32.png from hex_to_png)")

    return p.parse_args()


def main():
    args = parse_args()

    if args.list_variations:
        list_variable_font_info(args.list_variations)
        return

    if args.save_png:
        if not args.text:
            print("--save-png requires --text (e.g. --text 36)")
            sys.exit(1)
        api_url = f"{API_BASE_URL}/api/count"
        font_path = resolve_font_path(args.font_path) if args.font_path else get_builtin_font_path(args.font)
        text_color_rgb = _hex_to_rgb(args.text_color)
        bg_color_rgb = _hex_to_rgb(args.bg_color)
        if args.inverse:
            text_color_rgb, bg_color_rgb = bg_color_rgb, text_color_rgb
        path = render_text_to_image(
            f"{args.text}{args.suffix}", 64, 16,
            font_path=font_path,
            font_size=args.font_size or 16,
            font_weight=args.font_weight,
            font_width=args.font_width,
            font_optical_size=args.font_optical_size,
            font_instance=args.font_instance,
            y_offset=args.y_offset,
            crisp=args.crisp,
            text_color=text_color_rgb,
            bg_color=bg_color_rgb,
        )
        shutil.copy(path, args.save_png)
        try:
            os.unlink(path)
        except OSError:
            pass
        print(f"Saved reference PNG to {args.save_png}")
        return

    if args.send_png:
        if not os.path.isfile(args.send_png):
            print(f"File not found: {args.send_png}")
            sys.exit(1)
        resolve_args = argparse.Namespace(devices=getattr(args, "devices", None) or "auto")
        addresses, is_auto = resolve_device_addresses(resolve_args)
        if not addresses:
            print("No devices found. Use -d auto or -d addr1,addr2")
            sys.exit(1)
        clients, _ = _reconnect_clients(addresses, is_auto, [])
        if not clients:
            print("Could not connect to any display")
            sys.exit(1)
        _send_image_to_clients(clients, args.send_png, cleanup=False)
        for c in clients:
            try:
                c.disconnect()
            except Exception:
                pass
        print("Sent PNG to display")
        return

    if args.scan:
        print("Scanning for LED_BLE_* devices...")
        found = scan_led_devices()
        if found:
            print(f"Found {len(found)} device(s):")
            for name, addr in found:
                print(f"  {name}  {addr}")
        else:
            print("No devices found.")
        return

    addresses, is_auto = resolve_device_addresses(args)
    if not addresses:
        print("Provide devices via -d/--devices or BLE_DEVICE_ADDRESS.")
        sys.exit(1)

    api_url = f"{API_BASE_URL}/api/count"
    font_path = resolve_font_path(args.font_path) if args.font_path else get_builtin_font_path(args.font)

    text_color_rgb = _hex_to_rgb(args.text_color)
    bg_color_rgb = _hex_to_rgb(args.bg_color)
    if args.inverse:
        text_color_rgb, bg_color_rgb = bg_color_rgb, text_color_rgb
    text_color_hex = args.bg_color if args.inverse else args.text_color
    bg_color_hex = args.text_color if args.inverse else args.bg_color

    flash_duration = max(0.05, args.flash_duration)
    flash_color_rgb = _hex_to_rgb(args.flash_color)
    flash_color2_rgb = _hex_to_rgb(args.flash_color2) if args.flash_color2 else None
    flash_text_rgb = _hex_to_rgb(args.flash_text_color) if args.flash_text_color else bg_color_rgb
    flash_bg_rgb = _hex_to_rgb(args.flash_bg_color) if args.flash_bg_color else text_color_rgb

    print(f"Connecting to {len(addresses)} device(s)...")
    print(f"API: {api_url}")
    clients, addresses = _reconnect_clients(addresses, is_auto)
    if not clients:
        print("Could not connect to any device")
        sys.exit(1)
    w, h = clients[0].get_device_info().width, clients[0].get_device_info().height
    char_height = args.char_height if args.char_height is not None else h
    reconn = ReconnectState(addresses, is_auto)

    print(f"Display: {w}x{h} | Font: {font_path}\n")

    # Render helper with shared params
    def render(txt: str, text_col: tuple, bg_col: tuple) -> str:
        return render_text_to_image(
            txt, w, h,
            font_path=font_path,
            font_size=args.font_size or h,
            font_weight=args.font_weight,
            font_width=args.font_width,
            font_optical_size=args.font_optical_size,
            font_instance=args.font_instance,
            y_offset=args.y_offset,
            crisp=args.crisp,
            text_color=text_col,
            bg_color=bg_col,
        )

    def send_and_reconnect(path: str, cleanup: bool = True) -> list:
        nonlocal clients
        clients = _send_image_to_clients(clients, path, cleanup=cleanup)
        clients = reconn.maybe_reconnect(clients)
        return clients

    prev_count: int | None = None
    try:
        while True:
            clients = reconn.force_reconnect(clients)

            count = fetch_count(api_url)
            if count is not None or args.text:
                text = args.text if args.text else f"{count}{args.suffix}"
                print(f"{'Override' if args.text else f'Count {count}'}: {text}")

                if args.use_text:
                    working = []
                    for c in clients:
                        try:
                            c.send_text(
                                text, color=text_color_hex, bg_color=bg_color_hex,
                                animation=0, speed=80, save_slot=DISPLAY_SLOT,
                                char_height=char_height, font=args.font_path or args.font,
                            )
                            c.show_slot(DISPLAY_SLOT)
                            working.append(c)
                        except Exception as e:
                            print(f"Display disconnected: {e}")
                            try:
                                c.disconnect()
                            except Exception:
                                pass
                    clients = reconn.maybe_reconnect(working)
                else:
                    count_incremented = (
                        args.flash
                        and not args.text
                        and count is not None
                        and prev_count is not None
                        and count > prev_count
                    )

                    if count_incremented and args.flash == "invert":
                        flash_img = render(text, flash_text_rgb, flash_bg_rgb)
                        normal_img = render(text, text_color_rgb, bg_color_rgb)
                        for _ in range(FLASH_REPEAT):
                            send_and_reconnect(flash_img, cleanup=False)
                            time.sleep(flash_duration)
                            send_and_reconnect(normal_img, cleanup=False)
                            time.sleep(flash_duration)
                        try:
                            os.unlink(flash_img)
                            os.unlink(normal_img)
                        except OSError:
                            pass

                    elif count_incremented and args.flash == "screen":
                        normal_img = render(text, text_color_rgb, bg_color_rgb)
                        flash_paths = [_save_solid_image(w, h, flash_color_rgb)]
                        if flash_color2_rgb:
                            flash_paths.append(_save_solid_image(w, h, flash_color2_rgb))
                        for _ in range(FLASH_REPEAT):
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

                    send_and_reconnect(render(text, text_color_rgb, bg_color_rgb))

                if count is not None:
                    prev_count = count

                if args.text:
                    break
            else:
                print("API unreachable")

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        _disconnect_all(clients)


if __name__ == "__main__":
    main()
