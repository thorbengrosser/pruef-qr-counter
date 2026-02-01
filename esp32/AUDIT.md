# ESP32 Code Audit & Improvements

## Audit Date
February 1, 2026

## Summary
Comprehensive code audit of the ESP32 firmware, identifying design issues and implementing improvements including flash animation support.

## Issues Found & Fixed

### 1. **Memory Management**
- **Issue**: Static global `foundDevice` in `ipixel_ble.cpp` could leak if scan() was called multiple times without cleanup
- **Fix**: Added cleanup logic in `scan()` to delete previous device before allocating new one, and reset `scanPrefix` pointer

### 2. **Magic Numbers**
- **Issue**: Hardcoded delay values scattered throughout code (50ms, 500ms, 2000ms, etc.)
- **Fix**: Extracted all timing constants to named constants at top of `main.cpp`:
  - `WIFI_RECONNECT_INTERVAL_MS = 15000`
  - `WIFI_DISCONNECT_DELAY_MS = 100`
  - `SETUP_STABILIZE_DELAY_MS = 2000`
  - `DISPLAY_PRE_SEND_DELAY_MS = 50`
  - `DISPLAY_POST_ACK_DELAY_MS = 500`
  - `LOOP_DELAY_MS = 100`
  - `WIFI_RETRY_DELAY_MS = 200`

### 3. **Logging Verbosity**
- **Issue**: BLE notify callbacks and ACK messages logged excessively, cluttering serial output
- **Fix**: Wrapped verbose logging in `#if DEBUG_PNG` guards to reduce noise in production

### 4. **Missing Feature: Flash Animation**
- **Issue**: Python POC had flash animations on count increment, but ESP32 implementation was missing
- **Fix**: 
  - Extended `generate_pngs.py` to generate flash animation frames (invert and screen modes)
  - Added flash configuration to `config.h`:
    - `FLASH_ENABLED` (enable/disable)
    - `FLASH_MODE_INVERT` (0 = screen flash, 1 = invert flash)
    - `FLASH_DURATION_MS` (duration of each flash state)
    - `FLASH_REPEAT` (number of flash cycles)
  - Implemented `playFlashAnimation()` function in `main.cpp`
  - Added increment detection logic to trigger flash on count increase

### 5. **Code Organization**
- **Status**: Good overall structure
- **Note**: `display_render.cpp` is no longer used (replaced by pre-generated PNGs) but kept for reference

## Code Quality Improvements

### Constants & Configuration
- All timing values now use named constants
- Flash settings centralized in `config.h`
- Clear separation between configuration and implementation

### Error Handling
- Improved cleanup in BLE scan to prevent memory leaks
- Better state management for static globals

### Maintainability
- Flash animation logic is modular and configurable
- Easy to enable/disable features via `config.h`
- Clear function separation (updateDisplay vs playFlashAnimation)

## New Features

### Flash Animation Support
The ESP32 now supports flash animations matching the Python POC:

1. **Screen Flash Mode** (`FLASH_MODE_INVERT = 0`):
   - Displays solid color(s) during flash
   - Default: white flash
   - Supports multiple colors for alternating flash

2. **Invert Flash Mode** (`FLASH_MODE_INVERT = 1`):
   - Swaps text and background colors
   - Default: black text on white background during flash

Both modes:
- Trigger automatically on count increment
- Repeat `FLASH_REPEAT` times (default: 3)
- Each state lasts `FLASH_DURATION_MS` (default: 150ms)

## Build Instructions

After making changes, regenerate PNG frames with flash support:

```bash
cd esp32
python tools/generate_pngs.py
```

This will update `include/png_frames.h` with:
- Normal frames (0-99)
- Invert flash frames (0-99)
- Screen flash frames (1-2 colors)

## Configuration

Edit `include/config.h` to customize flash behavior:

```c
#define FLASH_ENABLED 1              // Enable/disable flash
#define FLASH_MODE_INVERT 0          // 0 = screen, 1 = invert
#define FLASH_DURATION_MS 150        // Flash state duration
#define FLASH_REPEAT 3               // Number of cycles
```

## Testing Recommendations

1. **Flash Animation**: Test both modes (screen and invert) to ensure smooth animation
2. **Memory**: Monitor heap usage during flash sequences
3. **Timing**: Verify flash duration feels appropriate (not too fast/slow)
4. **WiFi/BLE**: Ensure flash animations don't interfere with WiFi reconnection logic

## Future Improvements

1. **BLE Auto-Reconnect**: Currently basic, could be enhanced with exponential backoff
2. **Captive Portal**: Planned for WiFi setup (see README.md TODO)
3. **NVS Config Storage**: Planned for persistent settings
4. **Multi-Display Support**: Currently supports single display, could extend to multiple

## Files Modified

- `src/main.cpp` - Added flash animation logic, timing constants
- `src/ipixel_ble.cpp` - Improved memory management, reduced logging verbosity
- `include/config.h` - Added flash configuration options
- `tools/generate_pngs.py` - Extended to generate flash animation frames

## Files Generated

- `include/png_frames.h` - Auto-generated header with normal + flash frames (regenerate after changes)
