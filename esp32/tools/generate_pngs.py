#!/usr/bin/env python3
"""
Pre-generate PIL-encoded PNGs for counts 0-99. Device accepts PIL PNGs; our
runtime miniz PNGs show black. Output: esp32/include/png_frames.h
Run from project root: python esp32/tools/generate_pngs.py [options]

Flash colors (hex RRGGBB, same as Python POC):
  --flash-color       Screen flash color 1 (default: ffffff)
  --flash-color2      Screen flash color 2 for alternating (default: none)
  --flash-text-color  Invert flash: text color (default: 000000)
  --flash-bg-color    Invert flash: background color (default: ffffff)
"""

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
TESTING_DIR = os.path.join(PROJECT_ROOT, "testing")
FONT_PATH = os.path.join(TESTING_DIR, "Kario39C3Var-Roman.ttf")
OUTPUT_HEADER = os.path.join(PROJECT_ROOT, "esp32", "include", "png_frames.h")

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Install Pillow: pip install Pillow")
    sys.exit(1)

WIDTH, HEIGHT = 64, 16
FONT_SIZE = 22
FONT_WIDTH = 50
Y_OFFSET = 1
SUFFIX = " x"
TEXT_COLOR = (255, 255, 255)
BG_COLOR = (0, 0, 0)
MAX_COUNT = 99  # 0-99


def hex_to_rgb(hex_str: str) -> tuple:
    """Parse hex RRGGBB to (r, g, b) tuple."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) != 6:
        raise ValueError(f"Expected 6 hex digits, got: {hex_str}")
    return (
        int(hex_str[0:2], 16),
        int(hex_str[2:4], 16),
        int(hex_str[4:6], 16),
    )


def apply_variable_font_axes(font, width=None):
    try:
        axes = font.get_variation_axes()
        values = []
        for ax in axes:
            tag = (ax.get("tag") or b"").decode("utf-8", errors="ignore").lower()
            values.append(width if width is not None and tag == "wdth" else ax["default"])
        font.set_variation_by_axes(values)
    except (OSError, AttributeError):
        pass


def render_png(count: int, text_color=None, bg_color=None) -> bytes:
    """Render count PNG with optional color override for flash animations."""
    if text_color is None:
        text_color = TEXT_COLOR
    if bg_color is None:
        bg_color = BG_COLOR
    
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    apply_variable_font_axes(font, FONT_WIDTH)

    text = f"{count}{SUFFIX}"
    img = Image.new("RGB", (WIDTH, HEIGHT), bg_color)
    draw = ImageDraw.Draw(img)
    draw.text(
        (WIDTH // 2, HEIGHT // 2 + Y_OFFSET),
        text, fill=text_color, font=font, anchor="mm"
    )

    # Crisp: color-aware binarization
    pixels = img.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            px = pixels[x, y]
            d_text = sum((a - b) ** 2 for a, b in zip(px, text_color))
            d_bg = sum((a - b) ** 2 for a, b in zip(px, bg_color))
            pixels[x, y] = text_color if d_text <= d_bg else bg_color

    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_solid_png(color: tuple) -> bytes:
    """Render solid color PNG for screen flash."""
    img = Image.new("RGB", (WIDTH, HEIGHT), color)
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def parse_args():
    p = argparse.ArgumentParser(description="Generate PNG frames for ESP32 display")
    p.add_argument("--flash-color", default="ffffff", metavar="RRGGBB",
                   help="Screen flash color 1 (default: ffffff)")
    p.add_argument("--flash-color2", default=None, metavar="RRGGBB",
                   help="Screen flash color 2 for alternating (optional)")
    p.add_argument("--flash-text-color", default="000000", metavar="RRGGBB",
                   help="Invert flash: text color (default: 000000)")
    p.add_argument("--flash-bg-color", default="ffffff", metavar="RRGGBB",
                   help="Invert flash: background color (default: ffffff)")
    args = p.parse_args()

    flash_color = hex_to_rgb(args.flash_color)
    flash_color2 = hex_to_rgb(args.flash_color2) if args.flash_color2 else None
    flash_text_color = hex_to_rgb(args.flash_text_color)
    flash_bg_color = hex_to_rgb(args.flash_bg_color)
    return flash_color, flash_color2, flash_text_color, flash_bg_color


def main():
    flash_color, flash_color2, flash_text_color, flash_bg_color = parse_args()

    if not os.path.isfile(FONT_PATH):
        print(f"Font not found: {FONT_PATH}")
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_HEADER), exist_ok=True)
    pngs = []
    # Normal frames: 0-99
    for i in range(MAX_COUNT + 1):
        data = render_png(i)
        pngs.append(data)
        if i == 0:
            print(f"Sample PNG size: {len(data)} bytes")
    
    # Flash frames: invert flash (swapped colors) for each count
    flash_invert_pngs = []
    for i in range(MAX_COUNT + 1):
        data = render_png(i, text_color=flash_text_color, bg_color=flash_bg_color)
        flash_invert_pngs.append(data)
    
    # Flash frames: screen flash (solid colors)
    flash_screen_pngs = [render_solid_png(flash_color)]
    if flash_color2:
        flash_screen_pngs.append(render_solid_png(flash_color2))
    
    def hex_fmt(c):
        return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"
    print(f"Flash colors: screen={hex_fmt(flash_color)}{('+' + hex_fmt(flash_color2)) if flash_color2 else ''}, invert={hex_fmt(flash_text_color)} on {hex_fmt(flash_bg_color)}")
    print(f"Generated {len(pngs)} normal, {len(flash_invert_pngs)} invert flash, {len(flash_screen_pngs)} screen flash frames")

    # Combine all PNGs: normal frames first, then invert flash, then screen flash
    all_pngs = pngs + flash_invert_pngs + flash_screen_pngs
    normal_count = len(pngs)
    invert_count = len(flash_invert_pngs)
    screen_count = len(flash_screen_pngs)
    
    with open(OUTPUT_HEADER, "w") as f:
        f.write("// Auto-generated by tools/generate_pngs.py - do not edit\n")
        f.write("#ifndef PNG_FRAMES_H\n#define PNG_FRAMES_H\n#include <stdint.h>\n\n")
        f.write(f"#define PNG_FRAME_COUNT {normal_count}\n")
        f.write(f"#define PNG_FLASH_INVERT_COUNT {invert_count}\n")
        f.write(f"#define PNG_FLASH_SCREEN_COUNT {screen_count}\n")
        f.write(f"#define PNG_MAX_LEN 256\n\n")

        # Offsets: start index of each PNG in PNG_DATA
        f.write("static const uint16_t PNG_OFFSETS[] = {\n")
        pos = 0
        for i, data in enumerate(all_pngs):
            f.write(f"  {pos}" + ("," if i < len(all_pngs) - 1 else "") + "\n")
            pos += len(data)
        f.write("};\n\n")

        f.write("static const uint16_t PNG_LENS[] = {\n")
        for i, data in enumerate(all_pngs):
            f.write(f"  {len(data)}" + ("," if i < len(all_pngs) - 1 else "") + "\n")
        f.write("};\n\n")

        f.write("static const uint8_t PNG_DATA[] = {\n")
        for i, data in enumerate(all_pngs):
            comment = ""
            if i < normal_count:
                comment = f"/* normal {i} */"
            elif i < normal_count + invert_count:
                comment = f"/* invert flash {i - normal_count} */"
            else:
                comment = f"/* screen flash {i - normal_count - invert_count} */"
            f.write(f"  {comment} ")
            hex_bytes = ", ".join(f"0x{b:02x}" for b in data)
            # Wrap long lines
            remaining = hex_bytes
            while len(remaining) > 70:
                idx = remaining[:70].rfind(", ")
                if idx < 0:
                    break
                f.write(remaining[: idx + 1] + "\n  ")
                remaining = remaining[idx + 2 :].lstrip()
            f.write(remaining)
            f.write(",\n" if i < len(all_pngs) - 1 else "\n")
        f.write("};\n\n")

        # Normal frame lookup
        f.write("static inline const uint8_t* pngForCount(uint32_t count, size_t *len) {\n")
        f.write("  if (count > PNG_FRAME_COUNT - 1) count = PNG_FRAME_COUNT - 1;\n")
        f.write("  uint16_t idx = (uint16_t)count;\n")
        f.write("  *len = PNG_LENS[idx];\n")
        f.write("  return PNG_DATA + PNG_OFFSETS[idx];\n")
        f.write("}\n\n")
        
        # Invert flash lookup
        f.write("static inline const uint8_t* pngForInvertFlash(uint32_t count, size_t *len) {\n")
        f.write("  if (count > PNG_FRAME_COUNT - 1) count = PNG_FRAME_COUNT - 1;\n")
        f.write("  uint16_t idx = PNG_FRAME_COUNT + (uint16_t)count;\n")
        f.write("  *len = PNG_LENS[idx];\n")
        f.write("  return PNG_DATA + PNG_OFFSETS[idx];\n")
        f.write("}\n\n")
        
        # Screen flash lookup
        f.write("static inline const uint8_t* pngForScreenFlash(uint8_t index, size_t *len) {\n")
        f.write("  if (index >= PNG_FLASH_SCREEN_COUNT) index = PNG_FLASH_SCREEN_COUNT - 1;\n")
        f.write("  uint16_t idx = PNG_FRAME_COUNT + PNG_FLASH_INVERT_COUNT + index;\n")
        f.write("  *len = PNG_LENS[idx];\n")
        f.write("  return PNG_DATA + PNG_OFFSETS[idx];\n")
        f.write("}\n\n")
        
        f.write("#endif\n")

    total_bytes = sum(len(p) for p in all_pngs)
    print(f"Wrote {OUTPUT_HEADER} ({total_bytes} bytes total)")


if __name__ == "__main__":
    main()
