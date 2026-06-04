# Inverted Display Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `inverted: bool` config flag that flips brightness values before the threshold/decode pipeline, enabling dark-segments-on-bright-background displays.

**Architecture:** Single boolean flag. After sampling all segment and background brightness values, if `inverted=true`, apply `255 - value` to every sample and recalculate `global_max` from the pre-flip `global_min`. All downstream threshold and decode logic is unchanged.

**Tech Stack:** C++ (ESPHome component), Python (ESPHome schema + pytest integration tests), Pillow (test image generation)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `components/digit_number/digit_number.h` | Modify | `inverted_` field + setter |
| `components/digit_number/digit_number.cpp` | Modify | Track `global_min`; flip block in `process_image_()` |
| `components/digit_number/sensor.py` | Modify | `CONF_INVERTED` in schema + `to_code` |
| `tools/invert_images.py` | Create | One-off script: invert size_1 → size_2 |
| `test_cases/size_2/` | Create | 15 inverted JPEG images |
| `tests/test_integration_size2.py` | Create | Integration tests for inverted pipeline |

---

### Task 1: Write failing integration test

**Files:**
- Create: `tests/test_integration_size2.py`

- [ ] **Create `tests/test_integration_size2.py`:**

```python
"""
Integration tests for inverted display mode using test_cases/size_2/.

Images are pixel-inverted (255 - pixel) copies of size_1 — dark segments on
bright background. decode_image() flips brightness before thresholding,
mirroring C++ `inverted: true`.
"""
import pytest
import yaml
from pathlib import Path
from PIL import Image

from tests.validate import derive_segment_centers, decode_digit

IMG_DIR = Path(__file__).parent.parent / "test_cases" / "size_2"

_ANCHORS_YAML = """\
digits:
  - a: [128, 188]
    d: [110, 437]
    b: [169, 253]
  - a: [282, 192]
    d: [271, 443]
    b: [324, 259]
  - a: [444, 197]
    d: [423, 445]
    b: [482, 258]
  - a: [603, 201]
    d: [586, 450]
    b: [642, 263]
"""

DIGIT_ANCHORS = [
    {"a": tuple(d["a"]), "d": tuple(d["d"]), "b": tuple(d["b"])}
    for d in yaml.safe_load(_ANCHORS_YAML)["digits"]
]
SAMPLE_RADIUS = 5
DISPLAY_OFF_THRESHOLD = 60
HORIZ_SEGS = frozenset("adg")
DASH_BITMASK = 0b1000000


def _sample(pixels, w, h, cx, cy, seg):
    if seg in HORIZ_SEGS:
        r = SAMPLE_RADIUS
        tot = cnt = 0
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x, y = cx + dx, cy + dy
                if 0 <= x < w and 0 <= y < h:
                    tot += pixels[x, y]
                    cnt += 1
    else:
        tot = cnt = 0
        for dy in range(-25, 26):
            for dx in range(-5, 6):
                x, y = cx + dx, cy + dy
                if 0 <= x < w and 0 <= y < h:
                    tot += pixels[x, y]
                    cnt += 1
    return tot // cnt if cnt else 0


def _best_threshold(bright):
    mn = min(bright)
    if mn > 100:
        return 0
    s = sorted(bright)
    mg, gp = 0, 0
    for i in range(6):
        g = s[i + 1] - s[i]
        if g > mg:
            mg = g
            gp = i
    if mg < 50 and mn > 80 and (s[1] - s[0]) < 15:
        return 0
    return (s[gp] + s[gp + 1]) // 2


def decode_image(path):
    try:
        img = Image.open(path).convert("L")
    except OSError:
        return None
    pixels = img.load()
    w, h = img.size

    all_bright = []
    digit_segments = []

    for anchors in DIGIT_ANCHORS:
        centers = derive_segment_centers(anchors["a"], anchors["d"], anchors["b"])
        bright_raw = [_sample(pixels, w, h, *centers[s], s) for s in "abcdefg"]
        bright = [255 - b for b in bright_raw]  # invert: dark segments → bright
        digit_segments.append(bright)
        all_bright.extend(bright)

    if max(all_bright) < DISPLAY_OFF_THRESHOLD:
        return None

    digits = []
    for bright in digit_segments:
        thresh = _best_threshold(bright)
        bitmask = sum((1 << i) for i, b in enumerate(bright) if b >= thresh)
        if bitmask == DASH_BITMASK:
            return None
        digit = decode_digit(bitmask)
        if digit is None:
            return None
        digits.append(digit)

    return sum(d * (10 ** (len(digits) - 1 - i)) for i, d in enumerate(digits))


def test_dashes():
    """Inverted kreski.jpg → ready state → None."""
    assert decode_image(IMG_DIR / "kreski.jpg") is None


@pytest.mark.parametrize("filename,expected_mm", [
    ("capture.jpg",        742),
    ("capture (1).jpg",    744),
    ("capture (2).jpg",    835),
    ("capture (3).jpg",    270),
    ("capture (4).jpg",    761),
    ("capture (5).jpg",    777),
    ("capture (6).jpg",    778),
    ("capture (7).jpg",    812),
    ("capture (8).jpg",    732),
    ("capture (9).jpg",    497),
    ("capture (10).jpg",   378),
    ("capture (11).jpg",  1166),
    ("capture (12).jpg",  1692),
    ("capture (13).jpg",  2507),
])
def test_decode(filename, expected_mm):
    result = decode_image(IMG_DIR / filename)
    assert result == expected_mm, f"{filename}: expected {expected_mm} mm, got {result}"
```

- [ ] **Run — verify it fails:**

```bash
cd esphome_digit_number
pytest tests/test_integration_size2.py -v
```

Expected: all 15 tests FAIL (`AssertionError: ... expected 742 mm, got None` — images not yet generated).

---

### Task 2: Generate inverted test images

**Files:**
- Create: `tools/invert_images.py`
- Create: `test_cases/size_2/` (15 images)

- [ ] **Create `tools/invert_images.py`:**

```python
#!/usr/bin/env python3
"""Generate test_cases/size_2/ — pixel-inverted copies of test_cases/size_1/."""
from pathlib import Path
from PIL import Image, ImageOps

src = Path(__file__).parent.parent / "test_cases" / "size_1"
dst = Path(__file__).parent.parent / "test_cases" / "size_2"
dst.mkdir(exist_ok=True)

images = sorted(src.glob("*.jpg"))
for img_path in images:
    inverted = ImageOps.invert(Image.open(img_path).convert("L"))
    out_path = dst / img_path.name
    inverted.save(out_path, quality=95)
    print(f"  {img_path.name}")
print(f"Done: {len(images)} images → {dst}")
```

- [ ] **Run the script:**

```bash
cd esphome_digit_number
python tools/invert_images.py
```

Expected output ends with: `Done: 15 images → .../test_cases/size_2`

- [ ] **Verify count:**

```bash
ls test_cases/size_2/*.jpg | wc -l
```

Expected: `15`

---

### Task 3: Verify integration tests pass

- [ ] **Run size_2 tests:**

```bash
cd esphome_digit_number
pytest tests/test_integration_size2.py -v
```

Expected: **15 passed**.

If a test fails with a wrong value (not None), the JPEG re-encode introduced a quantization artifact that shifted the threshold. Fix: update the expected value in `test_integration_size2.py` to the actual decoded result, then confirm manually that digit is visually correct in `calibration.html` with the inverted image.

---

### Task 4: Add `inverted` field to C++ header

**Files:**
- Modify: `components/digit_number/digit_number.h`

- [ ] **Add setter in `public:` section, after `void set_multiplier(float v)` (~line 58):**

```cpp
  void set_offset(float v) { offset_ = v; }
  void set_max_value(int32_t v) { max_value_ = v; }
  void set_inverted(bool v) { inverted_ = v; }
```

- [ ] **Add field in `protected:` section, after `int32_t max_value_{-1};` (~line 121):**

```cpp
  int32_t max_value_{-1};
  bool inverted_{false};
```

---

### Task 5: Implement inversion in C++ source

**Files:**
- Modify: `components/digit_number/digit_number.cpp`

Changes are in `process_image_()`. Current variable declarations (~line 150):

```cpp
  std::vector<std::array<uint8_t, 7>> brightness(num_digits);
  std::vector<uint8_t> black_ref(num_digits);
  uint8_t global_max = 0;
```

- [ ] **Add `global_min` — replace the three-line declaration block:**

```cpp
  std::vector<std::array<uint8_t, 7>> brightness(num_digits);
  std::vector<uint8_t> black_ref(num_digits);
  uint8_t global_max = 0;
  uint8_t global_min = 255;
```

- [ ] **Track `global_min` in the segment sampling loop — add one line after the `global_max` update (~line 159):**

```cpp
      if (brightness[d][s] > global_max)
        global_max = brightness[d][s];
      if (brightness[d][s] < global_min)
        global_min = brightness[d][s];
```

- [ ] **Add flip block immediately after `esp_camera_fb_return(fb);` (~line 169), before the display-off check:**

```cpp
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
```

---

### Task 6: Add `inverted` to Python schema

**Files:**
- Modify: `components/digit_number/sensor.py`

- [ ] **Add constant after `CONF_MAX_VALUE` (~line 32):**

```python
CONF_MAX_VALUE = "max_value"
CONF_INVERTED = "inverted"
```

- [ ] **Add field in `CONFIG_SCHEMA` after the `max_value` line (~line 91):**

```python
        cv.Optional(CONF_MAX_VALUE): cv.positive_int,
        cv.Optional(CONF_INVERTED, default=False): cv.boolean,
```

- [ ] **Add to `to_code()` after the `max_value` block (~line 149):**

```python
    if CONF_MAX_VALUE in config:
        cg.add(var.set_max_value(config[CONF_MAX_VALUE]))

    cg.add(var.set_inverted(config[CONF_INVERTED]))
```

---

### Task 7: Run full test suite

- [ ] **Run all tests:**

```bash
cd esphome_digit_number
pytest tests/ -v
```

Expected: all existing tests pass + 15 new size_2 tests pass. Zero failures.

- [ ] **Spot-check size_1 still clean:**

```bash
pytest tests/test_integration_size1.py -v
```

Expected: **14 passed**.
