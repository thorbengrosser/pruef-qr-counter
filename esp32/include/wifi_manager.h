#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include "config_nvs.h"

// Call once at startup. Initializes NVS. Loads config into global.
void wifiManagerInit();

// Try to connect using stored config (primary, then secondary). Returns true if connected.
// Blocks for up to timeoutMs.
bool wifiManagerConnect(unsigned long timeoutMs);

// Reconnect attempt (primary, then secondary). Call periodically.
// If still disconnected after CAPTIVE_PORTAL_AFTER_FAILURES cycles, starts captive portal (blocks).
void wifiManagerReconnect();

// Start AP + captive portal. Blocks until user saves config, then reboots.
// Call when wifiManagerConnect() returns false.
void wifiManagerStartCaptivePortal();

// Returns true if WiFi is connected.
bool wifiManagerIsConnected();

// Get current config (for display/fetchCount).
const ConfigData* wifiManagerGetConfig();

// Start settings web server (call when STA connected). Serve settings page.
void wifiManagerStartSettingsServer();

// Handle settings server requests. Call from loop().
void wifiManagerHandleSettings();

#endif
