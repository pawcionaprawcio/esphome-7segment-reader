# Inverted Display Support — Design Spec

**Date:** 2026-06-04  
**Scope:** `digit_number` ESPHome component  
**Status:** Approved

## Problem

Component assumes bright segments on dark background. Displays with dark segments on bright background (inverted) are not supported — threshold logic classifies all segments as OFF.

## Solution

Add `inverted: bool` config flag (default `false`). When `true`, brightness values for all segment and background samples are flipped (`255 - value`) before the threshold/decode pipeline runs. Downstream logic is unchanged.

## Architecture

### `digit_number.h`

Add field and setter:

```cpp
void set_inverted(bool v) { inverted_ = v; }
// ...
bool inverted_{false};
```

### `digit_number.cpp` — `process_image_()`

Track `global_min` alongside existing `global_max` during brightness sampling loop.

After all brightness values are collected, before threshold computation:

```cpp
if (inverted_) {
    for (int d = 0; d < num_digits; d++) {
        for (int s = 0; s < 7; s++)
            brightness[d][s] = 255 - brightness[d][s];
        black_ref[d] = 255 - black_ref[d];
    }
    global_max = 255 - global_min;
}
```

No other changes to `process_image_()`.

### `sensor.py`

```python
CONF_INVERTED = "inverted"

# in CONFIG_SCHEMA:
cv.Optional(CONF_INVERTED, default=False): cv.boolean,

# in to_code():
cg.add(var.set_inverted(config[CONF_INVERTED]))
```

### YAML usage

```yaml
sensor:
  - platform: digit_number
    inverted: true   # dark segments on bright background
    # ... rest of config unchanged
```

## Test Images — `test_cases/size_2/`

One-off script `tools/invert_images.py` generates inverted copies of `test_cases/size_1/`:

```python
from pathlib import Path
from PIL import Image, ImageOps

src = Path("test_cases/size_1")
dst = Path("test_cases/size_2")
dst.mkdir(exist_ok=True)
for img_path in src.glob("*.jpg"):
    ImageOps.invert(Image.open(img_path).convert("L")).save(dst / img_path.name)
```

Result: `test_cases/size_2/` contains pixel-inverted versions of all size_1 images (same filenames, same expected decoded values).

Script is committed to `tools/` but is a one-off — generated images are committed to `test_cases/size_2/`.

## Test File — `tests/test_integration_size2.py`

Mirror of `test_integration_size1.py`:

- `IMG_DIR = test_cases/size_2`
- Same anchor coordinates and sample radius as size_1
- Same expected values (inverted image + inverted pipeline = identical decode)
- `decode_image()` applies brightness flip before threshold:

```python
if inverted:
    bright = [255 - b for b in bright]
    black_ref = 255 - black_ref
    global_max_eff = 255 - global_min  # recalculated
```

## Data Flow

```
camera frame
  → sample brightness (raw)
  → [if inverted] flip: 255 - raw
  → auto-threshold per digit: (black_ref + max) / 2
  → bitmask → decode_digit → value
```

## Scope

- No changes to burst mode, trigger logic, geometry derivation, or calibration tool.
- No per-digit inversion (global flag only).
- No auto-detection of inversion.

## Files Changed

| File | Change |
|------|--------|
| `components/digit_number/digit_number.h` | +1 field, +1 setter |
| `components/digit_number/digit_number.cpp` | track `global_min`, flip block in `process_image_()` |
| `components/digit_number/sensor.py` | `CONF_INVERTED`, schema, `to_code` |
| `tools/invert_images.py` | new — one-off image generation script |
| `test_cases/size_2/` | new — 15 inverted JPEG images |
| `tests/test_integration_size2.py` | new — integration tests for inverted display |
