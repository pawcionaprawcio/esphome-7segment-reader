# digit_number

ESPHome external component that reads a 4-digit 7-segment display via ESP32-CAM and publishes the value as a millimeter integer sensor.

Designed for close-up camera mounting where the display fills most of the frame. Works with heavily blurred images — uses area brightness averaging and per-frame auto-thresholding.

## How it works

1. Camera captures a frame (grayscale or RGB565)
2. For each digit, 7 segment brightness values are sampled from defined anchor positions
3. Auto-threshold = `(min + max) / 2` across all 28 samples
4. Each segment is classified ON/OFF → 7-bit bitmask
5. Bitmask is looked up in the standard 7-segment truth table → digit 0–9
6. Value = `d[0]*1000 + d[1]*100 + d[2]*10 + d[3]` → published as sensor in mm

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
      url: https://github.com/youruser/esphome-digit-number
    components: [digit_number]
```

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
| `g`    | Center pixel of the **middle horizontal** segment `[x, y]` |
| `b`    | X coordinate of the **top-right vertical** segment (integer) |

```
snapshot pixel coords:

        a=[cx, y_top]
     ┌──────────────┐
     │  top horiz   │ ← measure center of this bar
     └──────────────┘
  f  │              │ b ← measure x of this bar's center
     │              │     (use b=x, any y in the top-right bar)
     ┌──────────────┐
     │  mid horiz   │ ← g=[cx, y_mid]
     └──────────────┘
  e  │              │ c  (derived)
     │              │
     └──────────────┘
        d  (derived)
```

`g.x` and `a.x` should both be at the **horizontal center** of the digit.  
`b` is just an integer (x coordinate) — the component only uses the x value to derive left/right positions.

### Calibration steps

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
   - Hover over the center of the middle horizontal bar → note `[x, y]` → this is `g`
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
    update_interval: 2s
    sample_radius: 3          # pixels averaged around each sample point
    threshold: auto           # or fixed int 0-255
    display_off_threshold: 10 # max brightness below this = display off
    digits:
      - a: [195, 175]         # top horizontal center [x, y]
        g: [195, 220]         # middle horizontal center [x, y]
        b: 250                # top-right vertical x coordinate
      - a: [285, 175]
        g: [285, 220]
        b: 340
      - a: [375, 175]
        g: [375, 220]
        b: 430
      - a: [460, 175]
        g: [460, 220]
        b: 515
```

### Configuration reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `camera_id` | id | required | Reference to `esp32_camera` component |
| `digits` | list[4] | required | Exactly 4 digit definitions |
| `digits[].a` | [x, y] | required | Top horizontal segment center pixel |
| `digits[].g` | [x, y] | required | Middle horizontal segment center pixel |
| `digits[].b` | int | required | X coordinate of top-right vertical segment |
| `sample_radius` | int | 2 | Radius of averaging patch in pixels |
| `threshold` | `auto` or 0–255 | `auto` | Segment ON/OFF threshold. `auto` = `(min+max)/2` per frame |
| `display_off_threshold` | int | 10 | Max brightness below this → display off → publishes `NaN` |
| `update_interval` | duration | `5s` | How often to sample a camera frame |

### Pixel format

| Format | Notes |
|--------|-------|
| `GRAYSCALE` | Recommended. Direct 8-bit per pixel access, minimal processing |
| `RGB565` | Supported. Converted to grayscale via luma coefficients |
| `JPEG` | **Not supported.** Too expensive to decode on ESP32 |

## Sensor output

- **Unit**: mm
- **Accuracy**: 0 decimal places (integer)
- **Range**: 0–9999 mm
- **NaN** published when: display off, unknown segment pattern, camera unavailable

## Troubleshooting

**All digits decode as `?`**  
→ Coordinates are off. Run `python tests/validate.py --debug` with your image to see per-segment brightness values.

**Some digits correct, others `?`**  
→ Adjust `a`, `g`, or `b` for the failing digit. The `b` x-coordinate is often the most sensitive — try moving it 5–10 px inward from the right edge.

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
