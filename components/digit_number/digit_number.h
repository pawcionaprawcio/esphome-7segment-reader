#pragma once

#define DIGIT_NUMBER_VERSION "1.3.3"

#include <array>
#include <memory>
#include <vector>
#include "esphome/core/component.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/components/camera/camera.h"
#include "esphome/components/esp32_camera/esp32_camera.h"
#include "esphome/core/automation.h"
#include "esphome/core/gpio.h"

namespace esphome {
namespace digit_number {

enum class PixFmt : uint8_t { GRAY = 0, RGB565 = 1 };

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
  void set_staleness_sensor(sensor::Sensor *s) { staleness_sensor_ = s; }
  void set_last_state_sensor(text_sensor::TextSensor *s) { last_state_sensor_ = s; }
  void add_digit(DigitAnchors anchors) { digits_.push_back(anchors); }
  void set_sample_radius(uint8_t r) { sample_radius_ = r; }
  void set_threshold(int t) { threshold_ = t; }
  void set_display_off_threshold(uint8_t t) { display_off_threshold_ = t; }
  void set_update_interval(uint32_t ms) { update_interval_ms_ = ms; }
  void set_paused(bool p) { paused_ = p; }
  void set_trigger_pin(GPIOPin *pin) { trigger_pin_ = pin; }
  void set_burst_count(uint8_t count) { burst_count_ = count; }
  void set_burst_trigger_interval(uint32_t ms) { burst_trigger_interval_ms_ = ms; }
  void set_burst_rest_duration(uint32_t ms) { burst_rest_duration_ms_ = ms; }
  void set_max_value(int32_t v) { max_value_ = v; }
  void do_trigger_();

  void setup() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  void on_camera_image(const std::shared_ptr<camera::CameraImage> &image) override;

 protected:
  DigitGeometry derive_geometry_(const DigitAnchors &a) const;
  uint8_t sample_brightness_(const uint8_t *buf, uint16_t fw, uint16_t fh, PixFmt fmt,
                             uint16_t cx, uint16_t cy) const;
  static uint8_t max_gap_threshold_(const std::array<uint8_t, 7> &bright);
  int8_t decode_digit_(uint8_t bitmask) const;
  void process_image_();
  void publish_all_(const char *state);
  void burst_tick_();
  void wait_for_ok_();

  esp32_camera::ESP32Camera *camera_{nullptr};
  sensor::Sensor *staleness_sensor_{nullptr};
  text_sensor::TextSensor *last_state_sensor_{nullptr};
  std::vector<DigitAnchors> digits_;
  std::array<DigitGeometry, 4> geometries_{};
  uint8_t sample_radius_{2};
  int threshold_{-1};
  uint8_t display_off_threshold_{10};
  uint32_t update_interval_ms_{5000};
  uint32_t last_publish_ms_{0};
  bool paused_{false};
  // trigger pin
  GPIOPin *trigger_pin_{nullptr};

  // burst config
  uint8_t  burst_count_{3};
  uint32_t burst_trigger_interval_ms_{10000};
  uint32_t burst_rest_duration_ms_{300000};

  // burst runtime state
  uint8_t  burst_read_count_{0};
  bool     burst_resting_{false};
  uint32_t burst_rest_start_ms_{0};
  bool     trigger_busy_{false};
  int      wait_ok_remaining_{0};
  bool     burst_had_ok_{false};

  // last_state string for trigger logic
  std::string last_state_str_{"off"};

  int32_t max_value_{-1};
  float last_valid_{NAN};
  uint32_t last_valid_ms_{0};

  static const uint8_t SEGMENT_PATTERNS_[10];
  static const uint8_t DASH_BITMASK_ = 0b1000000;  // segment g only
  static const uint8_t ALL_ON_MIN_ = 100;           // min brightness when all segments lit (digit 8)
};

template<typename... Ts>
class TriggerMeasurementAction : public Action<Ts...> {
 public:
  explicit TriggerMeasurementAction(DigitNumber *parent) : parent_(parent) {}
  void play(Ts... x) override { parent_->do_trigger_(); }
 private:
  DigitNumber *parent_;
};

}  // namespace digit_number
}  // namespace esphome
