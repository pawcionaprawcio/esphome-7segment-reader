# last_state Sensor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `last_state` text sensor to `digit_number` ESPHome component that publishes `"off"` / `"ready"` / `"ok"` / `"fail"` based on camera display state, visible in web_server.

**Architecture:** Mirror the C++ state-machine logic in Python (validate.py) for testability, then implement identically in C++. State is determined after sampling all segment brightnesses: dark display → `"off"`, all-dash bitmasks → `"ready"`, all valid digits → `"ok"`, anything else → `"fail"`. Dash bitmask = `0b1000000` (segment g only, experimentally verified against production images).

**Tech Stack:** ESPHome C++ component, ESPHome Python schema (codegen), pytest + Pillow for integration tests.

---

## File Map

| File | Change |
|------|--------|
| `tests/validate.py` | Add `DASH_BITMASK` constant + `determine_state()` function |
| `tests/test_state.py` | New — unit + integration tests for state logic |
| `components/digit_number/digit_number.h` | Add text_sensor include, member, setter; add `DASH_BITMASK_` constant |
| `components/digit_number/digit_number.cpp` | Refactor `process_image_`: collect all bitmasks first, check dash, decode, publish state |
| `components/digit_number/sensor.py` | Import `text_sensor`, add `CONF_LAST_STATE` option, wire in `to_code` |
| `config.yaml` (project root `../..`) | Add `last_state: name: "Display State"` under the `digit_number` sensor |

---

## Task 1: Add `determine_state` to validate.py

**Files:**
- Modify: `tests/validate.py`

- [ ] **Step 1: Add `DASH_BITMASK` and `determine_state` to validate.py**

Append after the `decode_digit` function (after line 60):

```python
DASH_BITMASK = 0b1000000  # segment g only — kreska (dash); verified against size_3/kreski.jpg


def determine_state(all_bright, digit_segments, display_off_threshold=20):
    """Mirror C++ last_state logic. Returns (state, value_or_None).

    States:
      'off'   — global_max < display_off_threshold
      'ready' — all 4 digits have DASH_BITMASK (segment g only)
      'ok'    — all 4 digits decode to 0-9; value is the mm integer
      'fail'  — any other case (unknown bitmask, not dash)
    """
    gmax = max(all_bright)
    if gmax < display_off_threshold:
        return "off", None
    gmin = min(all_bright)
    thresh = (gmin + gmax) // 2
    bitmasks = [
        sum((1 << i) for i, b in enumerate(bright) if b >= thresh)
        for bright in digit_segments
    ]
    if all(b == DASH_BITMASK for b in bitmasks):
        return "ready", None
    digits = [decode_digit(b) for b in bitmasks]
    if all(d is not None for d in digits):
        value = digits[0] * 1000 + digits[1] * 100 + digits[2] * 10 + digits[3]
        return "ok", value
    return "fail", None
```

- [ ] **Step 2: Also add `DASH_BITMASK` to exports used by tests**

Add `DASH_BITMASK` to the import in `tests/test_decode.py` is not needed — just confirm `validate.py` exports it at module level (it will, since it's a module-level constant).

---

## Task 2: Write failing tests for state logic

**Files:**
- Create: `tests/test_state.py`

- [ ] **Step 1: Create `tests/test_state.py`**

```python
"""Tests for determine_state() logic — unit tests + image integration tests."""

import pytest
from pathlib import Path
from PIL import Image

from tests.validate import (
    DASH_BITMASK,
    DISPLAY_OFF_THRESHOLD,
    decode_digit,
    derive_segment_centers,
    determine_state,
    sample_brightness,
)

# ── Unit tests ────────────────────────────────────────────────────────────────

def test_dash_bitmask_is_not_a_digit():
    """DASH_BITMASK must not decode to any digit 0-9."""
    assert decode_digit(DASH_BITMASK) is None


def test_state_off_when_dark():
    all_bright = [5] * 28
    digit_segments = [[5] * 7 for _ in range(4)]
    state, value = determine_state(all_bright, digit_segments)
    assert state == "off"
    assert value is None


def test_state_ready_when_all_dashes():
    # thresh = (5 + 200) // 2 = 102
    # each digit: only segment g (index 6) at 200, rest at 5 → bitmask = DASH_BITMASK
    digit_segments = [[5, 5, 5, 5, 5, 5, 200] for _ in range(4)]
    all_bright = [b for seg in digit_segments for b in seg]
    state, value = determine_state(all_bright, digit_segments)
    assert state == "ready"
    assert value is None


def test_state_ok_when_valid_digits():
    # Digits: 0, 1, 2, 7 → value = 127
    # thresh = (5 + 200) // 2 = 102
    # digit 0: segments a,b,c,d,e,f bright → bitmask 0b0111111 = 63
    d0 = [200, 200, 200, 200, 200, 200, 5]
    # digit 1: segments b,c bright → bitmask 0b0000110 = 6
    d1 = [5, 200, 200, 5, 5, 5, 5]
    # digit 2: segments a,b,d,e,g bright → bitmask 0b1011011 = 91
    d2 = [200, 200, 5, 200, 200, 5, 200]
    # digit 7: segments a,b,c bright → bitmask 0b0000111 = 7
    d7 = [200, 200, 200, 5, 5, 5, 5]
    digit_segments = [d0, d1, d2, d7]
    all_bright = [b for seg in digit_segments for b in seg]
    state, value = determine_state(all_bright, digit_segments)
    assert state == "ok"
    assert value == 127


def test_state_fail_when_one_digit_unknown():
    # Digit 2 has only segment a (bitmask 0b0000001 = 1) — unknown, not a dash
    d_dash = [5, 5, 5, 5, 5, 5, 200]   # DASH_BITMASK
    d_fail = [200, 5, 5, 5, 5, 5, 5]   # only segment a — not a digit, not a dash
    digit_segments = [d_dash, d_dash, d_fail, d_dash]
    all_bright = [b for seg in digit_segments for b in seg]
    state, value = determine_state(all_bright, digit_segments)
    assert state == "fail"
    assert value is None


def test_state_fail_not_confused_with_ready_when_mixed():
    # 3 dashes + 1 unknown bitmask → fail, not ready
    d_dash = [5, 5, 5, 5, 5, 5, 200]
    d_fail = [200, 200, 5, 5, 5, 5, 5]  # a,b only — not a digit
    digit_segments = [d_dash, d_dash, d_dash, d_fail]
    all_bright = [b for seg in digit_segments for b in seg]
    state, value = determine_state(all_bright, digit_segments)
    assert state == "fail"


# ── Integration tests using real size_3 images ────────────────────────────────

IMG_DIR = Path(__file__).parent.parent / "test_cases" / "size_3"

PROD_ANCHORS = [
    {"a": (135, 230), "g": (135, 357), "bx": 172},
    {"a": (292, 230), "g": (292, 357), "bx": 332},
    {"a": (449, 230), "g": (449, 357), "bx": 484},
    {"a": (603, 230), "g": (603, 357), "bx": 636},
]
PROD_SAMPLE_RADIUS = 5
PROD_OFF_THRESHOLD = 20


def _load_state(filename):
    img = Image.open(IMG_DIR / filename).convert("L")
    pixels = img.load()
    w, h = img.size
    all_bright, digit_segs = [], []
    for a in PROD_ANCHORS:
        centers = derive_segment_centers(a["a"], a["g"], a["bx"])
        bright = [sample_brightness(pixels, w, h, *centers[s], radius=PROD_SAMPLE_RADIUS)
                  for s in "abcdefg"]
        digit_segs.append(bright)
        all_bright.extend(bright)
    return determine_state(all_bright, digit_segs, PROD_OFF_THRESHOLD)


def test_real_image_off():
    state, value = _load_state("off.jpg")
    assert state == "off"
    assert value is None


def test_real_image_ready():
    state, value = _load_state("kreski.jpg")
    assert state == "ready"
    assert value is None


def test_real_image_ok():
    state, value = _load_state("capture.jpg")
    assert state == "ok"
    assert value == 3074
```

- [ ] **Step 2: Run tests — expect FAIL (determine_state not yet in validate.py)**

```bash
cd esphome_digit_number
source venv/bin/activate
pytest tests/test_state.py -v
```

Expected: `ImportError: cannot import name 'determine_state'`

- [ ] **Step 3: Implement Task 1 (add `determine_state` to validate.py), then re-run**

```bash
pytest tests/test_state.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Run full test suite to check no regressions**

```bash
pytest tests/ -v
```

Expected: all previously-passing tests still pass.

- [ ] **Step 5: Commit**

```bash
cd esphome_digit_number
git add tests/validate.py tests/test_state.py
git commit -m "feat: add determine_state() with tests for last_state sensor"
```

---

## Task 3: Update C++ header (`digit_number.h`)

**Files:**
- Modify: `components/digit_number/digit_number.h`

- [ ] **Step 1: Add text_sensor include and member**

Replace the current header content with the following (changes: new include, new setter, new member `last_state_sensor_`, new constant `DASH_BITMASK_`):

```cpp
#pragma once

#include <array>
#include <memory>
#include <vector>
#include "esphome/core/component.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/components/camera/camera.h"
#include "esphome/components/esp32_camera/esp32_camera.h"

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
  void set_frame_width(uint16_t w) { (void)w; }
  void set_frame_height(uint16_t h) { (void)h; }
  void add_digit(DigitAnchors anchors) { digits_.push_back(anchors); }
  void set_sample_radius(uint8_t r) { sample_radius_ = r; }
  void set_threshold(int t) { threshold_ = t; }
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
  void process_image_();

  esp32_camera::ESP32Camera *camera_{nullptr};
  sensor::Sensor *staleness_sensor_{nullptr};
  text_sensor::TextSensor *last_state_sensor_{nullptr};
  std::vector<DigitAnchors> digits_;
  uint8_t sample_radius_{2};
  int threshold_{-1};
  uint8_t display_off_threshold_{10};
  uint32_t update_interval_ms_{5000};
  uint32_t last_publish_ms_{0};
  float last_valid_{NAN};
  uint32_t last_valid_ms_{0};

  static const uint8_t SEGMENT_PATTERNS_[10];
  static const uint8_t DASH_BITMASK_ = 0b1000000;  // segment g only
};

}  // namespace digit_number
}  // namespace esphome
```

---

## Task 4: Refactor `process_image_` in `digit_number.cpp`

**Files:**
- Modify: `components/digit_number/digit_number.cpp`

- [ ] **Step 1: Replace `process_image_` with new state-aware version**

Replace the entire `process_image_` function (lines 95–181) with:

```cpp
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

  // Check "ready": all digits show dash (segment g only)
  bool all_dash = true;
  for (int d = 0; d < num_digits; d++) {
    if (bitmasks[d] != DASH_BITMASK_) { all_dash = false; break; }
  }
  if (all_dash) {
    ESP_LOGD(TAG, "Display ready (all dashes, thresh=%d)", thresh);
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
```

- [ ] **Step 2: Commit C++ changes**

```bash
cd esphome_digit_number
git add components/digit_number/digit_number.h components/digit_number/digit_number.cpp
git commit -m "feat: add last_state text sensor to digit_number C++ component"
```

---

## Task 5: Update Python schema (`sensor.py`)

**Files:**
- Modify: `components/digit_number/sensor.py`

- [ ] **Step 1: Add text_sensor import and CONF_LAST_STATE**

Replace the top of `sensor.py` (imports + constants section) with:

```python
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor, esp32_camera, text_sensor
from esphome.const import STATE_CLASS_MEASUREMENT
from . import digit_number_ns, DigitNumber

CONF_CAMERA_ID = "camera_id"
CONF_DIGITS = "digits"
CONF_SAMPLE_RADIUS = "sample_radius"
CONF_THRESHOLD = "threshold"
CONF_DISPLAY_OFF_THRESHOLD = "display_off_threshold"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_FRAME_WIDTH = "frame_width"
CONF_FRAME_HEIGHT = "frame_height"
CONF_LAST_SUCCESSFUL_READ = "last_successful_read"
CONF_LAST_STATE = "last_state"
```

- [ ] **Step 2: Add `last_state` to CONFIG_SCHEMA**

In `CONFIG_SCHEMA`, after the `CONF_LAST_SUCCESSFUL_READ` block, add:

```python
        cv.Optional(CONF_LAST_STATE): text_sensor.text_sensor_schema(
            icon="mdi:information-outline",
        ),
```

- [ ] **Step 3: Wire `last_state` in `to_code`**

At the end of `to_code`, after the `CONF_LAST_SUCCESSFUL_READ` block, add:

```python
    if CONF_LAST_STATE in config:
        ts = await text_sensor.new_text_sensor(config[CONF_LAST_STATE])
        cg.add(var.set_last_state_sensor(ts))
```

- [ ] **Step 4: Commit**

```bash
cd esphome_digit_number
git add components/digit_number/sensor.py
git commit -m "feat: add last_state text_sensor to Python schema"
```

---

## Task 6: Update `config.yaml`

**Files:**
- Modify: `../../config.yaml` (relative to `esphome_digit_number/` — actual path: project root `config.yaml`)

- [ ] **Step 1: Add `last_state` sub-sensor**

In `config.yaml`, inside the `sensor` → `digit_number` block, add after `display_off_threshold: 20`:

```yaml
    last_state:
      name: "Display State"
```

The `web_server` at port 80 (already in config.yaml) automatically exposes all entities including text_sensors — no additional config required.

- [ ] **Step 2: Commit**

```bash
# from the Esp32Cam project root (not inside esphome_digit_number)
git add config.yaml 2>/dev/null || true
# note: config.yaml is not in esphome_digit_number git repo
# just save the file; commit separately if project root has git
```

---

## Task 7: Final verification

- [ ] **Step 1: Run full test suite**

```bash
cd esphome_digit_number
source venv/bin/activate
pytest tests/ -v
```

Expected output — all tests pass, including:
- `tests/test_state.py::test_dash_bitmask_is_not_a_digit` PASSED
- `tests/test_state.py::test_state_off_when_dark` PASSED
- `tests/test_state.py::test_state_ready_when_all_dashes` PASSED
- `tests/test_state.py::test_state_ok_when_valid_digits` PASSED
- `tests/test_state.py::test_state_fail_when_one_digit_unknown` PASSED
- `tests/test_state.py::test_state_fail_not_confused_with_ready_when_mixed` PASSED
- `tests/test_state.py::test_real_image_off` PASSED
- `tests/test_state.py::test_real_image_ready` PASSED
- `tests/test_state.py::test_real_image_ok` PASSED

- [ ] **Step 2: Validate full pipeline output**

```bash
python tests/validate.py --debug
```

Verify no errors; confirm off.jpg still shows `None`.
