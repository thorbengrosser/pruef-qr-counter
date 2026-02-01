#include "display_render.h"
#include "font_glyphs.h"
#include <Arduino.h>
#include <stdio.h>
#include <string.h>

static const uint8_t PNG_SIGNATURE[8] = {0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A};

static uint32_t crc32(uint32_t crc, const uint8_t* buf, size_t len) {
  crc ^= 0xFFFFFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= buf[i];
    for (int j = 0; j < 8; j++)
      crc = (crc >> 1) ^ (0xEDB88320 & -(crc & 1));
  }
  return crc ^ 0xFFFFFFFF;
}

static int glyphIndex(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c == ' ') return GLYPH_INDEX_SPACE;
  if (c == 'x') return GLYPH_INDEX_X;
  return -1;
}

// Draw glyph at (x,y) onto RGB bitmap (row-major, 3 bytes per pixel)
// iPixel may expect BGR order - set to 1 to swap R and B (no effect for b/w)
#define USE_BGR 0
static void drawGlyph(uint8_t* rgb, int x, int y, const glyph_t* g, uint8_t r, uint8_t gg, uint8_t b) {
  if (!g || !g->bits || g->w <= 0 || g->h <= 0) return;
  int bytesPerRow = (g->w + 7) / 8;
  if (bytesPerRow <= 0) return;
  for (int gy = 0; gy < g->h; gy++) {
    for (int gx = 0; gx < g->w; gx++) {
      int px = x + gx;
      int py = y + gy;
      if (px < 0 || px >= DISPLAY_WIDTH || py < 0 || py >= DISPLAY_HEIGHT) continue;
      int byteIdx = gy * bytesPerRow + gx / 8;
      int bit = 7 - (gx % 8);
      if (byteIdx < (int)(bytesPerRow * g->h) && (g->bits[byteIdx] & (1 << bit))) {
        int off = (py * DISPLAY_WIDTH + px) * 3;
#if USE_BGR
        rgb[off] = b;
        rgb[off + 1] = gg;
        rgb[off + 2] = r;
#else
        rgb[off] = r;
        rgb[off + 1] = gg;
        rgb[off + 2] = b;
#endif
      }
    }
  }
}

// Render count string "N x" centered
static void renderToBitmap(uint8_t* rgb, uint32_t count, uint8_t tr, uint8_t tg, uint8_t tb,
                           uint8_t br, uint8_t bg, uint8_t bb) {
#if USE_BGR
  for (int i = 0; i < DISPLAY_WIDTH * DISPLAY_HEIGHT * 3; i += 3) {
    rgb[i] = bb;
    rgb[i + 1] = bg;
    rgb[i + 2] = br;
  }
#else
  for (int i = 0; i < DISPLAY_WIDTH * DISPLAY_HEIGHT * 3; i += 3) {
    rgb[i] = br;
    rgb[i + 1] = bg;
    rgb[i + 2] = bb;
  }
#endif

  char buf[16];
  snprintf(buf, sizeof(buf), "%lu x", (unsigned long)count);

  int totalW = 0;
  for (int i = 0; buf[i]; i++) {
    int idx = glyphIndex(buf[i]);
    if (idx >= 0) totalW += GLYPHS[idx].w + 1;  // +1 spacing
  }
  if (totalW > 0) totalW -= 1;

  int x = (DISPLAY_WIDTH - totalW) / 2;
  for (int i = 0; buf[i]; i++) {
    int idx = glyphIndex(buf[i]);
    if (idx < 0) continue;
    const glyph_t* g = &GLYPHS[idx];
    int y = (DISPLAY_HEIGHT - g->h) / 2;
    drawGlyph(rgb, x, y, g, tr, tg, tb);
    x += g->w + 1;
  }
}

// Use miniz for zlib compression - device requires compressed PNG (uncompressed shows black)
#define MINIZ_NO_ZLIB_COMPATIBLE_NAMES
#include "miniz.h"

uint8_t* renderCountToPng(uint32_t count, uint32_t textColor, uint32_t bgColor, size_t* outLen) {
  uint8_t rgb[DISPLAY_WIDTH * DISPLAY_HEIGHT * 3];
  uint8_t tr = (textColor >> 16) & 0xFF;
  uint8_t tg = (textColor >> 8) & 0xFF;
  uint8_t tb = textColor & 0xFF;
  uint8_t br = (bgColor >> 16) & 0xFF;
  uint8_t bg = (bgColor >> 8) & 0xFF;
  uint8_t bb = bgColor & 0xFF;

  renderToBitmap(rgb, count, tr, tg, tb, br, bg, bb);

  // Build raw IDAT input: filter byte 0 + scanline for each row
  size_t rawStride = 1 + DISPLAY_WIDTH * 3;
  size_t rawLen = rawStride * DISPLAY_HEIGHT;
  uint8_t* raw = (uint8_t*)malloc(rawLen);
  if (!raw) return nullptr;

  for (int y = 0; y < DISPLAY_HEIGHT; y++) {
    raw[y * rawStride] = 0;  // filter type: None
    memcpy(raw + y * rawStride + 1, rgb + y * DISPLAY_WIDTH * 3, DISPLAY_WIDTH * 3);
  }

  mz_ulong zlibLen = (mz_ulong)mz_compressBound(rawLen);
  uint8_t* zlibData = (uint8_t*)malloc(zlibLen);
  if (!zlibData) {
    free(raw);
    return nullptr;
  }
  int rc = mz_compress2(zlibData, &zlibLen, raw, (mz_ulong)rawLen, MZ_BEST_SPEED);
  free(raw);
  if (rc != MZ_OK) {
    free(zlibData);
    return nullptr;
  }
  size_t pngMax = 8 + 25 + 12 + (size_t)zlibLen + 12 + 16;
  uint8_t* png = (uint8_t*)malloc(pngMax);
  if (!png) {
    free(zlibData);
    return nullptr;
  }

  size_t pos = 0;
  memcpy(png, PNG_SIGNATURE, 8);
  pos = 8;

  // IHDR
  uint8_t ihdr[13];
  ihdr[0] = (DISPLAY_WIDTH >> 24) & 0xFF;
  ihdr[1] = (DISPLAY_WIDTH >> 16) & 0xFF;
  ihdr[2] = (DISPLAY_WIDTH >> 8) & 0xFF;
  ihdr[3] = DISPLAY_WIDTH & 0xFF;
  ihdr[4] = (DISPLAY_HEIGHT >> 24) & 0xFF;
  ihdr[5] = (DISPLAY_HEIGHT >> 16) & 0xFF;
  ihdr[6] = (DISPLAY_HEIGHT >> 8) & 0xFF;
  ihdr[7] = DISPLAY_HEIGHT & 0xFF;
  ihdr[8] = 8;   // bit depth
  ihdr[9] = 2;   // color type: RGB
  ihdr[10] = 0;  // compression
  ihdr[11] = 0;  // filter
  ihdr[12] = 0;  // interlace

  uint8_t ihdrWithType[17];
  memcpy(ihdrWithType, "IHDR", 4);
  memcpy(ihdrWithType + 4, ihdr, 13);
  uint32_t ihdrCrc = crc32(0, ihdrWithType, 17);

  png[pos++] = 0; png[pos++] = 0; png[pos++] = 0; png[pos++] = 13;
  memcpy(png + pos, "IHDR", 4); pos += 4;
  memcpy(png + pos, ihdr, 13); pos += 13;
  png[pos++] = (ihdrCrc >> 24) & 0xFF;
  png[pos++] = (ihdrCrc >> 16) & 0xFF;
  png[pos++] = (ihdrCrc >> 8) & 0xFF;
  png[pos++] = ihdrCrc & 0xFF;

  uint8_t idatWithType[4];
  memcpy(idatWithType, "IDAT", 4);
  uint32_t idatCrc = crc32(crc32(0, idatWithType, 4), zlibData, (size_t)zlibLen);

  png[pos++] = (zlibLen >> 24) & 0xFF;
  png[pos++] = (zlibLen >> 16) & 0xFF;
  png[pos++] = (zlibLen >> 8) & 0xFF;
  png[pos++] = zlibLen & 0xFF;
  memcpy(png + pos, "IDAT", 4); pos += 4;
  memcpy(png + pos, zlibData, (size_t)zlibLen); pos += (size_t)zlibLen;
  free(zlibData);
  png[pos++] = (idatCrc >> 24) & 0xFF;
  png[pos++] = (idatCrc >> 16) & 0xFF;
  png[pos++] = (idatCrc >> 8) & 0xFF;
  png[pos++] = idatCrc & 0xFF;

  // IEND
  uint32_t iendCrc = crc32(0, (const uint8_t*)"IEND", 4);
  png[pos++] = 0; png[pos++] = 0; png[pos++] = 0; png[pos++] = 0;
  memcpy(png + pos, "IEND", 4); pos += 4;
  png[pos++] = (iendCrc >> 24) & 0xFF;
  png[pos++] = (iendCrc >> 16) & 0xFF;
  png[pos++] = (iendCrc >> 8) & 0xFF;
  png[pos++] = iendCrc & 0xFF;

  *outLen = pos;
  return png;
}
