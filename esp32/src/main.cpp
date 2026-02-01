#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "config.h"
#include "config_nvs.h"
#include "ipixel_ble.h"
#include "png_frames.h"
#include "wifi_manager.h"

IPixelMulti ipixel;
uint32_t lastCount = 0;
unsigned long lastPoll = 0;
unsigned long lastDisplayUpdate = 0;
static const unsigned long REFRESH_DISPLAY_MS = 5000;
static const unsigned long BLE_RECONNECT_COOLDOWN_MS = 10000;

static const unsigned long WIFI_CONNECT_TIMEOUT_MS = 20000;
static const unsigned long SETUP_STABILIZE_DELAY_MS = 2000;
static const unsigned long DISPLAY_PRE_SEND_DELAY_MS = 50;
static const unsigned long DISPLAY_POST_ACK_DELAY_MS = 500;
static const unsigned long LOOP_DELAY_MS = 100;
static const unsigned long WIFI_RETRY_DELAY_MS = 200;

uint32_t fetchCount() {
  if (!wifiManagerIsConnected()) return lastCount;

  const ConfigData* cfg = wifiManagerGetConfig();
  HTTPClient http;
  http.begin(cfg->api_url);
  http.setTimeout(5000);
  int code = http.GET();

  if (code != HTTP_CODE_OK) {
    Serial.printf("API error %d\n", code);
    http.end();
    return lastCount;
  }

  String payload = http.getString();
  http.end();
  payload.trim();  // Remove stray whitespace/CRLF

  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, payload);
  if (err) {
    Serial.printf("JSON parse error: %s (len=%d)\n", err.c_str(), payload.length());
    return lastCount;
  }

  // as<uint32_t> handles int, long, and numeric strings
  uint32_t count = doc["count"].as<uint32_t>();
  return count;
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("PRUF Counter ESP32");

  wifiManagerInit();

  if (!wifiManagerConnect(WIFI_CONNECT_TIMEOUT_MS)) {
    wifiManagerStartCaptivePortal();  // Blocks until config saved, then reboots
  }

  wifiManagerStartSettingsServer();

  BLEDevice::init("");
  Serial.println("Scanning for iPixel displays...");
  int found = ipixel.scan();
  if (found > 0) {
    Serial.printf("Found %d display(s), connecting...\n", found);
    ipixel.connectAll();
    Serial.printf("Connected to %d/%d displays\n", ipixel.connectedCount(), found);
  } else {
    Serial.println("No LED_BLE_ displays found");
  }

  delay(SETUP_STABILIZE_DELAY_MS);  // Let WiFi/network stabilize before first API poll
}

void updateDisplay(uint32_t count) {
  if (!ipixel.isAnyConnected()) return;

  if (count > PNG_FRAME_COUNT - 1) count = PNG_FRAME_COUNT - 1;
  size_t pngLen = 0;
  const uint8_t* png = pngForCount(count, &pngLen);
  if (!png || pngLen == 0) return;

  delay(DISPLAY_PRE_SEND_DELAY_MS);
  if (ipixel.sendImageAll(png, pngLen, DISPLAY_SLOT)) {
    delay(DISPLAY_POST_ACK_DELAY_MS);
    ipixel.showSlotAll(DISPLAY_SLOT);
    lastDisplayUpdate = millis();
  } else if (ipixel.getLastError()[0] != '\0') {
    Serial.printf("Send failed: %s\n", ipixel.getLastError());
  }
}

#if FLASH_ENABLED
void playFlashAnimation(uint32_t count) {
  if (!ipixel.isAnyConnected()) return;
  if (count > PNG_FRAME_COUNT - 1) count = PNG_FRAME_COUNT - 1;

#if FLASH_MODE_INVERT
  // Invert flash: swap text and background colors
  size_t flashLen = 0;
  const uint8_t* flashPng = pngForInvertFlash(count, &flashLen);
  size_t normalLen = 0;
  const uint8_t* normalPng = pngForCount(count, &normalLen);
  
  if (!flashPng || flashLen == 0 || !normalPng || normalLen == 0) return;
  
  for (int i = 0; i < FLASH_REPEAT; i++) {
    delay(DISPLAY_PRE_SEND_DELAY_MS);
    if (ipixel.sendImageAll(flashPng, flashLen, DISPLAY_SLOT)) {
      delay(DISPLAY_POST_ACK_DELAY_MS);
      ipixel.showSlotAll(DISPLAY_SLOT);
      delay(FLASH_DURATION_MS);
    }
    
    delay(DISPLAY_PRE_SEND_DELAY_MS);
    if (ipixel.sendImageAll(normalPng, normalLen, DISPLAY_SLOT)) {
      delay(DISPLAY_POST_ACK_DELAY_MS);
      ipixel.showSlotAll(DISPLAY_SLOT);
      delay(FLASH_DURATION_MS);
    }
  }
#else
  // Screen flash: solid color(s)
  size_t normalLen = 0;
  const uint8_t* normalPng = pngForCount(count, &normalLen);
  if (!normalPng || normalLen == 0) return;
  
  for (int i = 0; i < FLASH_REPEAT; i++) {
    // Flash each screen color
    for (uint8_t flashIdx = 0; flashIdx < PNG_FLASH_SCREEN_COUNT; flashIdx++) {
      size_t flashLen = 0;
      const uint8_t* flashPng = pngForScreenFlash(flashIdx, &flashLen);
      if (!flashPng || flashLen == 0) continue;
      
      delay(DISPLAY_PRE_SEND_DELAY_MS);
      if (ipixel.sendImageAll(flashPng, flashLen, DISPLAY_SLOT)) {
        delay(DISPLAY_POST_ACK_DELAY_MS);
        ipixel.showSlotAll(DISPLAY_SLOT);
        delay(FLASH_DURATION_MS);
      }
    }
    
    // Return to normal
    delay(DISPLAY_PRE_SEND_DELAY_MS);
    if (ipixel.sendImageAll(normalPng, normalLen, DISPLAY_SLOT)) {
      delay(DISPLAY_POST_ACK_DELAY_MS);
      ipixel.showSlotAll(DISPLAY_SLOT);
      delay(FLASH_DURATION_MS);
    }
  }
#endif
  lastDisplayUpdate = millis();
}
#endif

void loop() {
  unsigned long now = millis();

  wifiManagerHandleSettings();
  wifiManagerReconnect();

  if (!ipixel.isAnyConnected()) {
    static unsigned long lastBleReconnect = 0;
    if (now - lastBleReconnect >= BLE_RECONNECT_COOLDOWN_MS) {
      lastBleReconnect = now;
      Serial.println("No displays connected, scanning...");
      if (ipixel.scan() > 0) {
        ipixel.connectAll();
        Serial.printf("Reconnected to %d display(s)\n", ipixel.connectedCount());
      }
    }
  }

  if (!wifiManagerIsConnected()) {
    delay(WIFI_RETRY_DELAY_MS);
    return;
  }

  const ConfigData* cfg = wifiManagerGetConfig();
  if (now - lastPoll >= cfg->poll_interval_ms) {
    lastPoll = now;
    uint32_t count = fetchCount();

    if (count != lastCount || lastCount == 0) {
      bool countIncremented = (lastCount > 0 && count > lastCount);
      lastCount = count;
      Serial.printf("Count: %lu\n", (unsigned long)count);
      
#if FLASH_ENABLED
      // Play flash animation on increment
      if (countIncremented) {
        playFlashAnimation(count);
      } else {
        updateDisplay(count);
      }
#else
      updateDisplay(count);
#endif
    } else if (ipixel.isAnyConnected() && lastDisplayUpdate > 0 &&
               (now - lastDisplayUpdate) >= REFRESH_DISPLAY_MS) {
      updateDisplay(count);
    }
  }

  delay(LOOP_DELAY_MS);
}
