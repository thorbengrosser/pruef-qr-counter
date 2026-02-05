# RPi Code Audit — Pi Zero 2 W Compatibility

## Audit Date
February 2, 2026

## Summary
Code audit of the RPi implementation for Raspberry Pi Zero 2 W compatibility. Overall structure is sound, but several issues need addressing before deployment.

---

## Issues Found

### 1. **Import Path Issue (CRITICAL)** ✅ FIXED
**Location**: `config_ui/app.py` line 297  
**Issue**: `import display_app as da` may fail when running as `python -m config_ui.app` because `display_app.py` is not on the Python module path.  
**Impact**: Preview feature will fail with `ModuleNotFoundError: No module named 'display_app'`.  
**Fix**: ✅ Added `sys.path.insert(0, RPI_DIR)` before import in `_render_preview_png()`.

### 2. **Missing config.json.example** ✅ FIXED
**Location**: `install.sh` line 119  
**Issue**: Script references `config.json.example` which doesn't exist (falls back to inline JSON).  
**Impact**: Minor — fallback works, but could be cleaner.  
**Fix**: ✅ Replaced with heredoc that writes proper JSON with all fields including `font_width`.

### 3. **Python Version Requirement** ✅ DOCUMENTED
**Location**: `display_app.py` uses `str | None` type hints  
**Issue**: Requires Python 3.10+ (union types).  
**Impact**: Raspberry Pi OS Bookworm ships Python 3.11, so OK, but should be documented.  
**Fix**: ✅ Added Python 3.10+ requirement to README.

### 4. **NetworkManager AP Mode Assumptions**
**Location**: `network/start_ap.sh`  
**Issue**: Assumes `wlan0` interface name and that NetworkManager can create AP while interface may be managed elsewhere.  
**Impact**: On some Pi OS setups, `wlan0` might be managed by `dhcpcd` or another service, causing conflicts.  
**Fix**: Check if interface is managed by NetworkManager; optionally disable conflicting services in install.sh.

### 5. **Strict Error Handling in Network Scripts**
**Location**: `network/try_connect.sh` line 5 (`set -e`)  
**Issue**: Script exits immediately on any error, which might mask useful error messages.  
**Impact**: Minor — script is meant to fail fast, but could be more informative.  
**Fix**: Consider removing `set -e` or adding better error messages.

### 6. **BLE Permissions**
**Location**: Systemd services run as `root`  
**Issue**: Running as root works but is not ideal. BLE typically requires `bluetooth` group membership.  
**Impact**: Works as-is, but if we ever want to run as non-root user, we'd need group membership.  
**Fix**: Document or optionally add user to `bluetooth` group in install.sh.

### 7. **Font Width Type Handling**
**Location**: `config_ui/app.py` line 303, `display_app.py` line 270  
**Issue**: `font_width` from form is string; needs conversion to `float | None`. Current code handles this, but could be clearer.  
**Impact**: Works but fragile if form sends unexpected value.  
**Fix**: Already handled correctly, but could add validation.

### 8. **NetworkManager AP Shared Mode**
**Location**: `network/start_ap.sh` line 16 (`ipv4.method shared`)  
**Issue**: Shared mode may not work on all NetworkManager versions or may conflict with existing connections.  
**Impact**: AP might not start or DHCP might not work.  
**Fix**: Test on actual Pi; consider fallback to hostapd+dnsmasq if NetworkManager AP fails.

---

## Recommendations

### High Priority

1. ✅ **Fix import path** (Issue #1) — **FIXED**: Added `sys.path.insert(0, RPI_DIR)` before import.

2. ✅ **Document Python version** — **FIXED**: Added to README.

3. **Test NetworkManager AP**: Verify `nmcli` AP mode works on Pi Zero 2 W; if not, fall back to hostapd+dnsmasq. **ACTION NEEDED**: Test on actual hardware.

### Medium Priority

4. **Create config.json.example**: Add a template file so install.sh can copy it cleanly.

5. ✅ **NetworkManager interface check**: Added note in install.sh about dhcpcd.conf conflicts (non-blocking, NetworkManager should handle it).

### Low Priority

6. **Improve error messages**: Make network scripts more verbose on failure.

7. **BLE group membership**: Document or add user to `bluetooth` group (optional if staying root).

---

## Architecture Compatibility

✅ **Python**: Python 3.11 on Bookworm supports all syntax (`str | None`, `asyncio.run`, etc.)  
✅ **BLE**: `bleak` and `pypixelcolor` work on Linux/ARM (Pi Zero 2 W)  
✅ **WiFi**: NetworkManager (`nmcli`) available on Raspberry Pi OS  
✅ **Systemd**: Standard on Raspberry Pi OS  
✅ **File paths**: All relative, no hardcoded assumptions  
✅ **Dependencies**: All available via pip/apt for ARM

---

## Testing Checklist

Before deploying to Pi Zero 2 W:

- [ ] Run `./run_local.sh dry-run` to verify rendering logic
- [ ] Test config UI preview feature (fixes import path first)
- [ ] Verify NetworkManager AP mode on actual Pi (or fallback to hostapd)
- [ ] Test BLE scan/connect with actual iPixel device
- [ ] Verify systemd services start correctly
- [ ] Test WiFi failover (primary → backup → AP)
- [ ] Test captive portal (connect to PRUF-Setup, open http://192.168.4.1)
- [ ] Verify mDNS (`http://pruf.local` works)

---

## Files to Review/Modify

1. `config_ui/app.py` — Fix import path for `display_app`
2. `install.sh` — Document Python version, optionally handle NetworkManager conflicts
3. `README.md` — Add Python 3.10+ requirement
4. `network/start_ap.sh` — Add error handling/fallback if NetworkManager AP fails
