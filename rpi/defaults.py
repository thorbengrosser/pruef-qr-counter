"""Shared config defaults for PRÜF Counter (display daemon + config UI).

Single source of truth so display_app.py and config_ui/app.py stay in sync.
"""

CONFIG_DEFAULTS = {
    "wifi_ssid": "",
    "wifi_pass": "",
    "wifi_ssid2": "",
    "wifi_pass2": "",
    "wifi_ssid3": "",
    "wifi_pass3": "",
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
