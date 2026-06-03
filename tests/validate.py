"""
Validation script: run the Python equivalent of the C++ pipeline against test images.

Usage:
    python tests/validate.py                        # defaults to test_cases/size_2
    python tests/validate.py --dir test_cases/size_1
    python tests/validate.py --debug
    python tests/validate.py --dir /path/to/images --debug

CALIBRATION: The coords below are calibrated for test_cases/size_2 (640x480, close-up).
For your own camera setup, run with --debug to see per-segment brightness values, then
adjust DIGIT_ANCHORS until all images decode correctly.
"""

import sys
import argparse
from pathlib import Path
from PIL import Image


def derive_segment_centers(a, d, b):
    ax, ay = a
    dx, dy = d
    bx, by = b
    gx = (ax + dx) // 2  # middle segment x = (a + d) / 2
    gy = (ay + dy) // 2  # middle segment y = (a + d) / 2
    dvx = gx - ax        # down vector x (g - a)
    dvy = gy - ay        # down vector y (g - a)
    return {
        'a':   (ax,          ay),            # anchor a
        'b':   (bx,          by),            # anchor b
        'c':   (bx + dvx,    by + dvy),      # b + down
        'd':   (dx,          dy),            # anchor d
        'e':   (ax+dx - bx,  ay+dy - by),    # a + d - b
        'f':   (ax+gx - bx,  ay+gy - by),    # a + g - b
        'g':   (gx,          gy),            # (a + d) / 2
        'bg0': ((ax+gx)//2,  (ay+gy)//2),    # upper interior background reference
        'bg1': ((dx+gx)//2,  (dy+gy)//2),    # lower interior background reference
    }


SEGMENT_PATTERNS = [
    0b0111111,  # 0
    0b0000110,  # 1
    0b1011011,  # 2
    0b1001111,  # 3
    0b1100110,  # 4
    0b1101101,  # 5
    0b1111101,  # 6
    0b0000111,  # 7
    0b1111111,  # 8
    0b1101111,  # 9
]


def decode_digit(bitmask):
    for i, p in enumerate(SEGMENT_PATTERNS):
        if p == bitmask:
            return i
    return None


DASH_BITMASK = 0b1000000  # segment g only — kreska (dash); verified against size_3/kreski.jpg


def determine_state(all_bright, digit_segments, bg_refs=None, display_off_threshold=20):
    """Mirror C++ last_state logic. Returns (state, value_or_None).

    States:
      'off'   — global_max < display_off_threshold
      'ready' — all 4 digits have DASH_BITMASK (segment g only)
      'ok'    — all 4 digits decode to 0-9; value is the mm integer
      'fail'  — any other case (unknown bitmask, not dash)

    bg_refs: per-digit background brightness (avg of 2 interior points).
             If None, falls back to per-digit min (for unit tests with synthetic data).
    """
    gmax = max(all_bright)
    if gmax < display_off_threshold:
        return "off", None
    bitmasks = []
    for i, bright in enumerate(digit_segments):
        black_ref = bg_refs[i] if bg_refs is not None else min(bright)
        bright_max = max(bright)
        thresh = (black_ref + bright_max) // 2
        bitmasks.append(sum((1 << j) for j, b in enumerate(bright) if b >= thresh))
    if all(b == DASH_BITMASK for b in bitmasks):
        return "ready", None
    digits = [decode_digit(b) for b in bitmasks]
    if all(d is not None for d in digits):
        value = digits[0] * 1000 + digits[1] * 100 + digits[2] * 10 + digits[3]
        return "ok", value
    return "fail", None


def sample_brightness(pixels, width, height, cx, cy, radius=4):
    total, count = 0, 0
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            x, y = cx + dx, cy + dy
            if 0 <= x < width and 0 <= y < height:
                px = pixels[x, y]
                total += px if isinstance(px, int) else (px[0] * 30 + px[1] * 59 + px[2] * 11) // 100
                count += 1
    return total // count if count else 0


# ── CALIBRATION SECTION ──────────────────────────────────────────────────────
# Calibrated for test_cases/size_2 (640x480 close-up, lower row of display).
#
# To calibrate for your own setup:
#   1. Save a camera snapshot (enable esp32_camera_web_server in ESPHome)
#   2. Open calibration.html, load the snapshot directory
#   3. Place anchors:
#      a = center of TOP HORIZONTAL segment
#      d = center of BOTTOM HORIZONTAL segment
#      b = center of TOP-RIGHT VERTICAL segment (the b-segment itself)
#   4. Run:  python tests/validate.py --debug
#   5. Adjust until all digits decode correctly

DIGIT_ANCHORS = [
    # digit 0 (leftmost)  — by = (ay+gy)//2 = 196, gy = (143+355)//2 = 249
    {"a": (105, 143), "d": (105, 355), "b": (140, 196)},
    # digit 1
    {"a": (230, 143), "d": (230, 355), "b": (265, 196)},
    # digit 2
    {"a": (362, 143), "d": (362, 355), "b": (398, 196)},
    # digit 3 (rightmost)
    {"a": (485, 143), "d": (485, 355), "b": (515, 196)},
]
SAMPLE_RADIUS = 4
DISPLAY_OFF_THRESHOLD = 20
# ─────────────────────────────────────────────────────────────────────────────


def process_image(path, debug=False):
    img = Image.open(path).convert("L")
    pixels = img.load()
    w, h = img.size

    all_bright = []
    digit_segments = []

    bg_refs = []
    for anchors in DIGIT_ANCHORS:
        centers = derive_segment_centers(anchors["a"], anchors["g"], anchors["b"])
        seg_order = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
        bright = [sample_brightness(pixels, w, h, *centers[s], radius=SAMPLE_RADIUS)
                  for s in seg_order]
        digit_segments.append(bright)
        all_bright.extend(bright)
        bg0 = sample_brightness(pixels, w, h, *centers['bg0'], radius=SAMPLE_RADIUS)
        bg1 = sample_brightness(pixels, w, h, *centers['bg1'], radius=SAMPLE_RADIUS)
        bg_refs.append((bg0 + bg1) // 2)

    global_max = max(all_bright)

    if global_max < DISPLAY_OFF_THRESHOLD:
        if debug:
            print(f"  DISPLAY OFF (max brightness {global_max} < {DISPLAY_OFF_THRESHOLD})")
        return None

    digits = []
    for d, bright in enumerate(digit_segments):
        black_ref = bg_refs[d]
        bright_max = max(bright)
        thresh = (black_ref + bright_max) // 2
        bitmask = sum((1 << i) for i, b in enumerate(bright) if b >= thresh)
        digit = decode_digit(bitmask)
        if debug:
            print(f"  digit {d}: bg={black_ref} thresh={thresh} bright={bright} bitmask={bin(bitmask)} -> {digit}")
        if digit is None:
            if not debug:
                print(f"  {path.name}: UNKNOWN bitmask {bin(bitmask)} for digit {d}")
            return None
        digits.append(digit)

    value = digits[0] * 1000 + digits[1] * 100 + digits[2] * 10 + digits[3]
    return value


def main():
    parser = argparse.ArgumentParser(description="Validate digit_number detection against test images")
    parser.add_argument("--debug", action="store_true", help="Show per-segment brightness values")
    parser.add_argument("--dir", default=None,
                        help="Directory containing .jpg images (default: test_cases/size_2)")
    args = parser.parse_args()

    if args.dir:
        test_dir = Path(args.dir)
    else:
        test_dir = Path(__file__).parent.parent / "test_cases" / "size_2"

    images = sorted(test_dir.glob("*.jpg"))

    if not images:
        print(f"No .jpg images found in {test_dir}")
        sys.exit(1)

    print(f"Processing {len(images)} images from {test_dir}")
    for img_path in images:
        if args.debug:
            print(f"\n{img_path.name}:")
        result = process_image(img_path, debug=args.debug)
        if result is None:
            print(f"{img_path.name}: None (display off or unknown pattern)")
        else:
            print(f"{img_path.name}: {result} mm")


if __name__ == "__main__":
    main()
