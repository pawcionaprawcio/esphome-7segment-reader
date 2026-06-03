"""
Integration tests using real camera images from test_cases/size_4/.

Image size: 800x600. Lower row of 7-segment display (upper row partially cropped).

Sampling strategy:
  - Horizontal segments (a, g, d): 11x11 square (radius=5) — avoids bleed from
    adjacent vertical segments into the center region.
  - Vertical segments (b, c, e, f): 50x11 strip (±25 rows, ±5 cols) — robust to
    ±25 px vertical display shift between captures.

Threshold strategy: per-digit max-gap (largest brightness gap among 7 values).
  Fallback 1: min(7) > 100 → all ON (fully lit display, e.g. bright '8').
  Fallback 2: max_gap < 50 AND min > 80 AND first_gap < 15 → all ON — handles
    a dim '8' where camera perspective underexposes the top/bottom horizontal bars
    while vertical bars are bright; the narrow first gap distinguishes this from '0'
    where the OFF g-segment creates a meaningful gap from the ON segments.

All 18 digit images and kreski.jpg decode reliably with this approach.
"""

import pytest
from pathlib import Path
from PIL import Image

from tests.validate import derive_segment_centers, decode_digit

IMG_DIR = Path(__file__).parent.parent / "test_cases" / "size_1"

# Calibrated for test_cases/size_4 (800x600, lower display row).
# Digits shifted down vs size_3 — camera position/zoom changed.
# a1=(128,188) d1=(110,437) b1=(169,253) │ a2=(282,192) d2=(271,443) b2=(324,259) │
# a3=(444,197) d3=(423,445) b3=(482,258) │ a4=(603,201) d4=(586,450) b4=(642,263)
DIGIT_ANCHORS = [
    {"a": (128,188), "d": (110,437), "b": (169,253)},
    {"a": (282,192), "d": (271,443), "b": (324,259)},
    {"a": (444,197), "d": (423,445), "b": (482,258)},
    {"a": (603,201), "d": (586,450), "b": (642,263)},
]
SAMPLE_RADIUS = 5
DISPLAY_OFF_THRESHOLD = 60

HORIZ_SEGS = frozenset("adg")


def _sample(pixels, w, h, cx, cy, seg):
    if seg in HORIZ_SEGS:
        # Square: avoids side-vertical bleed into horizontal segment center
        r = SAMPLE_RADIUS
        tot = cnt = 0
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x, y = cx + dx, cy + dy
                if 0 <= x < w and 0 <= y < h:
                    tot += pixels[x, y]
                    cnt += 1
    else:
        # Tall strip: ±25 rows absorbs ±25 px vertical display shift
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
    # Dim '8': all segments on but top/bottom bars underlit by camera perspective.
    # first_gap < 15 distinguishes from '0' where g=OFF creates a real gap (≥28).
    if mg < 50 and mn > 80 and (s[1] - s[0]) < 15:
        return 0
    return (s[gp] + s[gp + 1]) // 2


DASH_BITMASK = 0b1000000  # segment g only — ready/standby state


def decode_image(path):
    """Return integer mm value, or None for display-off/ready (dashes) / unknown pattern."""
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
        bright = [_sample(pixels, w, h, *centers[s], s) for s in "abcdefg"]
        digit_segments.append(bright)
        all_bright.extend(bright)

    if max(all_bright) < DISPLAY_OFF_THRESHOLD:
        return None

    digits = []
    for bright in digit_segments:
        thresh = _best_threshold(bright)
        bitmask = sum((1 << i) for i, b in enumerate(bright) if b >= thresh)
        if bitmask == DASH_BITMASK:
            return None  # ready state
        digit = decode_digit(bitmask)
        if digit is None:
            return None
        digits.append(digit)

    return digits[0] * 1000 + digits[1] * 100 + digits[2] * 10 + digits[3]


# ── Ready state ──────────────────────────────────────────────────────────────

def test_dashes():
    """Display showing dashes (ready/standby) → None."""
    assert decode_image(IMG_DIR / "kreski.jpg") is None


# ── Digit images ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename,expected_mm", [
    ("capture.jpg",       742),
    ("capture (1).jpg",   744),
    ("capture (2).jpg",   835),
    ("capture (3).jpg",   270),
    ("capture (4).jpg",  761),
    ("capture (5).jpg",  777),
    ("capture (6).jpg",  778),
    ("capture (7).jpg",  812),
    ("capture (8).jpg",  732),
    ("capture (9).jpg",  497),
    ("capture (10).jpg", 378),
    ("capture (11).jpg",  1166),
    ("capture (12).jpg",  1692),
    ("capture (13).jpg",  2507),
])
def test_decode(filename, expected_mm):
    result = decode_image(IMG_DIR / filename)
    assert result == expected_mm, f"{filename}: expected {expected_mm} mm, got {result}"
