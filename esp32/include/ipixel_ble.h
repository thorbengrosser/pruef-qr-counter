#ifndef IPIXEL_BLE_H
#define IPIXEL_BLE_H

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>
#include <BLEClient.h>
#include <BLEAdvertisedDevice.h>

// iPixel BLE UUIDs (from pypixelcolor)
#define IPIXEL_WRITE_UUID "0000fa02-0000-1000-8000-00805f9b34fb"
#define IPIXEL_NOTIFY_UUID "0000fa03-0000-1000-8000-00805f9b34fb"

// Device name prefix for auto-discovery
#define IPIXEL_DEVICE_PREFIX "LED_BLE_"
#define IPIXEL_MAX_DISPLAYS 4

class IPixelBLE {
public:
  IPixelBLE();
  ~IPixelBLE();

  // Scan for LED_BLE_* devices, return first address found
  bool scan(const char* prefix = IPIXEL_DEVICE_PREFIX, int timeoutSec = 5);

  // Connect to device at address (format "XX:XX:XX:XX:XX:XX")
  bool connect(const char* address);

  void disconnect();

  bool isConnected() const { return connected_; }

  // Send PNG image bytes (full payload), then show slot
  bool sendImage(const uint8_t* pngData, size_t pngLen, uint8_t saveSlot = 1);

  // Show specified slot on display
  bool showSlot(uint8_t slot = 1);

  const char* getLastError() const { return lastError_; }
  const char* getAddress() const { return deviceAddr_; }

private:
  BLEClient* client_ = nullptr;
  BLERemoteCharacteristic* writeChar_ = nullptr;
  BLERemoteCharacteristic* notifyChar_ = nullptr;
  bool connected_ = false;
  char lastError_[64] = {0};
  char deviceAddr_[18] = {0};

  bool writeChunked(const uint8_t* data, size_t len, bool waitAck = true);
  bool waitForAck(unsigned long timeoutMs = 3000);
  void setError(const char* msg);
};

// Multi-display: scan for all LED_BLE_*, connect to each, broadcast to all
class IPixelMulti {
public:
  IPixelMulti();

  // Scan for all LED_BLE_* devices. Returns count found (max IPIXEL_MAX_DISPLAYS).
  int scan(int timeoutSec = 8);

  // Connect to all found devices.
  void connectAll();

  void disconnectAll();

  bool sendImageAll(const uint8_t* pngData, size_t pngLen, uint8_t saveSlot = 1);
  void showSlotAll(uint8_t slot = 1);

  int connectedCount() const;
  bool isAnyConnected() const;

  const char* getLastError() const;

private:
  IPixelBLE displays_[IPIXEL_MAX_DISPLAYS];
  char addresses_[IPIXEL_MAX_DISPLAYS][18];
  int count_ = 0;
};

#endif
