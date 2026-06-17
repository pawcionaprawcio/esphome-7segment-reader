#include "digit_number.h"
#include "esphome/core/log.h"
#include "esp_camera.h"
#include <algorithm>
#include <cmath>
#include <cstdio>

namespace esphome {
namespace digit_number {

static const char *const TAG = "digit_number";

void DigitNumber::setup() {
  ESP_LOGI(TAG, "digit_number v%s", DIGIT_NUMBER_VERSION);
  last_valid_ms_ = millis();
  geometries_.reserve(digits_.size());
  for (const auto &da : digits_)
    geometries_.push_back(digit_logic::derive_geometry(da));
  static_cast<camera::Camera *>(camera_)->add_listener(this);
  if (trigger_pin_ != nullptr) {
    trigger_pin_->setup();
    trigger_pin_->digital_write(false);
    burst_current_rest_ms_ = burst_rest_duration_ms_;
    set_interval("burst_tick", burst_trigger_interval_ms_, [this] { burst_tick_(); });
    ESP_LOGI(TAG, "Burst mode: count=%d interval=%ums rest=%ums",
             burst_count_, (unsigned)burst_trigger_interval_ms_,
             (unsigned)burst_rest_duration_ms_);
  }
}

void DigitNumber::on_camera_image(const std::shared_ptr<camera::CameraImage> & /*image*/) {
  if (paused_) return;
  const uint32_t now = millis();
  if (now - last_publish_ms_ >= update_interval_ms_) {
    last_publish_ms_ = now;
    process_image_();
  }
}

void DigitNumber::publish_all_(const char *state) {
  last_state_str_ = state;
  publish_state(last_valid_);
  if (last_state_sensor_)
    last_state_sensor_->publish_state(state);
}

void DigitNumber::process_image_() {
  const int num_digits = (int)digits_.size();

  ESP_LOGD(TAG, "[v" DIGIT_NUMBER_VERSION "] processing frame");
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    ESP_LOGE(TAG, "esp_camera_fb_get failed");
    return;
  }

  PixFmt fmt;
  if (fb->format == PIXFORMAT_GRAYSCALE) {
    fmt = PixFmt::GRAY;
  } else if (fb->format == PIXFORMAT_RGB565) {
    fmt = PixFmt::RGB565;
  } else {
    ESP_LOGE(TAG, "Unsupported pixel format %d. Use GRAYSCALE or RGB565.", fb->format);
    esp_camera_fb_return(fb);
    return;
  }

  const uint8_t *buf = fb->buf;
  const uint16_t fw  = (uint16_t)fb->width;
  const uint16_t fh  = (uint16_t)fb->height;

  std::vector<std::array<uint8_t, 7>> brightness(num_digits);
  std::vector<uint8_t> black_ref(num_digits);
  uint8_t global_max = 0;
  uint8_t global_min = 255;

  for (int d = 0; d < num_digits; d++) {
    for (int s = 0; s < 7; s++) {
      brightness[d][s] = digit_logic::sample_brightness(buf, fw, fh, fmt,
                                                         geometries_[d].seg[s].x,
                                                         geometries_[d].seg[s].y,
                                                         sample_radius_);
      if (brightness[d][s] > global_max)
        global_max = brightness[d][s];
      if (brightness[d][s] < global_min)
        global_min = brightness[d][s];
    }
    const uint8_t bg0 = digit_logic::sample_brightness(buf, fw, fh, fmt,
                                                        geometries_[d].bg[0].x, geometries_[d].bg[0].y,
                                                        sample_radius_);
    const uint8_t bg1 = digit_logic::sample_brightness(buf, fw, fh, fmt,
                                                        geometries_[d].bg[1].x, geometries_[d].bg[1].y,
                                                        sample_radius_);
    black_ref[d] = (uint8_t)(((uint16_t)bg0 + bg1) / 2);
  }

  esp_camera_fb_return(fb);

  if (inverted_) {
    for (int d = 0; d < num_digits; d++) {
      for (int s = 0; s < 7; s++)
        brightness[d][s] = 255 - brightness[d][s];
      black_ref[d] = 255 - black_ref[d];
    }
    global_max = 255 - global_min;
    ESP_LOGD(TAG, "Inverted mode: effective global_max=%d", global_max);
  }

  if (global_max < display_off_threshold_) {
    ESP_LOGW(TAG, "Display off (max brightness %d < %d)", global_max, display_off_threshold_);
    publish_all_("off");
    return;
  }

  std::vector<uint8_t> bitmasks(num_digits);
  std::vector<uint8_t> thresholds(num_digits);
  for (int d = 0; d < num_digits; d++) {
    uint8_t thresh;
    if (threshold_ >= 0) {
      thresh = (uint8_t)threshold_;
    } else {
      const uint8_t bright_max = *std::max_element(brightness[d].begin(), brightness[d].end());
      thresh = (uint8_t)(((uint16_t)black_ref[d] + bright_max) / 2);
    }
    thresholds[d] = thresh;
    uint8_t bm = 0;
    for (int s = 0; s < 7; s++) {
      if (brightness[d][s] >= thresh)
        bm |= (1 << s);
    }
    bitmasks[d] = bm;
    ESP_LOGV(TAG, "Digit %d: bg=%d thresh=%d bitmask=0x%02X (segs a=%d b=%d c=%d d=%d e=%d f=%d g=%d)",
             d, black_ref[d], thresh, bm,
             brightness[d][0], brightness[d][1], brightness[d][2], brightness[d][3],
             brightness[d][4], brightness[d][5], brightness[d][6]);
  }

  bool all_zero = true;
  for (int d = 0; d < num_digits; d++) {
    if (bitmasks[d] != 0) { all_zero = false; break; }
  }
  if (all_zero) {
    ESP_LOGW(TAG, "All bitmasks zero (noise/dark) → off");
    publish_all_("off");
    return;
  }

  bool all_dash = true;
  for (int d = 0; d < num_digits; d++) {
    if (bitmasks[d] != digit_logic::DASH_BITMASK) { all_dash = false; break; }
  }
  if (all_dash) {
    ESP_LOGD(TAG, "Display ready (all dashes)");
    publish_all_("ready");
    if (auto_trigger_on_ready_ && trigger_pin_ != nullptr && !trigger_busy_) {
      ESP_LOGI(TAG, "Display ready — triggering measurement");
      do_trigger_();
    }
    return;
  }

  int32_t value = 0;

  for (int d = 0; d < num_digits; d++) {
    const int8_t digit = digit_logic::decode_digit(bitmasks[d]);
    if (digit < 0) {
      ESP_LOGW(TAG, "Unknown bitmask 0x%02X for digit %d", bitmasks[d], d);
      publish_all_("fail");
      return;
    }
    int32_t place_value = 1;
    for (int k = d + 1; k < num_digits; k++) place_value *= 10;
    value += digit * place_value;
  }

  if (max_value_ >= 0 && value > max_value_) {
    ESP_LOGW(TAG, "Value %d > max_value %d, treating as read error", (int)value, (int)max_value_);
    publish_all_("fail");
    return;
  }

  float fval = (float)value;
  if (decimal_digits_ > 0) {
    float divisor = 1.0f;
    for (uint8_t i = 0; i < decimal_digits_; i++) divisor *= 10.0f;
    fval /= divisor;
  }
  fval = fval * multiplier_ + offset_;
  if (anomaly_sensor_ != nullptr && !std::isnan(prev_burst_value_) &&
      std::abs(fval - prev_burst_value_) > delta_threshold_) {
    char abuf[256];
    int apos = snprintf(abuf, sizeof(abuf), "val=%.0f prev=%.0f delta=%+.0f",
                        fval, prev_burst_value_, fval - prev_burst_value_);
    for (int d = 0; d < num_digits && apos < (int)sizeof(abuf) - 1; d++) {
      apos += snprintf(abuf + apos, sizeof(abuf) - apos,
                       " |d%d:a=%d d=%d g=%d t=%d",
                       d, brightness[d][0], brightness[d][3], brightness[d][6], thresholds[d]);
    }
    ESP_LOGW(TAG, "Anomaly: %s", abuf);
    anomaly_sensor_->publish_state(abuf);
  }
  last_valid_ = fval;
  last_valid_ms_ = millis();
  last_state_str_ = "ok";
  burst_had_ok_ = true;
  if (trigger_pin_ != nullptr) {
    burst_readings_.push_back(fval);
    ESP_LOGD(TAG, "Burst reading #%d: %.4f (raw=%d)", (int)burst_readings_.size(), fval, (int)value);
  } else {
    ESP_LOGD(TAG, "Publishing value: %.4f (raw=%d)", fval, (int)value);
    publish_state(last_valid_);
  }
  if (last_state_sensor_)
    last_state_sensor_->publish_state("ok");
}

void DigitNumber::burst_tick_() {
  if (burst_resting_) {
    if (millis() - burst_rest_start_ms_ < burst_current_rest_ms_) {
      ESP_LOGD(TAG, "Burst resting...");
      return;
    }
    ESP_LOGI(TAG, "Burst rest done, resuming");
    burst_resting_ = false;
    burst_read_count_ = 0;
    burst_readings_.clear();
    paused_ = false;
  }
  if (trigger_busy_) {
    ESP_LOGD(TAG, "Trigger busy, skipping tick");
    return;
  }
  do_trigger_();
  burst_read_count_++;
  ESP_LOGI(TAG, "Burst read %d/%d", burst_read_count_, burst_count_);
  if (burst_read_count_ >= burst_count_) {
    if (!burst_had_ok_) {
      ESP_LOGW(TAG, "Burst done but no valid read — retrying burst");
      burst_read_count_ = 0;
      return;
    }
    burst_had_ok_ = false;
    if (!burst_readings_.empty()) {
      int best_idx = (int)burst_readings_.size() - 1;
      if (!std::isnan(prev_burst_value_)) {
        float best_dist = std::abs(burst_readings_[best_idx] - prev_burst_value_);
        for (int i = 0; i < (int)burst_readings_.size(); i++) {
          const float d = std::abs(burst_readings_[i] - prev_burst_value_);
          if (d < best_dist) { best_dist = d; best_idx = i; }
        }
      }
      float best = burst_readings_[best_idx];
      char rbuf[128];
      int rpos = 0;
      for (int i = 0; i < (int)burst_readings_.size(); i++) {
        rpos += snprintf(rbuf + rpos, sizeof(rbuf) - rpos,
                         i == best_idx ? "[%.2f] " : "%.2f ", burst_readings_[i]);
        if (rpos >= (int)sizeof(rbuf) - 1) break;
      }
      ESP_LOGI(TAG, "Burst end: readings=%s→ publish=%.2f prev=%.2f", rbuf, best, prev_burst_value_);
      last_valid_ = best;
      publish_state(best);
      if (last_state_sensor_) last_state_sensor_->publish_state("ok");
      burst_readings_.clear();
    }
    if (!std::isnan(prev_burst_value_) && !std::isnan(last_valid_)) {
      const float delta = std::abs(last_valid_ - prev_burst_value_);
      if (delta >= delta_threshold_) {
        burst_current_rest_ms_ = std::min(burst_rest_duration_ms_, delta_rest_duration_ms_);
        ESP_LOGI(TAG, "Burst done: delta=%.2f >= %.2f, rest shortened to %ums", delta, delta_threshold_, (unsigned)burst_current_rest_ms_);
      } else {
        burst_current_rest_ms_ = burst_rest_duration_ms_;
        ESP_LOGI(TAG, "Burst done: delta=%.2f < %.2f, resting %ums", delta, delta_threshold_, (unsigned)burst_current_rest_ms_);
      }
    } else {
      burst_current_rest_ms_ = burst_rest_duration_ms_;
      ESP_LOGI(TAG, "Burst done, resting %ums", (unsigned)burst_current_rest_ms_);
    }
    if (!std::isnan(last_valid_))
      prev_burst_value_ = last_valid_;
    burst_resting_ = true;
    burst_rest_start_ms_ = millis();
    if (trigger_busy_) {
      pending_pause_ = true;  // pause after trigger completes so last read can be captured
    } else {
      paused_ = true;
    }
  }
}

void DigitNumber::force_burst_now() {
  if (burst_resting_) {
    ESP_LOGI(TAG, "Take Measurement: cancelling rest, starting burst now");
    burst_resting_ = false;
    burst_read_count_ = 0;
    burst_readings_.clear();
    paused_ = false;
    pending_pause_ = false;
    burst_had_ok_ = false;
    burst_tick_();
  } else {
    do_trigger_();
  }
}

void DigitNumber::do_trigger_() {
  if (trigger_pin_ == nullptr) return;
  trigger_busy_ = true;
  trigger_start_ms_ = millis();
  if (last_state_str_ == "off") {
    trigger_pin_->digital_write(true);
    set_timeout("trig_w1", trigger_pulse_ms_, [this]() {
      trigger_pin_->digital_write(false);
      set_timeout("trig_w2", trigger_cold_wait_ms_, [this]() {
        trigger_pin_->digital_write(true);
        set_timeout("trig_m_cold", trigger_pulse_ms_, [this]() {
          trigger_pin_->digital_write(false);
          wait_ok_remaining_ = (int)(trigger_timeout_cold_ms_ / 200);
          wait_for_ok_();
        });
      });
    });
  } else {
    trigger_pin_->digital_write(true);
    set_timeout("trig_m", trigger_pulse_ms_, [this]() {
      trigger_pin_->digital_write(false);
      wait_ok_remaining_ = (int)(trigger_timeout_warm_ms_ / 200);
      wait_for_ok_();
    });
  }
}

void DigitNumber::trigger_done_() {
  trigger_busy_ = false;
  if (pending_pause_) {
    pending_pause_ = false;
    paused_ = true;
    ESP_LOGI(TAG, "Trigger complete — entering burst rest");
  }
}

void DigitNumber::wait_for_ok_() {
  if (last_state_str_ == "ok" && last_valid_ms_ > trigger_start_ms_) {
    ESP_LOGD(TAG, "Trigger: got ok (fresh read after trigger)");
    trigger_done_();
    return;
  }
  if (wait_ok_remaining_ <= 0) {
    ESP_LOGW(TAG, "Trigger: timeout waiting for ok");
    trigger_done_();
    return;
  }
  wait_ok_remaining_--;
  set_timeout("wait_ok", 200, [this]() { wait_for_ok_(); });
}

}  // namespace digit_number
}  // namespace esphome
