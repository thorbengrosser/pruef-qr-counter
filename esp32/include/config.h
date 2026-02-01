#ifndef CONFIG_H
#define CONFIG_H

#ifndef WIFI_SSID
#define WIFI_SSID "eleanor_angrynathy"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS "109802why?"
#endif
#ifndef API_URL
#define API_URL "http://pruef.st/api/count"
#endif

#define POLL_INTERVAL_MS 1000
#define DISPLAY_SLOT 1

// Flash animation settings
#define FLASH_ENABLED 1              // Set to 0 to disable flash animations
#define FLASH_MODE_INVERT 1           // 0 = screen flash (solid colors), 1 = invert flash (swapped colors)
#define FLASH_DURATION_MS 150         // Duration of each flash state in milliseconds
#define FLASH_REPEAT 3                // Number of flash cycles (flash on/off pairs)

#define DEBUG_PNG 0
#define DEBUG_PNG_DUMP 0

#endif
