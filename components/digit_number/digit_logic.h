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

inline int8_t decode_digit(uint8_t /*bitmask*/) { return -1; }

inline DigitGeometry derive_geometry(const DigitAnchors & /*a*/) { return {}; }

inline uint8_t sample_brightness(const uint8_t * /*buf*/, uint16_t /*fw*/, uint16_t /*fh*/,
                                  PixFmt /*fmt*/, uint16_t /*cx*/, uint16_t /*cy*/,
                                  uint8_t /*radius*/) { return 0; }

}  // namespace digit_logic
}  // namespace digit_number
}  // namespace esphome
