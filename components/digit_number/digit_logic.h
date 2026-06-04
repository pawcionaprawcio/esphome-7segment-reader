#pragma once

#include <cstdint>

namespace esphome {
namespace digit_number {

enum class PixFmt : uint8_t { GRAY = 0, RGB565 = 1 };

struct DigitAnchors {
  uint16_t ax, ay;
  uint16_t dx, dy;
  uint16_t bx, by;
};

struct SegmentCenter {
  uint16_t x, y;
};

struct DigitGeometry {
  SegmentCenter seg[7];
  SegmentCenter bg[2];
};

namespace digit_logic {

constexpr uint8_t SEGMENT_PATTERNS[10] = {
  0b0111111,  // 0: a,b,c,d,e,f
  0b0000110,  // 1: b,c
  0b1011011,  // 2: a,b,d,e,g
  0b1001111,  // 3: a,b,c,d,g
  0b1100110,  // 4: b,c,f,g
  0b1101101,  // 5: a,c,d,f,g
  0b1111101,  // 6: a,c,d,e,f,g
  0b0000111,  // 7: a,b,c
  0b1111111,  // 8: all
  0b1101111,  // 9: a,b,c,d,f,g
};
constexpr uint8_t DASH_BITMASK = 0b1000000;

inline int8_t decode_digit(uint8_t bitmask) {
  for (int i = 0; i < 10; i++) {
    if (SEGMENT_PATTERNS[i] == bitmask)
      return (int8_t)i;
  }
  for (int i = 0; i < 10; i++) {
    const uint8_t diff = bitmask ^ SEGMENT_PATTERNS[i];
    if (diff && (diff & (diff - 1)) == 0)
      return (int8_t)i;
  }
  return -1;
}

inline DigitGeometry derive_geometry(const DigitAnchors &a) {
  const int32_t gx = ((int32_t)a.ax + a.dx) / 2;
  const int32_t gy = ((int32_t)a.ay + a.dy) / 2;
  const int32_t dvx = gx - a.ax;
  const int32_t dvy = gy - a.ay;

  DigitGeometry geo;
  geo.seg[0] = {a.ax,                            a.ay};
  geo.seg[1] = {a.bx,                            a.by};
  geo.seg[2] = {(uint16_t)(a.bx + dvx),          (uint16_t)(a.by + dvy)};
  geo.seg[3] = {a.dx,                            a.dy};
  geo.seg[4] = {(uint16_t)(a.ax + a.dx - a.bx),  (uint16_t)(a.ay + a.dy - a.by)};
  geo.seg[5] = {(uint16_t)(a.ax + gx  - a.bx),   (uint16_t)(a.ay + gy  - a.by)};
  geo.seg[6] = {(uint16_t)gx,                    (uint16_t)gy};
  geo.bg[0]  = {(uint16_t)((a.ax + gx) / 2),     (uint16_t)((a.ay + gy) / 2)};
  geo.bg[1]  = {(uint16_t)((a.dx + gx) / 2),     (uint16_t)((a.dy + gy) / 2)};
  return geo;
}

inline uint8_t sample_brightness(const uint8_t *buf, uint16_t fw, uint16_t fh,
                                  PixFmt fmt, uint16_t cx, uint16_t cy, uint8_t radius) {
  uint32_t sum = 0;
  uint16_t count = 0;
  const int r = radius;

  for (int dy = -r; dy <= r; dy++) {
    for (int dx = -r; dx <= r; dx++) {
      const int x = (int)cx + dx;
      const int y = (int)cy + dy;
      if (x < 0 || x >= (int)fw || y < 0 || y >= (int)fh)
        continue;

      if (fmt == PixFmt::GRAY) {
        sum += buf[y * fw + x];
      } else {
        const uint32_t offset = ((uint32_t)y * fw + x) * 2;
        const uint16_t pixel = ((uint16_t)buf[offset] << 8) | buf[offset + 1];
        const uint8_t rv = ((pixel >> 11) & 0x1F) << 3;
        const uint8_t gv = ((pixel >> 5)  & 0x3F) << 2;
        const uint8_t bv = (pixel         & 0x1F) << 3;
        sum += (77u * rv + 150u * gv + 29u * bv) >> 8;
      }
      count++;
    }
  }
  return (count > 0) ? (uint8_t)(sum / count) : 0;
}

}  // namespace digit_logic
}  // namespace digit_number
}  // namespace esphome
