#ifndef DISPLAY_RENDER_H
#define DISPLAY_RENDER_H

#include <stdint.h>
#include <stdlib.h>

#define DISPLAY_WIDTH 64
#define DISPLAY_HEIGHT 16

// Render "N x" (count + space + 'x') to 64x16 RGB bitmap, then encode as PNG.
// count: 0-999999, textColor/bgColor: 0xRRGGBB
// Returns malloc'd PNG bytes, or NULL. Caller must free().
uint8_t* renderCountToPng(uint32_t count, uint32_t textColor, uint32_t bgColor, size_t* outLen);

#endif
