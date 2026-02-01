#include "config_nvs.h"
#include "config.h"
#include <nvs.h>
#include <nvs_flash.h>
#include <esp_err.h>
#include <string.h>

static const char* NVS_NAMESPACE = "pruef_cfg";
static const char* KEY_DATA = "cfg";

void configLoad(ConfigData* out) {
  memset(out, 0, sizeof(ConfigData));

  // Defaults from config.h
  strncpy(out->wifi_ssid, WIFI_SSID, CONFIG_SSID_LEN);
  out->wifi_ssid[CONFIG_SSID_LEN] = '\0';
  strncpy(out->wifi_pass, WIFI_PASS, CONFIG_PASS_LEN);
  out->wifi_pass[CONFIG_PASS_LEN] = '\0';
  strncpy(out->api_url, API_URL, CONFIG_URL_LEN);
  out->api_url[CONFIG_URL_LEN] = '\0';
  out->poll_interval_ms = POLL_INTERVAL_MS;
  out->wifi_ssid2[0] = '\0';
  out->wifi_pass2[0] = '\0';

  nvs_handle h;
  if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &h) != ESP_OK) {
    return;
  }

  size_t len = sizeof(ConfigData);
  if (nvs_get_blob(h, KEY_DATA, out, &len) == ESP_OK) {
    // Sanity checks
    if (out->poll_interval_ms < 500) out->poll_interval_ms = 500;
    if (out->poll_interval_ms > 60000) out->poll_interval_ms = 60000;
  }
  nvs_close(h);
}

bool configSave(const ConfigData* data) {
  nvs_handle h;
  if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h) != ESP_OK) {
    return false;
  }
  esp_err_t err = nvs_set_blob(h, KEY_DATA, data, sizeof(ConfigData));
  if (err == ESP_OK) {
    err = nvs_commit(h);
  }
  nvs_close(h);
  return (err == ESP_OK);
}

void configReset() {
  nvs_handle h;
  if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h) == ESP_OK) {
    nvs_erase_key(h, KEY_DATA);
    nvs_commit(h);
    nvs_close(h);
  }
}
