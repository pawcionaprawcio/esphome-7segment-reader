#include "digit_number.h"
#include "esphome/core/log.h"
#include "esp_camera.h"
#include <algorithm>

namespace esphome {
namespace digit_number {

static const char *const TAG = "digit_number";

// bit 0=a, 1=b, 2=c, 3=d, 4=e, 5=f, 6=g
const uint8_t DigitNumber::SEGMENT_PATTERNS_[10] = {
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

DigitGeometry DigitNumber::derive_geometry_(const DigitAnchors &a) const {
  const uint16_t x_right = a.bx;
  const uint16_t x_left  = (uint16_t)(2 * a.ax - a.bx);
  const uint16_t y_top   = a.ay;
  const uint16_t y_mid   = a.gy;
  const uint16_t y_bot   = (uint16_t)(2 * a.gy - a.ay);
  const uint16_t y_th    = (uint16_t)((a.ay + a.gy) / 2);
  const uint16_t y_bh    = (uint16_t)((a.gy + y_bot) / 2);

  DigitGeometry geo;
  geo.seg[0] = {a.ax,    y_top};   // a
  geo.seg[1] = {x_right, y_th};    // b
  geo.seg[2] = {x_right, y_bh};    // c
  geo.seg[3] = {a.ax,    y_bot};   // d
  geo.seg[4] = {x_left,  y_bh};    // e
  geo.seg[5] = {x_left,  y_th};    // f
  geo.seg[6] = {a.gx,    y_mid};   // g
  return geo;
}

uint8_t DigitNumber::max_gap_threshold_(const std::array<uint8_t, 7> &bright) {
  if (*std::min_element(bright.begin(), bright.end()) > ALL_ON_MIN_)
    return 0;  // all segments clearly ON (e.g. digit 8 with uniform backlight)
  std::array<uint8_t, 7> s = bright;
  std::sort(s.begin(), s.end());
  uint8_t best_gap = 0, gap_pos = 0;
  for (int i = 0; i < 6; i++) {
    const uint8_t g = s[i + 1] - s[i];
    if (g > best_gap) { best_gap = g; gap_pos = i; }
  }
  return (s[gap_pos] + s[gap_pos + 1]) / 2;
}

uint8_t DigitNumber::sample_brightness_(const uint8_t *buf, uint16_t fw, uint16_t fh,
                                        PixFmt fmt, uint16_t cx, uint16_t cy) const {
  uint32_t sum = 0;
  uint16_t count = 0;
  const int r = sample_radius_;

  for (int dy = -r; dy <= r; dy++) {
    for (int dx = -r; dx <= r; dx++) {
      const int x = (int)cx + dx;
      const int y = (int)cy + dy;
      if (x < 0 || x >= (int)fw || y < 0 || y >= (int)fh)
        continue;

      if (fmt == PixFmt::GRAY) {
        sum += buf[y * fw + x];
      } else {
        // RGB565
        const uint32_t offset = ((uint32_t)y * fw + x) * 2;
        const uint16_t pixel = ((uint16_t)buf[offset] << 8) | buf[offset + 1];
        const uint8_t rv = ((pixel >> 11) & 0x1F) << 3;
        const uint8_t gv = ((pixel >> 5)  & 0x3F) << 2;
        const uint8_t bv = (pixel         & 0x1F) << 3;
        sum += (77u * rv + 150u * gv + 29u * bv) >> 8;  // BT.601
      }
      count++;
    }
  }
  return (count > 0) ? (uint8_t)(sum / count) : 0;
}

int8_t DigitNumber::decode_digit_(uint8_t bitmask) const {
  for (int i = 0; i < 10; i++) {
    if (SEGMENT_PATTERNS_[i] == bitmask)
      return (int8_t)i;
  }
  // 1-bit Hamming tolerance: accept if exactly one segment is borderline
  for (int i = 0; i < 10; i++) {
    const uint8_t diff = bitmask ^ SEGMENT_PATTERNS_[i];
    if (diff && (diff & (diff - 1)) == 0) {
      ESP_LOGW(TAG, "Fuzzy match 0x%02X -> digit %d (1-bit off, diff=0x%02X)", bitmask, i, diff);
      return (int8_t)i;
    }
  }
  return -1;
}

void DigitNumber::setup() {
  ESP_LOGI(TAG, "digit_number v%s", DIGIT_NUMBER_VERSION);
  last_valid_ms_ = millis();
  for (int d = 0; d < (int)digits_.size() && d < 4; d++)
    geometries_[d] = derive_geometry_(digits_[d]);
  static_cast<camera::Camera *>(camera_)->add_listener(this);
  if (trigger_pin_ != nullptr) {
    trigger_pin_->setup();
    trigger_pin_->digital_write(false);
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
  if (staleness_sensor_)
    staleness_sensor_->publish_state((float)((millis() - last_valid_ms_) / 1000));
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

  std::array<std::array<uint8_t, 7>, 4> brightness{};
  uint8_t global_max = 0;

  for (int d = 0; d < num_digits; d++) {
    for (int s = 0; s < 7; s++) {
      brightness[d][s] = sample_brightness_(buf, fw, fh, fmt,
                                            geometries_[d].seg[s].x,
                                            geometries_[d].seg[s].y);
      if (brightness[d][s] > global_max)
        global_max = brightness[d][s];
    }
  }

  esp_camera_fb_return(fb);

  if (global_max < display_off_threshold_) {
    ESP_LOGW(TAG, "Display off (max brightness %d < %d)", global_max, display_off_threshold_);
    publish_all_("off");
    return;
  }

  std::array<uint8_t, 4> bitmasks{};
  for (int d = 0; d < num_digits; d++) {
    const uint8_t thresh = (threshold_ < 0)
        ? max_gap_threshold_(brightness[d])
        : (uint8_t)threshold_;
    uint8_t bm = 0;
    for (int s = 0; s < 7; s++) {
      if (brightness[d][s] >= thresh)
        bm |= (1 << s);
    }
    bitmasks[d] = bm;
    ESP_LOGD(TAG, "Digit %d: thresh=%d bitmask=0x%02X (segs a=%d b=%d c=%d d=%d e=%d f=%d g=%d)",
             d, thresh, bm,
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
    if (bitmasks[d] != DASH_BITMASK_) { all_dash = false; break; }
  }
  if (all_dash) {
    ESP_LOGD(TAG, "Display ready (all dashes)");
    publish_all_("ready");
    return;
  }

  int32_t value = 0;
  const int32_t multipliers[4] = {1000, 100, 10, 1};

  for (int d = 0; d < num_digits; d++) {
    const int8_t digit = decode_digit_(bitmasks[d]);
    if (digit < 0) {
      ESP_LOGW(TAG, "Unknown bitmask 0x%02X for digit %d", bitmasks[d], d);
      publish_all_("fail");
      return;
    }
    value += digit * multipliers[d];
  }

  ESP_LOGD(TAG, "Publishing value: %d mm", (int)value);
  last_valid_ = (float)value;
  last_valid_ms_ = millis();
  publish_state(last_valid_);
  if (staleness_sensor_)
    staleness_sensor_->publish_state(0.0f);
  if (last_state_sensor_)
    last_state_sensor_->publish_state("ok");
}

void DigitNumber::burst_tick_() {
  if (burst_resting_) {
    if (millis() - burst_rest_start_ms_ < burst_rest_duration_ms_) {
      ESP_LOGD(TAG, "Burst resting...");
      return;
    }
    ESP_LOGI(TAG, "Burst rest done, resuming");
    burst_resting_ = false;
    burst_read_count_ = 0;
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
    burst_resting_ = true;
    burst_rest_start_ms_ = millis();
    paused_ = true;
    ESP_LOGI(TAG, "Burst done, resting %ums", (unsigned)burst_rest_duration_ms_);
  }
}

void DigitNumber::do_trigger_() {
  if (trigger_pin_ == nullptr) return;
  trigger_busy_ = true;
  if (last_state_str_ == "off") {
    trigger_pin_->digital_write(true);
    set_timeout("trig_w1", 300, [this]() {
      trigger_pin_->digital_write(false);
      set_timeout("trig_w2", 2000, [this]() {
        trigger_pin_->digital_write(true);
        set_timeout("trig_m_cold", 300, [this]() {
          trigger_pin_->digital_write(false);
          wait_ok_remaining_ = 30;
          wait_for_ok_();
        });
      });
    });
  } else {
    trigger_pin_->digital_write(true);
    set_timeout("trig_m", 300, [this]() {
      trigger_pin_->digital_write(false);
      wait_ok_remaining_ = 30;
      wait_for_ok_();
    });
  }
}

void DigitNumber::wait_for_ok_() {
  if (last_state_str_ == "ok") {
    ESP_LOGD(TAG, "Trigger: got ok");
    trigger_busy_ = false;
    return;
  }
  if (wait_ok_remaining_ <= 0) {
    ESP_LOGW(TAG, "Trigger: timeout waiting for ok");
    trigger_busy_ = false;
    return;
  }
  wait_ok_remaining_--;
  set_timeout("wait_ok", 200, [this]() { wait_for_ok_(); });
}

}  // namespace digit_number
}  // namespace esphome
