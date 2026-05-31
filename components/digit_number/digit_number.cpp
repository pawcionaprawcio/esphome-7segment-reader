#include "digit_number.h"
#include "esphome/core/log.h"
#include "esp_camera.h"

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
        sum += (uint32_t)(rv * 30 + gv * 59 + bv * 11) / 100;
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
  return -1;
}

void DigitNumber::setup() {
  last_valid_ms_ = millis();
  static_cast<camera::Camera *>(camera_)->add_listener(this);
}

void DigitNumber::on_camera_image(const std::shared_ptr<camera::CameraImage> & /*image*/) {
  const uint32_t now = millis();
  if (now - last_publish_ms_ >= update_interval_ms_) {
    last_publish_ms_ = now;
    process_image_();
  }
}

void DigitNumber::process_image_() {
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
  const int num_digits = (int)digits_.size();

  std::vector<std::array<uint8_t, 7>> brightness(num_digits);
  uint8_t global_max = 0;

  for (int d = 0; d < num_digits; d++) {
    const DigitGeometry geo = derive_geometry_(digits_[d]);
    for (int s = 0; s < 7; s++) {
      brightness[d][s] = sample_brightness_(buf, fw, fh, fmt, geo.seg[s].x, geo.seg[s].y);
      if (brightness[d][s] > global_max)
        global_max = brightness[d][s];
    }
  }

  esp_camera_fb_return(fb);

  if (global_max < display_off_threshold_) {
    ESP_LOGW(TAG, "Display off (max brightness %d < %d)", global_max, display_off_threshold_);
    publish_state(last_valid_);
    if (staleness_sensor_)
      staleness_sensor_->publish_state((float)((millis() - last_valid_ms_) / 1000));
    if (last_state_sensor_)
      last_state_sensor_->publish_state("off");
    return;
  }

  uint8_t thresh;
  if (threshold_ < 0) {
    uint8_t global_min = 255;
    for (int d = 0; d < num_digits; d++)
      for (int s = 0; s < 7; s++)
        if (brightness[d][s] < global_min)
          global_min = brightness[d][s];
    thresh = (uint8_t)((global_min + global_max) / 2);
  } else {
    thresh = (uint8_t)threshold_;
  }

  std::vector<uint8_t> bitmasks(num_digits);
  for (int d = 0; d < num_digits; d++) {
    uint8_t bm = 0;
    for (int s = 0; s < 7; s++) {
      if (brightness[d][s] >= thresh)
        bm |= (1 << s);
    }
    bitmasks[d] = bm;
  }

  // Check "off": all bitmasks zero means thresh > all segment brightnesses (uniform noise)
  bool all_zero = true;
  for (int d = 0; d < num_digits; d++) {
    if (bitmasks[d] != 0) { all_zero = false; break; }
  }
  if (all_zero) {
    ESP_LOGW(TAG, "All bitmasks zero (noise/dark, thresh=%d) → off", thresh);
    publish_state(last_valid_);
    if (staleness_sensor_)
      staleness_sensor_->publish_state((float)((millis() - last_valid_ms_) / 1000));
    if (last_state_sensor_)
      last_state_sensor_->publish_state("off");
    return;
  }

  // Check "ready": all digits show dash (segment g only)
  bool all_dash = true;
  for (int d = 0; d < num_digits; d++) {
    if (bitmasks[d] != DASH_BITMASK_) { all_dash = false; break; }
  }
  if (all_dash) {
    ESP_LOGD(TAG, "Display ready (all dashes, thresh=%d)", thresh);
    last_publish_ms_ = now - update_interval_ms_ + ready_retry_delay_ms_;
    publish_state(last_valid_);
    if (staleness_sensor_)
      staleness_sensor_->publish_state((float)((millis() - last_valid_ms_) / 1000));
    if (last_state_sensor_)
      last_state_sensor_->publish_state("ready");
    return;
  }

  // Decode digits
  int32_t value = 0;
  const int32_t multipliers[4] = {1000, 100, 10, 1};

  for (int d = 0; d < num_digits; d++) {
    const int8_t digit = decode_digit_(bitmasks[d]);
    ESP_LOGD(TAG, "Digit %d: bitmask=0b%07b thresh=%d -> %d", d, bitmasks[d], thresh, digit);
    if (digit < 0) {
      ESP_LOGW(TAG, "Unknown bitmask 0b%07b for digit %d", bitmasks[d], d);
      publish_state(last_valid_);
      if (staleness_sensor_)
        staleness_sensor_->publish_state((float)((millis() - last_valid_ms_) / 1000));
      if (last_state_sensor_)
        last_state_sensor_->publish_state("fail");
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

}  // namespace digit_number
}  // namespace esphome
