#!/usr/bin/env python3
"""
Flask config UI for PRÜF Counter (RPi). Serves config form; on POST writes config.json
and optionally restarts display service / triggers WiFi reconnect.
"""

import json
import os
import subprocess
import sys
import threading
import time
import types

import io
from flask import Flask, request, render_template_string, Response, jsonify

RPI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.environ.get("CONFIG_PATH") or os.path.join(RPI_DIR, "config.json")
FONTS_DIR = os.path.join(RPI_DIR, "fonts")

# Import shared defaults (single source of truth for both display daemon and config UI)
if RPI_DIR not in sys.path:
    sys.path.insert(0, RPI_DIR)
from defaults import CONFIG_DEFAULTS as DEFAULTS

app = Flask(__name__)


def load_config() -> dict:
    """Load config from JSON. Returns DEFAULTS if file missing or invalid (e.g. empty/corrupt)."""
    if not os.path.isfile(CONFIG_PATH):
        return DEFAULTS.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = f.read().strip()
            if not raw:
                return DEFAULTS.copy()
            data = json.loads(raw)
            return {**DEFAULTS, **data}
    except (json.JSONDecodeError, OSError):
        return DEFAULTS.copy()


def load_status() -> dict:
    """Read status.json from display daemon (last_error, last_count, api_ok)."""
    status_path = os.path.join(RPI_DIR, "status.json")
    if not os.path.isfile(status_path):
        return {}
    try:
        with open(status_path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
            if not raw:
                return {}
            return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def list_fonts() -> list[str]:
    fonts = []
    if os.path.isdir(FONTS_DIR):
        for name in sorted(os.listdir(FONTS_DIR)):
            if name.lower().endswith((".ttf", ".otf")):
                fonts.append(name)
    try:
        import pypixelcolor
        builtin = os.path.join(os.path.dirname(pypixelcolor.__file__), "fonts")
        if os.path.isdir(builtin):
            for name in sorted(os.listdir(builtin)):
                if name.lower().endswith((".ttf", ".otf")):
                    fonts.append(f"(built-in) {name}")
    except Exception:
        pass
    if not fonts:
        fonts = ["Kario39C3Var-Roman.ttf"]
    return fonts


def try_connect_sta() -> bool:
    """Run network/try_connect.sh to reconnect to primary/backup WiFi (nmcli)."""
    try_connect = os.path.join(RPI_DIR, "network", "try_connect.sh")
    if os.path.isfile(try_connect) and os.access(try_connect, os.X_OK):
        try:
            r = subprocess.run(
                [try_connect],
                cwd=RPI_DIR,
                timeout=30,
                capture_output=True,
            )
            return r.returncode == 0
        except Exception:
            pass
    return False


def _async_wifi_reconnect() -> None:
    """Run WiFi reconnect in background thread (only when WiFi settings changed).

    Display service is NOT restarted — it hot-reloads config.json automatically.
    """
    try:
        try_connect_sta()
    except Exception:
        pass


def _norm_hex(s: str) -> str:
    """Normalize to 6-char hex for type='color' value."""
    if not s:
        return "000000"
    h = (s or "").strip().lstrip("#")[:6]
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    return (h + "000000")[:6].lower()


CONFIG_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PRÜF Counter Setup</title>
  <style>
    :root { --bg: #1a1d21; --card: #25282c; --border: #3d4248; --text: #e8eaed; --muted: #9aa0a6; --accent: #5b9cf5; --accent-hover: #7aaff7; --error-bg: #3d2528; --error-border: #8b4c52; --success-bg: #243d2a; --success-border: #5a8b6a; --input-bg: #2d3136; }
    body { font-family: "Segoe UI", system-ui, -apple-system, sans-serif; font-size: 15px; line-height: 1.5; color: var(--text); background: var(--bg); margin: 0; padding: 1.25rem; min-height: 100vh; box-sizing: border-box; }
    * { box-sizing: border-box; }
    .wrap { max-width: 480px; margin: 0 auto; }
    h1 { font-size: 1.35rem; font-weight: 600; margin: 0 0 1rem; letter-spacing: -0.02em; color: var(--text); }
    .msg { margin: 0 0 1rem; padding: 0.6rem 0.75rem; border-radius: 6px; font-size: 0.9rem; }
    .msg.error { background: var(--error-bg); border: 1px solid var(--error-border); color: #f1aeb5; }
    .msg:not(.error) { background: var(--success-bg); border: 1px solid var(--success-border); color: #a3cfbb; }
    form { background: var(--card); border-radius: 10px; padding: 1.25rem; box-shadow: 0 2px 8px rgba(0,0,0,.3); border: 1px solid var(--border); }
    fieldset { margin: 0 0 1.25rem; padding: 0; border: none; }
    fieldset:last-of-type { margin-bottom: 0; }
    legend { font-weight: 600; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin-bottom: 0.6rem; padding: 0; }
    .row { margin-bottom: 0.75rem; }
    .row:last-child { margin-bottom: 0; }
    label { display: block; }
    label .label { display: block; font-size: 0.875rem; color: var(--text); margin-bottom: 0.25rem; }
    input[type="text"], input[type="number"], select { width: 100%; padding: 0.5rem 0.6rem; border: 1px solid var(--border); border-radius: 6px; font-size: 0.95rem; font-family: inherit; background: var(--input-bg); color: var(--text); }
    input[type="number"] { max-width: 5.5rem; }
    input::placeholder { color: var(--muted); }
    input:focus, select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(91,156,245,.25); }
    input[type="checkbox"] { width: 1.1em; height: 1.1em; margin-right: 0.35rem; vertical-align: middle; }
    select { color: var(--text); }
    select option { background: var(--card); color: var(--text); }
    .color-row { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
    .color-row .label { flex: 0 0 100%; }
    input[type="color"] { width: 2.5rem; height: 2.25rem; padding: 2px; border: 1px solid var(--border); border-radius: 6px; cursor: pointer; background: var(--input-bg); }
    input[type="color"]::-webkit-color-swatch-wrapper { padding: 2px; }
    input[type="color"]::-webkit-color-swatch { border-radius: 4px; border: none; }
    .color-hex { flex: 1; min-width: 5rem; max-width: 7rem; font-family: ui-monospace, monospace; }
    button[type="submit"] { margin-top: 1rem; padding: 0.6rem 1.25rem; font-size: 0.95rem; font-weight: 500; color: #1a1d21; background: var(--accent); border: none; border-radius: 6px; cursor: pointer; font-family: inherit; }
    button[type="submit"]:hover { background: var(--accent-hover); }
    button[type="submit"]:focus { outline: none; box-shadow: 0 0 0 3px rgba(91,156,245,.4); }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>PRÜF Counter Setup</h1>
    {% if message %}
    <p class="msg {{ 'error' if error else '' }}">{{ message }}</p>
    {% endif %}
    {% if status.last_error %}
    <p class="msg error">Display: {{ status.last_error }}</p>
    {% endif %}
    {% if status.get('last_count') is defined and status.get('api_ok', false) %}
    <p class="msg">Last count: {{ status.last_count }}</p>
    {% endif %}
    <form method="post" action="">
      <fieldset>
        <legend>Primary WiFi</legend>
        <div class="row"><label><span class="label">SSID</span> <input type="text" name="wifi_ssid" value="{{ config.wifi_ssid }}" maxlength="32"></label></div>
        <div class="row"><label><span class="label">Password</span> <input type="password" name="wifi_pass" value="{{ config.wifi_pass }}" maxlength="64"></label></div>
      </fieldset>
      <fieldset>
        <legend>Backup WiFi (optional)</legend>
        <div class="row"><label><span class="label">SSID 2</span> <input type="text" name="wifi_ssid2" value="{{ config.wifi_ssid2 }}" maxlength="32"></label></div>
        <div class="row"><label><span class="label">Password 2</span> <input type="text" name="wifi_pass2" value="{{ config.wifi_pass2 }}" maxlength="64" autocomplete="off"></label></div>
      </fieldset>
      <fieldset>
        <legend>WiFi 3 (optional)</legend>
        <div class="row"><label><span class="label">SSID 3</span> <input type="text" name="wifi_ssid3" value="{{ config.wifi_ssid3 }}" maxlength="32"></label></div>
        <div class="row"><label><span class="label">Password 3</span> <input type="text" name="wifi_pass3" value="{{ config.wifi_pass3 }}" maxlength="64" autocomplete="off"></label></div>
      </fieldset>
      <fieldset>
        <legend>API</legend>
        <div class="row"><label><span class="label">Count API URL</span> <input type="text" name="api_url" value="{{ config.api_url }}" size="40"></label></div>
        <div class="row"><label><span class="label">Poll interval (sec)</span> <input type="number" name="poll_interval_sec" value="{{ config.poll_interval_sec }}" min="0.5" max="60" step="0.5"></label></div>
      </fieldset>
      <fieldset>
        <legend>Display</legend>
        <div class="row"><label><span class="label">Fixed text (empty = from API)</span> <input type="text" name="display_string" value="{{ config.display_string }}"></label></div>
        <div class="row"><label><span class="label">Suffix</span> <input type="text" name="suffix" value="{{ config.suffix }}"></label></div>
        <div class="row"><label><span class="label">Font</span>
          <select name="font">
            {% for f in fonts %}
            {% set fval = f.replace('(built-in) ', '') if f.startswith('(built-in) ') else f %}
            <option value="{{ fval }}" {{ 'selected' if config.font == fval else '' }}>{{ f }}</option>
            {% endfor %}
          </select>
        </label></div>
        <div class="row"><label><span class="label">Font size (px)</span> <input type="number" name="font_size" value="{{ config.font_size }}" min="6" max="64"></label></div>
        <div class="row"><label><span class="label">Font width (axis, e.g. 100 for Kario)</span> <input type="number" name="font_width" value="{{ config.font_width }}" min="50" max="200" step="1" placeholder="100"></label></div>
        <div class="row"><label><span class="label">Y offset (px)</span> <input type="number" name="y_offset" value="{{ config.y_offset }}" min="-16" max="16"></label></div>
        <div class="row"><label><span class="label">Crisp edges</span> <input type="checkbox" name="crisp" {{ 'checked' if config.crisp else '' }}></label></div>
        <div class="row color-row"><label><span class="label">Text color</span></label><input type="color" id="pick_text_color" value="#{{ norm_hex(config.text_color) }}" aria-label="Text color"><input type="text" name="text_color" value="{{ config.text_color }}" maxlength="7" class="color-hex" data-picker="pick_text_color"></div>
        <div class="row color-row"><label><span class="label">Background color</span></label><input type="color" id="pick_bg_color" value="#{{ norm_hex(config.bg_color) }}" aria-label="Background color"><input type="text" name="bg_color" value="{{ config.bg_color }}" maxlength="7" class="color-hex" data-picker="pick_bg_color"></div>
        <div class="row"><label><span class="label">Effect</span>
          <select name="effect">
            <option value="none" {{ 'selected' if config.effect == 'none' else '' }}>None</option>
            <option value="invert" {{ 'selected' if config.effect == 'invert' else '' }}>Invert (flash on increment)</option>
            <option value="screen" {{ 'selected' if config.effect == 'screen' else '' }}>Screen flash</option>
          </select>
        </label></div>
        <div class="row"><label><span class="label">Flash duration (sec)</span> <input type="number" name="flash_duration_sec" value="{{ config.flash_duration_sec }}" min="0.05" max="2" step="0.05"></label></div>
        <div class="row"><label><span class="label">Flash repeat</span> <input type="number" name="flash_repeat" value="{{ config.flash_repeat }}" min="1" max="10"></label></div>
        <div class="row color-row"><label><span class="label">Invert flash: text</span></label><input type="color" id="pick_flash_text" value="#{{ norm_hex(config.flash_text_color) }}" aria-label="Invert flash text"><input type="text" name="flash_text_color" value="{{ config.flash_text_color }}" maxlength="7" class="color-hex" data-picker="pick_flash_text"></div>
        <div class="row color-row"><label><span class="label">Invert flash: background</span></label><input type="color" id="pick_flash_bg" value="#{{ norm_hex(config.flash_bg_color) }}" aria-label="Invert flash bg"><input type="text" name="flash_bg_color" value="{{ config.flash_bg_color }}" maxlength="7" class="color-hex" data-picker="pick_flash_bg"></div>
        <div class="row color-row"><label><span class="label">Screen flash color</span></label><input type="color" id="pick_flash_color" value="#{{ norm_hex(config.flash_color) }}" aria-label="Screen flash"><input type="text" name="flash_color" value="{{ config.flash_color }}" maxlength="7" class="color-hex" data-picker="pick_flash_color"></div>
        <div class="row color-row"><label><span class="label">Screen flash color 2 (optional)</span></label><input type="color" id="pick_flash_color2" value="#{{ norm_hex(config.flash_color2) }}" aria-label="Screen flash 2"><input type="text" name="flash_color2" value="{{ config.flash_color2 }}" maxlength="7" class="color-hex" data-picker="pick_flash_color2"></div>
        <div class="row"><label><span class="label">Devices</span> <input type="text" name="devices" value="{{ config.devices }}" placeholder="auto or addr1,addr2"></label></div>
      </fieldset>
      <button type="submit">Save &amp; Reconnect</button>
    </form>
    <fieldset style="margin-top:1.5rem;">
      <legend>Preview</legend>
      <p class="label" style="margin-bottom:0.5rem;">Render a frame with current display settings (64×16 with white frame).</p>
      <div class="row" style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
        <label><span class="label">Count</span> <input type="number" id="preview_count" value="42" min="0" max="999" style="max-width:5rem;"></label>
        <button type="button" id="preview_render" style="margin-top:1.25rem;">Render</button>
      </div>
      <div id="preview_container" style="margin-top:0.75rem; display:none;">
        <img id="preview_img" alt="Preview" style="display:block; image-rendering:pixelated; image-rendering:crisp-edges;">
      </div>
    </fieldset>
  </div>
  <script>
  (function(){
    function toHex(v){ v = (v||'').replace(/^#/,''); if(v.length===3) v = v[0]+v[0]+v[1]+v[1]+v[2]+v[2]; return (v+'000000').slice(0,6).toLowerCase(); }
    function toHash(h){ h = toHex(h); return '#'+h; }
    document.querySelectorAll('.color-hex').forEach(function(hex){
      var picker = document.getElementById(hex.dataset.picker);
      if(!picker) return;
      picker.addEventListener('input', function(){ hex.value = toHex(picker.value); });
      hex.addEventListener('input', function(){ picker.value = toHash(hex.value); });
    });
    document.getElementById('preview_render').addEventListener('click', function(){
      var form = document.querySelector('form');
      var count = document.getElementById('preview_count').value || '0';
      var fd = new FormData();
      fd.append('preview_count', count);
      fd.append('font', form.querySelector('[name=font]').value);
      fd.append('font_size', form.querySelector('[name=font_size]').value);
      fd.append('font_width', form.querySelector('[name=font_width]').value);
      fd.append('y_offset', form.querySelector('[name=y_offset]').value);
      fd.append('suffix', form.querySelector('[name=suffix]').value);
      fd.append('crisp', form.querySelector('[name=crisp]').checked ? 'on' : '');
      fd.append('text_color', form.querySelector('[name=text_color]').value);
      fd.append('bg_color', form.querySelector('[name=bg_color]').value);
      var img = document.getElementById('preview_img');
      var container = document.getElementById('preview_container');
      fetch('/preview', { method: 'POST', body: fd })
        .then(function(r){ if(!r.ok) throw new Error('Preview failed'); return r.blob(); })
        .then(function(blob){ img.src = URL.createObjectURL(blob); container.style.display = 'block'; })
        .catch(function(){ container.innerHTML = '<p class="msg error">Preview failed. Check font and colors.</p>'; container.style.display = 'block'; });
    });
  })();
  </script>
</body>
</html>
"""


def _render_preview_png() -> Response:
    """Render one frame with current form display settings; return PNG with 2px white frame."""
    # Ensure rpi/ is on path so we can import display_app
    if RPI_DIR not in sys.path:
        sys.path.insert(0, RPI_DIR)
    import display_app as da
    from PIL import Image

    cfg = {
        "font": (request.form.get("font") or DEFAULTS["font"]).strip(),
        "font_size": max(6, min(64, int(request.form.get("font_size") or 22))),
        "font_width": request.form.get("font_width", "").strip() or None,
        "y_offset": max(-16, min(16, int(request.form.get("y_offset") or 1))),
        "suffix": (request.form.get("suffix") or " x")[:32],
        "crisp": request.form.get("crisp") == "on",
        "text_color": (request.form.get("text_color") or "ffffff").strip().lstrip("#")[:6] or "ffffff",
        "bg_color": (request.form.get("bg_color") or "000000").strip().lstrip("#")[:6] or "000000",
    }
    font_width_raw = cfg.get("font_width")
    font_width = float(font_width_raw) if font_width_raw not in (None, "") else None
    count = request.form.get("preview_count", "0").strip() or "0"
    text = count + (cfg["suffix"] or " x")
    font_path = da.resolve_font_path(cfg)
    text_color = da.hex_to_rgb(cfg["text_color"])
    bg_color = da.hex_to_rgb(cfg["bg_color"])

    path = da.render_text_to_image(
        text, 64, 16,
        font_path=font_path,
        font_size=cfg["font_size"],
        font_width=font_width,
        y_offset=cfg["y_offset"],
        crisp=cfg["crisp"],
        text_color=text_color,
        bg_color=bg_color,
    )
    try:
        img = Image.open(path).convert("RGB")
        w, h = 64, 16
        border = 2
        framed = Image.new("RGB", (w + 2 * border, h + 2 * border), (255, 255, 255))
        framed.paste(img, (border, border))
        buf = io.BytesIO()
        framed.save(buf, format="PNG")
        buf.seek(0)
        return Response(buf.getvalue(), mimetype="image/png")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@app.route("/preview", methods=["POST"])
def preview():
    try:
        return _render_preview_png()
    except Exception as e:
        return Response(str(e), status=400, mimetype="text/plain")


_service_cache: dict = {}  # {name: (timestamp, result)}
_SERVICE_CACHE_TTL = 5.0   # seconds

# Services the UI is allowed to restart (do not include pruf-config-server or we kill the UI)
RESTARTABLE_SERVICES = frozenset({"pruf-display.service", "pruf-network.service"})


def _clear_service_cache(service_name: str) -> None:
    """Clear cache for a service so next status fetch is fresh."""
    for key in list(_service_cache.keys()):
        if key == service_name or key == service_name + ":full":
            del _service_cache[key]


def get_service_status(service_name: str) -> dict:
    """Check systemd service status with caching. Returns {active: bool, status: str}."""
    now = time.monotonic()
    cached = _service_cache.get(service_name)
    if cached and (now - cached[0]) < _SERVICE_CACHE_TTL:
        return cached[1]
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=2,
        )
        active = result.returncode == 0
        # Only fetch full status text if explicitly needed (status page)
        # For /status.json keep it lightweight
        status_text = "active" if active else "inactive"
        data = {"active": active, "status": status_text}
        _service_cache[service_name] = (now, data)
        return data
    except Exception:
        return {"active": False, "status": "unknown"}


def get_service_status_full(service_name: str) -> dict:
    """Full systemd status with journal lines. Used for /status HTML page only."""
    cache_key = service_name + ":full"
    now = time.monotonic()
    cached = _service_cache.get(cache_key)
    if cached and (now - cached[0]) < _SERVICE_CACHE_TTL:
        return cached[1]
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=2,
        )
        active = result.returncode == 0
        status_result = subprocess.run(
            ["systemctl", "status", service_name, "--no-pager", "-n", "5"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        status_text = status_result.stdout if status_result.returncode == 0 else status_result.stderr
        data = {"active": active, "status": status_text}
        _service_cache[cache_key] = (now, data)
        return data
    except Exception:
        return {"active": False, "status": "unknown"}


_wifi_cache: dict = {}  # {"result": ..., "ts": ...}
_WIFI_CACHE_TTL = 5.0


def get_wifi_status() -> dict:
    """Get WiFi connection status via nmcli (cached)."""
    now = time.monotonic()
    if _wifi_cache and (now - _wifi_cache.get("ts", 0)) < _WIFI_CACHE_TTL:
        return _wifi_cache["result"]
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,DEVICE,TYPE,STATE", "connection", "show", "--active"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            # nmcli reports WiFi as type "802-11-wireless", not "wifi"
            wifi_conns = [l for l in lines if ":wifi:" in l.lower() or ":802-11-wireless:" in l.lower()]
            if wifi_conns:
                parts = wifi_conns[0].split(":")
                data = {"connected": True, "ssid": parts[0] if len(parts) > 0 else "unknown", "state": parts[-1] if len(parts) > 0 else "unknown"}
                _wifi_cache.update({"result": data, "ts": now})
                return data
        data = {"connected": False, "ssid": None, "state": "disconnected"}
        _wifi_cache.update({"result": data, "ts": now})
        return data
    except Exception:
        return {"connected": False, "ssid": None, "state": "unknown"}


@app.route("/api/restart-service", methods=["POST"])
def api_restart_service():
    """Restart a known systemd service (display or network). Returns JSON {ok, message}."""
    name = request.args.get("service") or request.form.get("service")
    if not name and request.is_json:
        body = request.get_json(silent=True)
        name = (body or {}).get("service") if body else None
    name = (name or "").strip()
    if not name or name not in RESTARTABLE_SERVICES:
        return jsonify({"ok": False, "message": "Invalid or disallowed service"}), 400
    try:
        subprocess.run(
            ["systemctl", "restart", name],
            capture_output=True,
            text=True,
            timeout=15,
        )
        _clear_service_cache(name)
        return jsonify({"ok": True, "message": f"Restarted {name}"})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "message": "Restart timed out"}), 500
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/status.json")
def status_json():
    """JSON status endpoint for monitoring."""
    status = load_status()
    display_service = get_service_status("pruf-display.service")
    config_service = get_service_status("pruf-config-server.service")
    network_service = get_service_status("pruf-network.service")
    wifi = get_wifi_status()
    
    return jsonify({
        "display": {
            "last_count": status.get("last_count"),
            "last_error": status.get("last_error"),
            "api_ok": status.get("api_ok", False),
            "ble_connected": status.get("ble_connected", 0),
            "ble_addresses": status.get("ble_addresses", []),
            "last_update": status.get("last_update"),
        },
        "services": {
            "display": display_service,
            "config": config_service,
            "network": network_service,
        },
        "wifi": wifi,
    })


STATUS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PRÜF Counter - Status</title>
    <style>
        :root {
            --bg: #1a1a1a;
            --surface: #2d2d2d;
            --text: #e0e0e0;
            --text-dim: #999;
            --accent: #4a9eff;
            --success: #4caf50;
            --error: #f44336;
            --warning: #ff9800;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 20px;
            line-height: 1.6;
        }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { margin-bottom: 30px; color: var(--accent); }
        .card {
            background: var(--surface);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }
        .card h2 {
            font-size: 1.2em;
            margin-bottom: 15px;
            color: var(--accent);
            border-bottom: 1px solid #444;
            padding-bottom: 8px;
        }
        .status-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #333;
        }
        .status-item:last-child { border-bottom: none; }
        .status-label { color: var(--text-dim); }
        .status-value {
            font-weight: 500;
            word-break: break-all;
        }
        .status-row-with-action {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
        }
        .status-row-with-action .status-value { flex: 0 1 auto; }
        .restart-btn {
            flex-shrink: 0;
            padding: 6px 12px;
            font-size: 0.85em;
            background: var(--surface);
            color: var(--accent);
            border: 1px solid var(--accent);
            border-radius: 6px;
            cursor: pointer;
            text-decoration: none;
        }
        .restart-btn:hover { background: rgba(74, 158, 255, 0.15); }
        .restart-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: 500;
        }
        .badge-success { background: var(--success); color: white; }
        .badge-error { background: var(--error); color: white; }
        .badge-warning { background: var(--warning); color: white; }
        .badge-info { background: var(--accent); color: white; }
        .refresh-btn {
            background: var(--accent);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 1em;
            margin-bottom: 20px;
        }
        .refresh-btn:hover { opacity: 0.9; }
        .auto-refresh { color: var(--text-dim); font-size: 0.9em; margin-top: 10px; }
        .error-text { color: var(--error); }
        .success-text { color: var(--success); }
    </style>
</head>
<body>
    <div class="container">
        <h1>PRÜF Counter Status</h1>
        <button class="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
        <div class="auto-refresh">Auto-refreshes every 30 seconds</div>
        
        <div class="card">
            <h2>Display</h2>
            <div class="status-item">
                <span class="status-label">Last Count:</span>
                <span class="status-value">{{ status.get('last_count', 'N/A') }}</span>
            </div>
            <div class="status-item">
                <span class="status-label">API Status:</span>
                <span class="status-value">
                    {% if status.get('api_ok') %}
                        <span class="badge badge-success">OK</span>
                    {% else %}
                        <span class="badge badge-error">Error</span>
                    {% endif %}
                </span>
            </div>
            <div class="status-item">
                <span class="status-label">BLE Connected:</span>
                <span class="status-value">
                    <span class="badge {% if status.get('ble_connected', 0) > 0 %}badge-success{% else %}badge-error{% endif %}">
                        {{ status.get('ble_connected', 0) }} device(s)
                    </span>
                </span>
            </div>
            {% if status.get('ble_addresses') %}
            <div class="status-item">
                <span class="status-label">BLE Addresses:</span>
                <span class="status-value">{{ ', '.join(status.get('ble_addresses', [])) }}</span>
            </div>
            {% endif %}
            {% if status.get('last_error') %}
            <div class="status-item">
                <span class="status-label">Last Error:</span>
                <span class="status-value error-text">{{ status.get('last_error') }}</span>
            </div>
            {% endif %}
            {% if status.get('last_update') %}
            <div class="status-item">
                <span class="status-label">Last Update:</span>
                <span class="status-value">{{ last_update_formatted }}</span>
            </div>
            {% endif %}
        </div>
        
        <div class="card">
            <h2>Services</h2>
            <div class="status-item status-row-with-action">
                <span class="status-label">Display Service:</span>
                <span class="status-value">
                    <span class="badge {% if display_service.get('active') %}badge-success{% else %}badge-error{% endif %}">
                        {{ 'Active' if display_service.get('active') else 'Inactive' }}
                    </span>
                </span>
                <button type="button" class="restart-btn" data-service="pruf-display.service" data-label="Display (rescan BLE)" data-restore="Restart (rescan BLE)" onclick="restartService(this)">Restart (rescan BLE)</button>
            </div>
            <div class="status-item">
                <span class="status-label">Config Service:</span>
                <span class="status-value">
                    <span class="badge {% if config_service.get('active') %}badge-success{% else %}badge-error{% endif %}">
                        {{ 'Active' if config_service.get('active') else 'Inactive' }}
                    </span>
                </span>
            </div>
            <div class="status-item status-row-with-action">
                <span class="status-label">Network Service:</span>
                <span class="status-value">
                    <span class="badge {% if network_service.get('active') %}badge-success{% else %}badge-error{% endif %}">
                        {{ 'Active' if network_service.get('active') else 'Inactive' }}
                    </span>
                </span>
                <button type="button" class="restart-btn" data-service="pruf-network.service" data-label="Network" data-restore="Restart" onclick="restartService(this)">Restart</button>
            </div>
        </div>
        
        <div class="card">
            <h2>WiFi</h2>
            <div class="status-item">
                <span class="status-label">Status:</span>
                <span class="status-value">
                    {% if wifi.get('connected') %}
                        <span class="badge badge-success">Connected</span>
                    {% else %}
                        <span class="badge badge-error">Disconnected</span>
                    {% endif %}
                </span>
            </div>
            {% if wifi.get('ssid') %}
            <div class="status-item">
                <span class="status-label">SSID:</span>
                <span class="status-value">{{ wifi.get('ssid') }}</span>
            </div>
            {% endif %}
            <div class="status-item">
                <span class="status-label">State:</span>
                <span class="status-value">{{ wifi.get('state', 'unknown') }}</span>
            </div>
        </div>
        
        <div class="card">
            <h2>Quick Links</h2>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <a href="/" style="color: var(--accent); text-decoration: none;">⚙️ Configuration</a>
                <a href="/status.json" style="color: var(--accent); text-decoration: none;">📊 JSON Status</a>
            </div>
        </div>
    </div>
    
    <script>
        // Auto-refresh every 30 seconds
        setTimeout(() => location.reload(), 30000);

        function restartService(btn) {
            const service = btn.dataset.service;
            const label = btn.dataset.label || service;
            if (!confirm('Restart ' + label + '? Displays may go dark for a few seconds.')) return;
            btn.disabled = true;
            btn.textContent = 'Restarting…';
            fetch('/api/restart-service?service=' + encodeURIComponent(service), { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.ok) {
                        btn.textContent = 'Restarted';
                        setTimeout(() => location.reload(), 2000);
                    } else {
                        alert('Failed: ' + (data.message || 'Unknown error'));
                        btn.disabled = false;
                        btn.textContent = btn.dataset.restore || 'Restart';
                    }
                })
                .catch(err => {
                    alert('Error: ' + err.message);
                    btn.disabled = false;
                    btn.textContent = btn.dataset.restore || 'Restart';
                });
        }

        // Format timestamp if needed
        const timestamps = document.querySelectorAll('[data-timestamp]');
        timestamps.forEach(el => {
            const ts = parseInt(el.textContent);
            if (ts) {
                const date = new Date(ts * 1000);
                el.textContent = date.toLocaleString();
            }
        });
    </script>
</body>
</html>
"""


@app.route("/status")
def status_page():
    """HTML status dashboard."""
    status = load_status()
    display_service = get_service_status_full("pruf-display.service")
    config_service = get_service_status_full("pruf-config-server.service")
    network_service = get_service_status_full("pruf-network.service")
    wifi = get_wifi_status()

    # Format last_update timestamp
    from datetime import datetime
    last_update_ts = status.get("last_update")
    last_update_formatted = (
        datetime.fromtimestamp(last_update_ts).strftime("%Y-%m-%d %H:%M:%S")
        if last_update_ts else "N/A"
    )
    
    return render_template_string(
        STATUS_HTML,
        status=status,
        display_service=display_service,
        config_service=config_service,
        network_service=network_service,
        wifi=wifi,
        last_update_formatted=last_update_formatted,
    )


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        old_config = load_config()
        data = {
            "wifi_ssid": (request.form.get("wifi_ssid") or "").strip()[:32],
            "wifi_pass": (request.form.get("wifi_pass") or "").strip()[:64],
            "wifi_ssid2": (request.form.get("wifi_ssid2") or "").strip()[:32],
            "wifi_pass2": (request.form.get("wifi_pass2") or "").strip()[:64],
            "wifi_ssid3": (request.form.get("wifi_ssid3") or "").strip()[:32],
            "wifi_pass3": (request.form.get("wifi_pass3") or "").strip()[:64],
            "api_url": (request.form.get("api_url") or DEFAULTS["api_url"]).strip()[:256],
            "poll_interval_sec": max(0.5, min(60, float(request.form.get("poll_interval_sec") or 1))),
            "display_string": (request.form.get("display_string") or "").strip(),
            "suffix": (request.form.get("suffix") or " x")[:32],
            "font": (request.form.get("font") or DEFAULTS["font"]).strip(),
            "font_size": max(6, min(64, int(request.form.get("font_size") or 22))),
            "font_width": request.form.get("font_width", "").strip() or None,
            "y_offset": max(-16, min(16, int(request.form.get("y_offset") or 1))),
            "crisp": request.form.get("crisp") == "on",
            "text_color": (request.form.get("text_color") or "ffffff").strip().lstrip("#")[:6] or "ffffff",
            "bg_color": (request.form.get("bg_color") or "000000").strip().lstrip("#")[:6] or "000000",
            "effect": (request.form.get("effect") or "none").strip().lower() or "none",
            "flash_duration_sec": max(0.05, min(2, float(request.form.get("flash_duration_sec") or 0.15))),
            "flash_repeat": max(1, min(10, int(request.form.get("flash_repeat") or 3))),
            "flash_text_color": (request.form.get("flash_text_color") or "000000").strip().lstrip("#")[:6] or "000000",
            "flash_bg_color": (request.form.get("flash_bg_color") or "ffffff").strip().lstrip("#")[:6] or "ffffff",
            "flash_color": (request.form.get("flash_color") or "ffffff").strip().lstrip("#")[:6] or "ffffff",
            "flash_color2": (request.form.get("flash_color2") or "").strip().lstrip("#")[:6],
            "devices": (request.form.get("devices") or "auto").strip() or "auto",
        }
        try:
            save_config(data)
            # Only reconnect WiFi if WiFi settings actually changed
            # Display service hot-reloads config.json automatically (no restart needed!)
            wifi_changed = (
                data["wifi_ssid"] != old_config.get("wifi_ssid", "") or
                data["wifi_pass"] != old_config.get("wifi_pass", "") or
                data["wifi_ssid2"] != old_config.get("wifi_ssid2", "") or
                data["wifi_pass2"] != old_config.get("wifi_pass2", "") or
                data["wifi_ssid3"] != old_config.get("wifi_ssid3", "") or
                data["wifi_pass3"] != old_config.get("wifi_pass3", "")
            )
            if wifi_changed:
                threading.Thread(target=_async_wifi_reconnect, daemon=True).start()
                message = "Saved. WiFi reconnecting in background\u2026"
            else:
                message = "Saved. Display will update within seconds."
            return render_template_string(
                CONFIG_HTML,
                config=types.SimpleNamespace(**data),
                fonts=list_fonts(),
                status=load_status(),
                norm_hex=_norm_hex,
                message=message,
                error=False,
            )
        except Exception as e:
            return render_template_string(
                CONFIG_HTML,
                config=load_config(),
                fonts=list_fonts(),
                status=load_status(),
                norm_hex=_norm_hex,
                message=f"Save failed: {e}",
                error=True,
            ), 500

    config = load_config()
    # Ensure font is in list
    fonts = list_fonts()
    if config.get("font") and config["font"] not in [f.replace("(built-in) ", "") if f.startswith("(built-in) ") else f for f in fonts]:
        fonts.insert(0, config["font"])
    return render_template_string(
        CONFIG_HTML,
        config=types.SimpleNamespace(**{**DEFAULTS, **config}),
        fonts=fonts,
        status=load_status(),
        norm_hex=_norm_hex,
        message=None,
        error=False,
    )


def main():
    host = os.environ.get("CONFIG_UI_HOST", "0.0.0.0")
    port = int(os.environ.get("CONFIG_UI_PORT", "80"))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
