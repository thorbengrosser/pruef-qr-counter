#!/usr/bin/env python3
"""Convert hex dump from ESP32 serial to PNG file.

Usage:
  1. In esp32/include/config.h set DEBUG_PNG_DUMP 1, flash, run.
  2. Capture serial: cd esp32 && pio device monitor 2>&1 | tee ../testing/serial.log
  3. Wait for count (PNG dump on first send), Ctrl+C.
  4. cd testing && python scripts/hex_to_png.py esp32.png < serial.log
"""
import re
import sys
import binascii


def main():
    if len(sys.argv) < 2:
        print("Usage: hex_to_png.py OUTPUT.png [INPUT.hex | < serial.log]", file=sys.stderr)
        sys.exit(1)

    out_path = sys.argv[1]
    input_path = sys.argv[2] if len(sys.argv) > 2 else None
    if input_path:
        with open(input_path) as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()

    # Find hex block between PNG_HEX_START and PNG_HEX_END
    hex_lines = []
    in_block = False
    for line in lines:
        line = line.strip()
        if "PNG_HEX_START" in line:
            in_block = True
            continue
        if "PNG_HEX_END" in line:
            break
        if in_block and line:
            hex_part = re.sub(r"[^0-9a-fA-F]", "", line)
            if hex_part:
                hex_lines.append(hex_part)

    # No delimiters - treat whole file as raw hex (e.g. esp32/test/dump.hex)
    if not hex_lines:
        hex_lines = [re.sub(r"[^0-9a-fA-F]", "", ln) for ln in lines if ln.strip()]

    if not hex_lines:
        print("No PNG hex data found.", file=sys.stderr)
        sys.exit(1)

    hex_str = "".join(hex_lines).replace(" ", "")
    try:
        data = binascii.unhexlify(hex_str)
    except binascii.Error as e:
        print(f"Invalid hex: {e}", file=sys.stderr)
        sys.exit(1)

    if data[:8] != bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]):
        print("Warning: data does not start with PNG signature", file=sys.stderr)

    with open(out_path, "wb") as f:
        f.write(data)

    print(f"Wrote {len(data)} bytes to {out_path}")


if __name__ == "__main__":
    main()
