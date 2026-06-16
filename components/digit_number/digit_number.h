#pragma once

#define DIGIT_NUMBER_VERSION "2.2.9"

#include "digit_logic.h"
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

class DigitNumber : public sensor::Sensor, public Component, public camera::CameraListener {
 public:
  void set_camera(esp32_camera::ESP32Camera *camera) { camera_ = camera; }
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
  void set_trigger_pulse_ms(uint32_t ms) { trigger_pulse_ms_ = ms; }
  void set_trigger_cold_wait_ms(uint32_t ms) { trigger_cold_wait_ms_ = ms; }
  void set_trigger_timeout_warm_ms(uint32_t ms) { trigger_timeout_warm_ms_ = ms; }
  void set_trigger_timeout_cold_ms(uint32_t ms) { trigger_timeout_cold_ms_ = ms; }
  void set_delta_threshold(float v) { delta_threshold_ = v; }
  void set_delta_rest_duration_ms(uint32_t ms) { delta_rest_duration_ms_ = ms; }
  void set_auto_trigger_on_ready(bool v) { auto_trigger_on_ready_ = v; }
  void set_decimal_digits(uint8_t d) { decimal_digits_ = d; }
  void set_multiplier(float v) { multiplier_ = v; }
  void set_offset(float v) { offset_ = v; }
  void set_max_value(int32_t v) { max_value_ = v; }
  void set_inverted(bool v) { inverted_ = v; }
  void do_trigger_();
  void force_burst_now();

  void setup() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  void on_camera_image(const std::shared_ptr<camera::CameraImage> &image) override;

 protected:
  void process_image_();
  void publish_all_(const char *state);
  void burst_tick_();
  void wait_for_ok_();
  void trigger_done_();

  esp32_camera::ESP32Camera *camera_{nullptr};
  text_sensor::TextSensor *last_state_sensor_{nullptr};
  std::vector<DigitAnchors> digits_;
  std::vector<DigitGeometry> geometries_;
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
  uint32_t trigger_pulse_ms_{300};
  uint32_t trigger_cold_wait_ms_{2000};
  uint32_t trigger_timeout_warm_ms_{6000};
  uint32_t trigger_timeout_cold_ms_{15000};
  float    delta_threshold_{5.0f};
  uint32_t delta_rest_duration_ms_{60000};

  // burst runtime state
  uint8_t  burst_read_count_{0};
  bool     burst_resting_{false};
  uint32_t burst_rest_start_ms_{0};
  bool     trigger_busy_{false};
  bool     pending_pause_{false};
  uint32_t trigger_start_ms_{0};
  int      wait_ok_remaining_{0};
  bool     burst_had_ok_{false};

  // last_state string for trigger logic
  std::string last_state_str_{"off"};

  bool     auto_trigger_on_ready_{true};
  uint8_t  decimal_digits_{0};
  float    multiplier_{1.0f};
  float    offset_{0.0f};
  int32_t max_value_{-1};
  bool inverted_{false};
  float last_valid_{NAN};
  uint32_t last_valid_ms_{0};
  float prev_burst_value_{NAN};
  uint32_t burst_current_rest_ms_{0};
};

template<typename... Ts>
class TriggerMeasurementAction : public Action<Ts...> {
 public:
  explicit TriggerMeasurementAction(DigitNumber *parent) : parent_(parent) {}
  void play(Ts... x) override { parent_->force_burst_now(); }
 private:
  DigitNumber *parent_;
};

}  // namespace digit_number
}  // namespace esphome
