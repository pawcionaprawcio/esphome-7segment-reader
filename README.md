# digit_number

ESPHome external component that reads a multi-digit 7-segment display via ESP32-CAM and publishes the value as a millimeter integer sensor. The number of digits is defined by the length of the `digits:` list in config — no fixed limit.

Designed for close-up camera mounting where the display fills most of the frame. Works with heavily blurred images — uses area brightness averaging and per-frame auto-thresholding.

## How it works

1. Camera captures a frame (grayscale or RGB565)
2. For each digit, 7 segment brightness values are sampled from defined anchor positions
3. Auto-threshold = `(black_ref + max) / 2` per digit (background reference from interior pixels)
4. Each segment is classified ON/OFF → 7-bit bitmask
5. Bitmask is looked up in the standard 7-segment truth table → digit 0–9
6. Value = `Σ d[i] × 10^(N–1–i)` → published as sensor in mm

**Display off** (all samples below `display_off_threshold`): publishes `NaN`.  
**Unknown bitmask** (unrecognised segment pattern): publishes `NaN`.

## Requirements

- ESP32-CAM
- ESPHome 2024.x+
- Camera configured with `pixel_format: GRAYSCALE` (RGB565 also supported)

## Installation

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/pawcionaprawcio/esphome_digit_number
      ref: main
    components: [digit_number]
    refresh: always
```

A minimal working config for ESP32-CAM is available in [`test.yaml`](test.yaml).

## Segment layout

Each 7-segment digit has this standard layout:

```
 _
|_|
|_|

 aaa
f   b
f   b
 ggg
e   c
e   c
 ddd
```

| Segment | Position            |
|---------|---------------------|
| `a`     | Top horizontal      |
| `b`     | Top-right vertical  |
| `c`     | Bottom-right vertical |
| `d`     | Bottom horizontal   |
| `e`     | Bottom-left vertical |
| `f`     | Top-left vertical   |
| `g`     | Middle horizontal   |

You only need to provide 3 anchor coordinates per digit. The component derives all 7 segment positions from them.

## Defining digit anchor coordinates

For each digit, provide **3 pixel coordinates** from a camera snapshot:

| Anchor | What to measure |
|--------|----------------|
| `a`    | Center pixel of the **top horizontal** segment `[x, y]` |
| `d`    | Center pixel of the **bottom horizontal** segment `[x, y]` |
| `b`    | Center pixel of the **top-right vertical** segment `[x, y]` |

```
snapshot pixel coords:

        a=[cx, y_top]
     ┌──────────────┐
     │  top horiz   │ ← measure center of this bar
     └──────────────┘
  f  │              │ b ← measure x of this bar's center
     │              │     (use b=x, any y in the top-right bar)
     ┌──────────────┐
     │  mid horiz   │ ← g (derived = (a+d)/2)
     └──────────────┘
  e  │              │ c  (derived)
     │              │
     ┌──────────────┐
     │  bot horiz   │ ← d=[cx, y_bot]
     └──────────────┘
```

`d.x` and `a.x` should both be at the **horizontal center** of the digit.  
`b` is a full `[x, y]` coordinate — place it at the center of the top-right vertical bar.

### Calibration GUI (`calibration.html`)

The repository includes a browser-based calibration tool — open `calibration.html` directly in any browser (no server needed).

**Workflow:**

1. Save several snapshots from `http://<device-ip>:8080` into one folder.
2. Click **Choose Folder** and select that folder.
3. Click anchor buttons (`a1`, `d1`, `b1`, …) and place them on the image by clicking the corresponding segment centers. Use `+` to add more digits.
4. Navigate through all saved images with **← Prev / Next →** (or arrow keys) — verify that the derived segment markers (blue crosshairs) land correctly on segments across different frames.
5. Adjust anchors until all frames look correct.
6. Click **YAML** → **Copy** and paste the result directly into `config.yaml`.

You can also paste an existing `digits:` block from `config.yaml` into the **Import** textarea in the YAML dialog to load previously saved coordinates back into the GUI.

### Manual calibration steps

1. Enable camera web server in ESPHome:
   ```yaml
   esp32_camera_web_server:
     - port: 8080
       mode: snapshot
   ```

2. Open `http://<device-ip>:8080` and save a snapshot.

3. Open the snapshot in any image editor (GIMP, Photoshop, even Paint).

4. For **each digit** (left to right):
   - Hover over the center of the top horizontal bar → note `[x, y]` → this is `a`
   - Hover over the center of the bottom horizontal bar → note `[x, y]` → this is `d`
   - Hover over any point on the top-right vertical bar → note `x` only → this is `b`

5. Fill the coordinates into the YAML config (see example below).

6. Flash and watch the debug log:
   ```
   [D][digit_number]: Digit 0: bitmask=0b0111111 thresh=128 -> 0
   [D][digit_number]: Publishing value: 223 mm
   ```
   Adjust coordinates if segments decode incorrectly.

## Configuration

```yaml
esp32_camera:
  id: my_camera
  # ... pin config for your board ...
  pixel_format: GRAYSCALE
  resolution: SVGA          # 800x600 recommended

sensor:
  - platform: digit_number
    name: "Distance"
    camera_id: my_camera
    unit_of_measurement: "mm"   # optional, default: mm — change to cm, kg, °C, etc.
    accuracy_decimals: 0        # optional, default: 0 (integer)
    update_interval: 2s
    sample_radius: 3            # pixels averaged around each sample point
    threshold: auto             # or fixed int 0-255
    display_off_threshold: 10   # max brightness below this = display off
    digits:
      - a: [195, 175]           # top horizontal center [x, y]
        d: [195, 265]           # bottom horizontal center [x, y]
        b: [250, 200]           # top-right vertical center [x, y]
      - a: [285, 175]
        d: [285, 265]
        b: [340, 200]
      - a: [375, 175]
        d: [375, 265]
        b: [430, 200]
      - a: [460, 175]
        d: [460, 265]
        b: [515, 200]
```

### Configuration reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `camera_id` | id | required | Reference to `esp32_camera` component |
| `digits` | list | required | 1 or more digit definitions (count determines sensor range) |
| `digits[].a` | [x, y] | required | Top horizontal segment center pixel |
| `digits[].d` | [x, y] | required | Bottom horizontal segment center pixel |
| `digits[].b` | [x, y] | required | Top-right vertical segment center pixel |
| `sample_radius` | int | 2 | Radius of averaging patch in pixels |
| `threshold` | `auto` or 0–255 | `auto` | Segment ON/OFF threshold. `auto` = `(black_ref + max) / 2` per digit (`black_ref` = background sample from digit interior) |
| `display_off_threshold` | int | 10 | Max brightness below this → display off → publishes `NaN` |
| `update_interval` | duration | `5s` | How often to sample a camera frame |
| `unit_of_measurement` | string | `mm` | Sensor unit published to Home Assistant (e.g. `mm`, `cm`, `kg`, `°C`) |
| `accuracy_decimals` | int | `0` | Decimal places in published value |
| `decimal_digits` | int | `0` | Shift decimal point by N places (e.g. `1` → `1234` becomes `123.4`) |
| `multiplier` | float | `1.0` | Scale factor applied after decimal shift: `value = raw / 10^decimal_digits * multiplier + offset` |
| `offset` | float | `0.0` | Offset added after multiplier |
| `max_value` | int | — | Readings above this value are treated as read errors (`fail`) |
| `last_state` | text_sensor | — | Optional text sensor: `off` / `ready` / `ok` / `fail` |
| `auto_trigger_on_ready` | bool | `true` | Auto-fire `trigger_pin` when display shows `----` (all-dash). Only has effect when `trigger_pin` is configured. |
| `trigger_pin` | pin | — | GPIO output to trigger external measurement device. Requires `burst_mode`. |
| `burst_mode.count` | int | 3 | Number of trigger pulses per burst |
| `burst_mode.trigger_interval` | duration | `10s` | Interval between trigger events within a burst |
| `burst_mode.rest_duration` | duration | `5min` | Pause between bursts |
| `burst_mode.trigger_pulse` | duration | `300ms` | Duration of each HIGH pulse sent to `trigger_pin` |
| `burst_mode.trigger_cold_wait` | duration | `2s` | Pause between the two pulses on cold start (display `off`) |
| `burst_mode.trigger_timeout_warm` | duration | `6s` | Max wait for valid reading after warm-start trigger |
| `burst_mode.trigger_timeout_cold` | duration | `15s` | Max wait for valid reading after cold-start trigger |
| `burst_mode.delta_threshold` | float | `5.0` | Value change considered significant (in sensor units); triggers shortened rest |
| `burst_mode.delta_rest_duration` | duration | `60s` | Shortened rest duration when delta ≥ `delta_threshold` |

### Pixel format

| Format | Notes |
|--------|-------|
| `GRAYSCALE` | Recommended. Direct 8-bit per pixel access, minimal processing |
| `RGB565` | Supported. Converted to grayscale via luma coefficients |
| `JPEG` | **Not supported.** Too expensive to decode on ESP32 |

## Sensor output

- **Unit**: configurable via `unit_of_measurement` (default: `mm`)
- **Accuracy**: configurable via `accuracy_decimals` (default: `0` — integer)
- **Range**: 0–9999 (4 digits) or limited by `max_value`
- **NaN** published when: display off, unknown segment pattern, camera unavailable

### `last_state` values

| State | Meaning |
|-------|---------|
| `off` | All segment brightness below `display_off_threshold` |
| `ready` | All digits show `–` (device warming up / measuring) |
| `ok` | Valid reading published |
| `fail` | Unrecognised segment pattern or value exceeded `max_value` |

## Best conditions

Works best when the display and camera background are evenly lit with no external reflections — uniform brightness and contrast across the frame. This stabilises auto-thresholding and minimises segment decode errors.

## Troubleshooting

**All digits decode as `?`**  
→ Coordinates are off. Run `python tests/validate.py --debug` with your image to see per-segment brightness values.

**Some digits correct, others `?`**  
→ Adjust `a`, `d`, or `b` for the failing digit. The `b` x-coordinate is often the most sensitive — try moving it 5–10 px inward from the right edge.

**Values flicker**  
→ Increase `sample_radius` (try 3–5). Or set a fixed `threshold` value once you know a stable level.

**`LOGW: Display off`** when display is on  
→ Lower `display_off_threshold` (try 5).

## Development

```bash
pip install -r requirements-test.txt
pytest tests/test_geometry.py tests/test_decode.py -v
python tests/validate.py --debug
```

## License

MIT — see [LICENSE](LICENSE).
