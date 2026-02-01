#ifndef CONFIG_NVS_H
#define CONFIG_NVS_H

#include <Arduino.h>

#define CONFIG_SSID_LEN 32
#define CONFIG_PASS_LEN 64
#define CONFIG_URL_LEN 127

// Stored config (NVS). Defaults from config.h if not set.
struct ConfigData {
  char wifi_ssid[CONFIG_SSID_LEN + 1];
  char wifi_pass[CONFIG_PASS_LEN + 1];
  char wifi_ssid2[CONFIG_SSID_LEN + 1];
  char wifi_pass2[CONFIG_PASS_LEN + 1];
  char api_url[CONFIG_URL_LEN + 1];
  uint32_t poll_interval_ms;
  bool configured;  // True if user has saved at least one config
};

// Load config from NVS. Fills defaults from config.h if empty.
void configLoad(ConfigData* out);

// Save config to NVS. Call after captive portal or web UI save.
bool configSave(const ConfigData* data);

// Reset to defaults (clears NVS config).
void configReset();

#endif
