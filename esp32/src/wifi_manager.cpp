#include "wifi_manager.h"
#include "config_nvs.h"
#include "config.h"
#include <WiFi.h>
#include <nvs_flash.h>
#include <esp_err.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Arduino.h>

static ConfigData s_config;
static WebServer* s_server = nullptr;
static WebServer* s_settingsServer = nullptr;
static DNSServer s_dns;
static const char* AP_SSID = "PRUF-Setup";
static const char* AP_PASS = "pruef1234";
static const byte DNS_PORT = 53;
static IPAddress apIP(192, 168, 4, 1);

void wifiManagerInit() {
  esp_err_t err = nvs_flash_init();
  if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    nvs_flash_erase();
    nvs_flash_init();
  }
  configLoad(&s_config);
}

bool wifiManagerConnect(unsigned long timeoutMs) {
  unsigned long start = millis();

  // Try primary SSID
  if (s_config.wifi_ssid[0] != '\0') {
    Serial.printf("Connecting to %s...\n", s_config.wifi_ssid);
    WiFi.mode(WIFI_STA);
    WiFi.begin(s_config.wifi_ssid, s_config.wifi_pass);
    while (millis() - start < timeoutMs && WiFi.status() != WL_CONNECTED) {
      delay(200);
      if ((millis() - start) % 2000 < 250) Serial.print(".");
    }
    Serial.println();
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("WiFi OK: %s\n", WiFi.localIP().toString().c_str());
      return true;
    }
    WiFi.disconnect();
    delay(500);
  }

  // Try secondary SSID
  if (s_config.wifi_ssid2[0] != '\0') {
    Serial.printf("Primary failed, trying %s...\n", s_config.wifi_ssid2);
    WiFi.begin(s_config.wifi_ssid2, s_config.wifi_pass2);
    while (millis() - start < timeoutMs + 5000 && WiFi.status() != WL_CONNECTED) {
      delay(200);
      if ((millis() - start) % 2000 < 250) Serial.print(".");
    }
    Serial.println();
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("WiFi OK (secondary): %s\n", WiFi.localIP().toString().c_str());
      return true;
    }
  }

  return false;
}

static WebServer* getServer() {
  return s_settingsServer ? s_settingsServer : s_server;
}

static void handleNotFound() {
  WebServer* svr = getServer();
  if (svr) {
    svr->sendHeader("Location", "http://192.168.4.1/");
    svr->send(302, "text/plain", "");
  }
}

static void handleRootGet() {
  WebServer* svr = getServer();
  if (!svr) return;
  String html = R"raw(
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PRUF Setup</title></head><body>
<h1>PRUF Counter Setup</h1>
<form method="post">
<h2>Primary WiFi</h2>
<label>SSID <input name="ssid" value=")raw";
  html += s_config.wifi_ssid;
  html += R"raw(" maxlength="32"></label><br>
<label>Password <input type="password" name="pass" value=")raw";
  html += s_config.wifi_pass;
  html += R"raw(" maxlength="64"></label><br>
<h2>Fallback WiFi (optional)</h2>
<label>SSID 2 <input name="ssid2" value=")raw";
  html += s_config.wifi_ssid2;
  html += R"raw(" maxlength="32"></label><br>
<label>Password 2 <input type="password" name="pass2" value=")raw";
  html += s_config.wifi_pass2;
  html += R"raw(" maxlength="64"></label><br>
<h2>API</h2>
<label>Count API URL <input name="api" value=")raw";
  html += s_config.api_url;
  html += R"raw(" maxlength=")raw";
  html += String(CONFIG_URL_LEN);
  html += R"raw(" size="40"></label><br>
<label>Poll interval (ms) <input type="number" name="poll" value=")raw";
  html += String(s_config.poll_interval_ms);
  html += R"raw(" min="500" max="60000" step="500"></label><br>
<p><button type="submit">Save & Reconnect</button></p>
</form></body></html>)raw";

  svr->send(200, "text/html", html);
}

static void handleRootPost() {
  WebServer* svr = getServer();
  if (!svr) return;
  if (svr->hasArg("ssid")) {
    strncpy(s_config.wifi_ssid, svr->arg("ssid").c_str(), CONFIG_SSID_LEN);
    s_config.wifi_ssid[CONFIG_SSID_LEN] = '\0';
  }
  if (svr->hasArg("pass")) {
    strncpy(s_config.wifi_pass, svr->arg("pass").c_str(), CONFIG_PASS_LEN);
    s_config.wifi_pass[CONFIG_PASS_LEN] = '\0';
  }
  if (svr->hasArg("ssid2")) {
    strncpy(s_config.wifi_ssid2, svr->arg("ssid2").c_str(), CONFIG_SSID_LEN);
    s_config.wifi_ssid2[CONFIG_SSID_LEN] = '\0';
  }
  if (svr->hasArg("pass2")) {
    strncpy(s_config.wifi_pass2, svr->arg("pass2").c_str(), CONFIG_PASS_LEN);
    s_config.wifi_pass2[CONFIG_PASS_LEN] = '\0';
  }
  if (svr->hasArg("api")) {
    strncpy(s_config.api_url, svr->arg("api").c_str(), CONFIG_URL_LEN);
    s_config.api_url[CONFIG_URL_LEN] = '\0';
  }
  if (svr->hasArg("poll")) {
    uint32_t p = svr->arg("poll").toInt();
    if (p >= 500 && p <= 60000) s_config.poll_interval_ms = p;
  }
  s_config.configured = true;

  if (configSave(&s_config)) {
    svr->send(200, "text/html",
      "<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>"
      "<h1>Saved!</h1><p>Rebooting...</p><script>setTimeout(function(){location='/';},2000);</script>"
      "</body></html>");
    delay(500);
    ESP.restart();
  } else {
    svr->send(500, "text/plain", "Save failed");
  }
}

void wifiManagerStartCaptivePortal() {
  Serial.println("Starting captive portal...");
  WiFi.disconnect(true);
  delay(100);
  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(apIP, apIP, IPAddress(255, 255, 255, 0));
  if (!WiFi.softAP(AP_SSID, AP_PASS)) {
    Serial.println("AP failed");
    return;
  }
  delay(500);  // Let AP stabilize before starting services
  Serial.printf("AP: %s / %s\n", AP_SSID, AP_PASS);
  Serial.printf("Connect and open http://192.168.4.1\n");

  s_dns.start(DNS_PORT, "*", apIP);

  s_server = new WebServer(80);
  if (!s_server) {
    Serial.println("WebServer alloc failed");
    return;
  }
  s_server->on("/", HTTP_GET, handleRootGet);
  s_server->on("/", HTTP_POST, handleRootPost);
  s_server->onNotFound(handleNotFound);
  s_server->begin();

  while (true) {
    s_dns.processNextRequest();
    s_server->handleClient();
    yield();
    delay(10);
  }
}

void wifiManagerStartSettingsServer() {
  if (s_settingsServer) return;
  s_settingsServer = new WebServer(80);
  s_settingsServer->on("/", HTTP_GET, handleRootGet);
  s_settingsServer->on("/", HTTP_POST, handleRootPost);
  s_settingsServer->begin();
  Serial.printf("Settings: http://%s/\n", WiFi.localIP().toString().c_str());
}

void wifiManagerHandleSettings() {
  if (s_settingsServer) {
    s_settingsServer->handleClient();
  }
}

void wifiManagerReconnect() {
  static unsigned long lastAttempt = 0;
  static int tryIdx = 0;
  static int failCount = 0;
  static bool wasConnected = true;  // Start true so first disconnect resets count
  unsigned long now = millis();

  if (WiFi.status() == WL_CONNECTED) {
    wasConnected = true;
    return;
  }
  if (wasConnected) {
    wasConnected = false;
    failCount = 0;  // Reset on new disconnect
  }

  if (now - lastAttempt < 15000) return;
  lastAttempt = now;
  failCount++;

  // After 8 failures (~2 min), start captive portal so user can fix credentials
  if (failCount >= 8) {
    Serial.println("Reconnect failed repeatedly - starting setup portal");
    failCount = 0;
    wifiManagerStartCaptivePortal();
  }

  WiFi.disconnect();
  delay(100);

  const char* ssid = (tryIdx == 0) ? s_config.wifi_ssid : s_config.wifi_ssid2;
  const char* pass = (tryIdx == 0) ? s_config.wifi_pass : s_config.wifi_pass2;

  if (ssid[0] != '\0') {
    Serial.printf("Reconnect: %s\n", ssid);
    WiFi.begin(ssid, pass);
  } else if (tryIdx == 1) {
    WiFi.begin(s_config.wifi_ssid, s_config.wifi_pass);
  }
  tryIdx = (tryIdx + 1) % 2;
}

bool wifiManagerIsConnected() {
  return WiFi.status() == WL_CONNECTED;
}

const ConfigData* wifiManagerGetConfig() {
  return &s_config;
}
