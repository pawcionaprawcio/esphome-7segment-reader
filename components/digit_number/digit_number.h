#pragma once

#include <array>
#include <memory>
#include <vector>
#include "esphome/core/component.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/camera/camera.h"
#include "esphome/components/esp32_camera/esp32_camera.h"

namespace esphome {
namespace digit_number {

enum class PixFmt : uint8_t { GRAY = 0, RGB565 = 1, RGB888 = 2 };

struct DigitAnchors {
  uint16_t ax, ay;  // top horizontal segment center
  uint16_t gx, gy;  // middle horizontal segment center
  uint16_t bx;      // top-right vertical segment x (y ignored)
};

struct SegmentCenter {
  uint16_t x, y;
};

struct DigitGeometry {
  SegmentCenter seg[7];  // order: a,b,c,d,e,f,g (index = bit position in bitmask)
};

class DigitNumber : public sensor::Sensor, public Component, public camera::CameraListener {
 public:
  void set_camera(esp32_camera::ESP32Camera *camera) { camera_ = camera; }
  void set_frame_width(uint16_t w) { frame_width_ = w; }
  void set_frame_height(uint16_t h) { frame_height_ = h; }
  void add_digit(DigitAnchors anchors) { digits_.push_back(anchors); }
  void set_sample_radius(uint8_t r) { sample_radius_ = r; }
  void set_threshold(int t) { threshold_ = t; }           // -1 = auto
  void set_display_off_threshold(uint8_t t) { display_off_threshold_ = t; }
  void set_update_interval(uint32_t ms) { update_interval_ms_ = ms; }

  void setup() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  void on_camera_image(const std::shared_ptr<camera::CameraImage> &image) override;

 protected:
  DigitGeometry derive_geometry_(const DigitAnchors &a) const;
  uint8_t sample_brightness_(const uint8_t *buf, uint16_t fw, uint16_t fh, PixFmt fmt,
                             uint16_t cx, uint16_t cy) const;
  int8_t decode_digit_(uint8_t bitmask) const;
  void process_image_(std::shared_ptr<camera::CameraImage> image);

  esp32_camera::ESP32Camera *camera_{nullptr};
  uint16_t frame_width_{800};
  uint16_t frame_height_{600};
  std::vector<DigitAnchors> digits_;
  uint8_t sample_radius_{2};
  int threshold_{-1};
  uint8_t display_off_threshold_{10};
  uint32_t update_interval_ms_{5000};
  uint32_t last_publish_ms_{0};

  static const uint8_t SEGMENT_PATTERNS_[10];
};

}  // namespace digit_number
}  // namespace esphome
