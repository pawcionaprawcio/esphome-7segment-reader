# digit_number ESPHome External Component — Design Spec

**Date:** 2026-05-21

## Context

ESP32-CAM mounted close to a 7-segment display (energy/distance meter). Display shows 4 digits, white glowing segments on dark background. Goal: read the 4-digit integer value and publish to Home Assistant as a sensor in mm. Camera proximity causes blur/bloom; config must tolerate that. No decimal point detection needed — display always shows 4 digits representing millimeters.

---

## Architecture

### Files

```
components/digit_number/
  __init__.py        # YAML schema + C++ codegen
  digit_number.h     # DigitNumber class (extends sensor::Sensor)
  digit_number.cpp   # geometry derivation, pixel sampling, decode
```

### Processing pipeline (per update interval)

1. Request camera frame (raw buffer, grayscale or RGB565)
2. For each of 4 digits: derive 7 segment sample centers from 3 anchor points
3. For each sample center: average brightness over `(2*radius+1)²` pixel patch
4. Check display-off condition: if max brightness of all 28 samples < `display_off_threshold` → publish `NaN` + `LOGW("Display off or no signal")`
5. Compute threshold: `auto` = `(min_brightness + max_brightness) / 2` across all 28 samples; or use fixed value
6. Classify each segment ON/OFF → 7-bit bitmask per digit
7. Look up bitmask in truth table → digit 0–9, or -1 (unknown)
8. If any digit unknown → publish `NaN`
9. Combine: `value = d[0]*1000 + d[1]*100 + d[2]*10 + d[3]`
10. Publish via ESPHome sensor infrastructure

### Geometry derivation (3 anchors → 7 sample centers)

User provides per digit:
- `a` = center of top horizontal segment `[x, y]`
- `g` = center of middle horizontal segment `[x, y]`
- `b` = center of top-right vertical segment `[x, y]` — only `x` used for width

Derivation:
```
x_left  = 2*a.x - b.x
x_right = b.x
y_top   = a.y
y_mid   = g.y
y_bot   = 2*g.y - a.y
y_th    = (a.y + g.y) / 2       # top-half vertical midpoint
y_bh    = (g.y + y_bot) / 2     # bottom-half vertical midpoint

Sample centers:
  a → (a.x,    y_top)
  b → (x_right, y_th)
  c → (x_right, y_bh)
  d → (a.x,    y_bot)
  e → (x_left,  y_bh)
  f → (x_left,  y_th)
  g → (g.x,    y_mid)
```

### 7-segment truth table

| Digit | a | b | c | d | e | f | g |
|-------|---|---|---|---|---|---|---|
| 0     | 1 | 1 | 1 | 1 | 1 | 1 | 0 |
| 1     | 0 | 1 | 1 | 0 | 0 | 0 | 0 |
| 2     | 1 | 1 | 0 | 1 | 1 | 0 | 1 |
| 3     | 1 | 1 | 1 | 1 | 0 | 0 | 1 |
| 4     | 0 | 1 | 1 | 0 | 0 | 1 | 1 |
| 5     | 1 | 0 | 1 | 1 | 0 | 1 | 1 |
| 6     | 1 | 0 | 1 | 1 | 1 | 1 | 1 |
| 7     | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| 8     | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| 9     | 1 | 1 | 1 | 1 | 0 | 1 | 1 |

---

## YAML Config

```yaml
external_components:
  - source: github://youruser/esphome-digit-number@main
    components: [digit_number]

esp32_camera:
  id: my_camera
  pixel_format: GRAYSCALE   # required; RGB565 also supported
  resolution: SVGA

sensor:
  - platform: digit_number
    name: "Distance"
    camera_id: my_camera
    unit_of_measurement: mm
    update_interval: 2s
    sample_radius: 2              # patch half-size; default 2 → 25px patch
    threshold: auto               # or fixed int 0-255
    display_off_threshold: 10     # max brightness below this = display off
    digits:
      - a: [120, 45]
        g: [120, 80]
        b: [155, 62]
      - a: [200, 45]
        g: [200, 80]
        b: [235, 62]
      - a: [280, 45]
        g: [280, 80]
        b: [315, 62]
      - a: [360, 45]
        g: [360, 80]
        b: [395, 62]
```

### Config fields

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `camera_id` | id | required | Reference to `esp32_camera` component |
| `digits` | list[4] | required | Exactly 4 digit definitions; `__init__.py` rejects non-4 list at compile time |
| `digits[].a` | [x,y] | required | Top horizontal segment center |
| `digits[].g` | [x,y] | required | Middle horizontal segment center |
| `digits[].b` | [x,y] | required | Top-right vertical center (x used for width derivation) |
| `sample_radius` | int | 2 | Patch half-size in pixels |
| `threshold` | auto\|int | auto | `auto` = (min+max)/2 per frame |
| `display_off_threshold` | int | 10 | Max brightness below this → display-off state |
| `update_interval` | duration | 5s | How often to request and process a frame |

---

## Error Handling

| Condition | Behavior |
|-----------|----------|
| Display off (all samples < `display_off_threshold`) | Publish `NaN` + `LOGW` |
| Unknown bitmask on any digit | Publish `NaN` |
| Camera frame unavailable | Skip update, retry next interval |
| Borderline brightness (DEBUG) | Log per-digit brightness + bitmask at `LOGD` level |

---

## Calibration Workflow

1. Enable camera web server in ESPHome to capture a live snapshot
2. Open snapshot in any image editor; note pixel coords of segment centers
3. Fill in `a`, `g`, `b` per digit in YAML
4. Flash device; watch `DEBUG` log — component logs per-frame brightness and decoded digits
5. Adjust coords or `sample_radius` until all digits decode correctly

---

## Verification

1. **Python unit test** — load test JPEGs from `test_cases/`, run geometry + sampling logic in Python, assert decoded values match known readings (0223, 2798, 1822, 0530, 1979, etc.)
2. **On-device debug log** — `LOGD` output shows brightness per segment + bitmask + decoded digit each frame; tune until stable
3. **ESPHome integration** — `esphome run`, observe sensor value in HA or serial monitor across all test-case display states
