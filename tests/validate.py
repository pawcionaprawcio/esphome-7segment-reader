"""
Validation script: run Python equivalent of the C++ pipeline against test_cases/*.jpg.

Usage:
    python tests/validate.py
    python tests/validate.py --debug

CALIBRATION REQUIRED: Fill in the coords for your specific camera/display setup.
The coords below are rough starting estimates from visual inspection.
Run with --debug to see brightness values per segment and adjust coords.
"""

import sys
import argparse
from pathlib import Path
from PIL import Image


def derive_segment_centers(a, g, bx):
    ax, ay = a
    gx, gy = g
    x_right = bx
    x_left = 2 * ax - bx
    y_top = ay
    y_mid = gy
    y_bot = 2 * gy - ay
    y_th = (ay + gy) // 2
    y_bh = (gy + y_bot) // 2
    return {
        'a': (ax,      y_top),
        'b': (x_right, y_th),
        'c': (x_right, y_bh),
        'd': (ax,      y_bot),
        'e': (x_left,  y_bh),
        'f': (x_left,  y_th),
        'g': (gx,      y_mid),
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


def sample_brightness(pixels, width, height, cx, cy, radius=2):
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
# Fill in pixel coords for YOUR camera+display setup.
# a = center of top horizontal segment [x, y]
# g = center of middle horizontal segment [x, y]
# bx = x coordinate of top-right vertical segment center
# These are rough estimates — run with --debug and adjust.
DIGIT_ANCHORS = [
    # digit 0 (leftmost)
    {"a": (195, 175), "g": (195, 220), "bx": 250},
    # digit 1
    {"a": (285, 175), "g": (285, 220), "bx": 340},
    # digit 2
    {"a": (375, 175), "g": (375, 220), "bx": 430},
    # digit 3 (rightmost)
    {"a": (460, 175), "g": (460, 220), "bx": 515},
]
SAMPLE_RADIUS = 2
DISPLAY_OFF_THRESHOLD = 10
# ─────────────────────────────────────────────────────────────────────────────


def process_image(path, debug=False):
    img = Image.open(path).convert("L")  # grayscale
    pixels = img.load()
    w, h = img.size

    all_bright = []
    digit_segments = []

    for anchors in DIGIT_ANCHORS:
        centers = derive_segment_centers(anchors["a"], anchors["g"], anchors["bx"])
        seg_order = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
        bright = [sample_brightness(pixels, w, h, *centers[s], radius=SAMPLE_RADIUS)
                  for s in seg_order]
        digit_segments.append(bright)
        all_bright.extend(bright)

    global_max = max(all_bright)
    global_min = min(all_bright)

    if global_max < DISPLAY_OFF_THRESHOLD:
        print(f"  {path.name}: DISPLAY OFF")
        return None

    thresh = (global_min + global_max) // 2

    digits = []
    for d, bright in enumerate(digit_segments):
        bitmask = sum((1 << i) for i, b in enumerate(bright) if b >= thresh)
        digit = decode_digit(bitmask)
        if debug:
            print(f"  digit {d}: bright={bright} bitmask={bin(bitmask)} thresh={thresh} -> {digit}")
        if digit is None:
            print(f"  {path.name}: UNKNOWN bitmask {bin(bitmask)} for digit {d}")
            return None
        digits.append(digit)

    value = digits[0] * 1000 + digits[1] * 100 + digits[2] * 10 + digits[3]
    return value


def main():
    parser = argparse.ArgumentParser(description="Validate digit_number detection against test images")
    parser.add_argument("--debug", action="store_true", help="Show per-segment brightness values")
    args = parser.parse_args()

    test_dir = Path(__file__).parent.parent / "test_cases"
    images = sorted(test_dir.glob("*.jpg"))

    if not images:
        print("No images found in test_cases/")
        sys.exit(1)

    for img_path in images:
        result = process_image(img_path, debug=args.debug)
        print(f"{img_path.name}: {result} mm")


if __name__ == "__main__":
    main()
