#include "ipixel_ble.h"
#include <string.h>
#include <string>

// Protocol: 2-byte length prefix, then [0x02, 0x00, option] + 4-byte size LE + 4-byte CRC32 LE + [0x00, save_slot] + PNG chunk
// Device sends ACK on notify: data[0]==0x05, data[4] in (0,1)=window ack, 3=final
static const int WINDOW_CHUNK_SIZE = 244;
static volatile bool s_ackReceived = false;

static void onNotify(BLERemoteCharacteristic* pChar, uint8_t* data, size_t len, bool isNotify) {
  (void)pChar;
  (void)isNotify;
  // Reduced verbosity - only log if DEBUG_PNG is enabled
#if DEBUG_PNG
  Serial.printf("Notify %u bytes: ", (unsigned)len);
  for (size_t i = 0; i < len && i < 16; i++) Serial.printf("%02x ", data[i]);
  if (len > 16) Serial.print("...");
  Serial.println();
#endif
  if (len >= 5 && data[0] == 0x05 && (data[4] == 0 || data[4] == 1 || data[4] == 3)) {
    s_ackReceived = true;
  }
}

static uint32_t crc32_le(const uint8_t* data, size_t len) {
  uint32_t crc = 0xFFFFFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (int j = 0; j < 8; j++) {
      crc = (crc >> 1) ^ (0xEDB88320 & -(crc & 1));
    }
  }
  return crc ^ 0xFFFFFFFF;
}

// Scan callback - improved to avoid memory leaks
static BLEAdvertisedDevice* foundDevice = nullptr;
static const char* scanPrefix = nullptr;

class ScanCallbacks : public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice advertisedDevice) override {
    if (!scanPrefix) return;
    const char* name = advertisedDevice.getName().c_str();
    if (name && strncmp(name, scanPrefix, strlen(scanPrefix)) == 0) {
      advertisedDevice.getScan()->stop();
      // Clean up previous device if any
      if (foundDevice) {
        delete foundDevice;
        foundDevice = nullptr;
      }
      foundDevice = new BLEAdvertisedDevice(advertisedDevice);
    }
  }
};

IPixelBLE::IPixelBLE() {
  lastError_[0] = '\0';
  deviceAddr_[0] = '\0';
}

IPixelBLE::~IPixelBLE() {
  disconnect();
}

void IPixelBLE::setError(const char* msg) {
  strncpy(lastError_, msg, sizeof(lastError_) - 1);
  lastError_[sizeof(lastError_) - 1] = '\0';
}

bool IPixelBLE::scan(const char* prefix, int timeoutSec) {
  // Clean up any previous scan result
  if (foundDevice) {
    delete foundDevice;
    foundDevice = nullptr;
  }
  
  foundDevice = nullptr;
  scanPrefix = prefix;

  BLEScan* scan = BLEDevice::getScan();
  scan->setAdvertisedDeviceCallbacks(new ScanCallbacks());
  scan->setActiveScan(true);
  BLEScanResults results = scan->start(timeoutSec);

  scan->clearResults();

  if (!foundDevice) {
    setError("No LED_BLE_ device found");
    scanPrefix = nullptr;  // Reset prefix
    return false;
  }

  strncpy(deviceAddr_, foundDevice->getAddress().toString().c_str(), sizeof(deviceAddr_) - 1);
  deviceAddr_[sizeof(deviceAddr_) - 1] = '\0';
  delete foundDevice;
  foundDevice = nullptr;
  scanPrefix = nullptr;  // Reset prefix

  return true;
}

bool IPixelBLE::connect(const char* address) {
  if (connected_) {
    disconnect();
  }

  BLEAddress addr(address);
  client_ = BLEDevice::createClient();
  if (!client_->connect(addr)) {
    setError("BLE connect failed");
    return false;
  }

  BLEUUID writeUuid(IPIXEL_WRITE_UUID);
  BLEUUID notifyUuid(IPIXEL_NOTIFY_UUID);
  BLERemoteService* svc = client_->getService(BLEUUID("0000fa00-0000-1000-8000-00805f9b34fb"));
  if (svc) {
    writeChar_ = svc->getCharacteristic(writeUuid);
    notifyChar_ = svc->getCharacteristic(notifyUuid);
  }
  if (!writeChar_) {
    std::map<std::string, BLERemoteService*>* services = client_->getServices();
    if (services) {
      for (auto it = services->begin(); it != services->end(); ++it) {
        writeChar_ = it->second->getCharacteristic(writeUuid);
        if (writeChar_) {
          notifyChar_ = it->second->getCharacteristic(notifyUuid);
          break;
        }
      }
    }
  }
  if (!writeChar_ || !writeChar_->canWrite()) {
    client_->disconnect();
    setError("Write char not found");
    return false;
  }

  if (notifyChar_) {
    notifyChar_->registerForNotify(onNotify, false);  // false = indicate (0x02), device may use indicate
    Serial.println("Subscribed to notify/indicate");
  } else {
    Serial.println("Notify char not found - no ACK wait");
  }

  connected_ = true;
  strncpy(deviceAddr_, address, sizeof(deviceAddr_) - 1);
  return true;
}

void IPixelBLE::disconnect() {
  if (client_) {
    client_->disconnect();
    delete client_;
    client_ = nullptr;
  }
  writeChar_ = nullptr;
  notifyChar_ = nullptr;
  connected_ = false;
}

bool IPixelBLE::writeChunked(const uint8_t* data, size_t len, bool waitAck) {
  if (!writeChar_) return false;

  size_t pos = 0;
  while (pos < len) {
    size_t chunkLen = min((size_t)WINDOW_CHUNK_SIZE, len - pos);
    writeChar_->writeValue(const_cast<uint8_t*>(data + pos), chunkLen, true);  // response=true for ack
    pos += chunkLen;
    delay(30);  // Give device time to process each chunk
  }

  (void)waitAck;
  return true;
}

bool IPixelBLE::waitForAck(unsigned long timeoutMs) {
  s_ackReceived = false;
  unsigned long start = millis();
  while (millis() - start < timeoutMs) {
    if (s_ackReceived) return true;
    delay(10);
  }
  return false;
}

bool IPixelBLE::sendImage(const uint8_t* pngData, size_t pngLen, uint8_t saveSlot) {
  if (!connected_ || !writeChar_) return false;

  uint32_t crc = crc32_le(pngData, pngLen);

  // Build header: [0x02, 0x00, 0x00] + 4B size LE + 4B CRC LE + [0x00, save_slot]
  uint8_t header[13];
  header[0] = 0x02;
  header[1] = 0x00;
  header[2] = 0x00;
  header[3] = (pngLen >> 0) & 0xFF;
  header[4] = (pngLen >> 8) & 0xFF;
  header[5] = (pngLen >> 16) & 0xFF;
  header[6] = (pngLen >> 24) & 0xFF;
  header[7] = (crc >> 0) & 0xFF;
  header[8] = (crc >> 8) & 0xFF;
  header[9] = (crc >> 16) & 0xFF;
  header[10] = (crc >> 24) & 0xFF;
  header[11] = 0x00;
  header[12] = saveSlot;

  size_t innerLen = 13 + pngLen;
  if (innerLen > 12000) {
    setError("Image too large");
    return false;
  }

  uint16_t totalLen = 2 + innerLen;
  uint8_t* buf = (uint8_t*)malloc(totalLen);
  if (!buf) {
    setError("Out of memory");
    return false;
  }
  buf[0] = totalLen & 0xFF;
  buf[1] = (totalLen >> 8) & 0xFF;
  memcpy(buf + 2, header, 13);
  memcpy(buf + 15, pngData, pngLen);

  s_ackReceived = false;
  bool ok = writeChunked(buf, totalLen);
  free(buf);
  if (!ok) return false;

  if (!waitForAck(3000)) {
    // Reduced verbosity - ACK is optional, device still updates
#if DEBUG_PNG
    Serial.println("No ACK from device (continuing anyway)");
#endif
  }
  return true;
}

bool IPixelBLE::showSlot(uint8_t slot) {
  if (!connected_ || !writeChar_) return false;

  uint8_t cmd[] = {0x07, 0x00, 0x08, 0x80, 0x01, 0x00, (uint8_t)(slot & 0xFF)};
  uint8_t buf[2 + sizeof(cmd)];
  buf[0] = (uint8_t)(2 + sizeof(cmd));
  buf[1] = 0x00;
  memcpy(buf + 2, cmd, sizeof(cmd));
  return writeChunked(buf, sizeof(buf));
}

// --- IPixelMulti ---

IPixelMulti::IPixelMulti() {
  count_ = 0;
  for (int i = 0; i < IPIXEL_MAX_DISPLAYS; i++) {
    addresses_[i][0] = '\0';
  }
}

int IPixelMulti::scan(int timeoutSec) {
  count_ = 0;
  BLEScan* scan = BLEDevice::getScan();
  scan->setActiveScan(true);
  scan->setAdvertisedDeviceCallbacks(nullptr);
  BLEScanResults results = scan->start(timeoutSec, false);

  size_t prefixLen = strlen(IPIXEL_DEVICE_PREFIX);
  for (int i = 0; i < results.getCount() && count_ < IPIXEL_MAX_DISPLAYS; i++) {
    BLEAdvertisedDevice dev = results.getDevice(i);
    std::string name = dev.getName();
    if (name.length() >= prefixLen && name.substr(0, prefixLen) == IPIXEL_DEVICE_PREFIX) {
      strncpy(addresses_[count_], dev.getAddress().toString().c_str(), 17);
      addresses_[count_][17] = '\0';
      count_++;
    }
  }
  scan->clearResults();
  return count_;
}

void IPixelMulti::connectAll() {
  for (int i = 0; i < count_; i++) {
    if (displays_[i].connect(addresses_[i])) {
      Serial.printf("Connected to display %d: %s\n", i + 1, addresses_[i]);
    } else {
      Serial.printf("Failed to connect to %s: %s\n", addresses_[i], displays_[i].getLastError());
    }
  }
}

void IPixelMulti::disconnectAll() {
  for (int i = 0; i < IPIXEL_MAX_DISPLAYS; i++) {
    displays_[i].disconnect();
  }
}

bool IPixelMulti::sendImageAll(const uint8_t* pngData, size_t pngLen, uint8_t saveSlot) {
  bool anyOk = false;
  for (int i = 0; i < count_; i++) {
    if (displays_[i].isConnected()) {
      if (displays_[i].sendImage(pngData, pngLen, saveSlot)) {
        anyOk = true;
      }
    }
  }
  return anyOk;
}

void IPixelMulti::showSlotAll(uint8_t slot) {
  for (int i = 0; i < count_; i++) {
    if (displays_[i].isConnected()) {
      displays_[i].showSlot(slot);
    }
  }
}

int IPixelMulti::connectedCount() const {
  int n = 0;
  for (int i = 0; i < count_; i++) {
    if (displays_[i].isConnected()) n++;
  }
  return n;
}

bool IPixelMulti::isAnyConnected() const {
  return connectedCount() > 0;
}

const char* IPixelMulti::getLastError() const {
  for (int i = 0; i < count_; i++) {
    if (strlen(displays_[i].getLastError()) > 0) {
      return displays_[i].getLastError();
    }
  }
  return "";
}
