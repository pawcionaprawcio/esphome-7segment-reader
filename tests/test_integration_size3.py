"""
Integration tests using real camera images from test_cases/size_3/.

Image size: 800x600. Calibrated anchor coordinates below.

Threshold strategy: per-digit max-gap threshold (finds largest brightness gap
among 7 segment values to split ON/OFF). Fallback: if min(7) > 100, all segments
are ON (handles digit '8' where all segments are similarly bright).

All 15 digit images decode reliably with this approach.
"""

import pytest
from pathlib import Path
from PIL import Image

from tests.validate import derive_segment_centers, decode_digit, sample_brightness

IMG_DIR = Path(__file__).parent.parent / "test_cases" / "size_3"

# Calibrated for test_cases/size_3 (800x600).
DIGIT_ANCHORS = [
    {"a": (135, 230), "g": (135, 357), "bx": 172},
    {"a": (292, 230), "g": (292, 357), "bx": 332},
    {"a": (449, 230), "g": (449, 357), "bx": 484},
    {"a": (603, 230), "g": (603, 357), "bx": 636},
]
SAMPLE_RADIUS = 5
DISPLAY_OFF_THRESHOLD = 20
ALL_ON_MIN = 100


def _best_threshold(bright):
    if min(bright) > ALL_ON_MIN:
        return 0
    s = sorted(bright)
    max_gap, gap_pos = 0, 0
    for i in range(len(s) - 1):
        g = s[i+1] - s[i]
        if g > max_gap:
            max_gap = g
            gap_pos = i
    return (s[gap_pos] + s[gap_pos+1]) // 2


def decode_image(path):
    """Return integer mm value, or None for display-off/unknown-pattern."""
    img = Image.open(path).convert("L")
    pixels = img.load()
    w, h = img.size

    all_bright = []
    digit_segments = []

    for anchors in DIGIT_ANCHORS:
        centers = derive_segment_centers(anchors["a"], anchors["g"], anchors["bx"])
        bright = [sample_brightness(pixels, w, h, *centers[s], radius=SAMPLE_RADIUS)
                  for s in "abcdefg"]
        digit_segments.append(bright)
        all_bright.extend(bright)

    if max(all_bright) < DISPLAY_OFF_THRESHOLD:
        return None

    digits = []
    for bright in digit_segments:
        thresh = _best_threshold(bright)
        bitmask = sum((1 << i) for i, b in enumerate(bright) if b >= thresh)
        digit = decode_digit(bitmask)
        if digit is None:
            return None
        digits.append(digit)

    return digits[0] * 1000 + digits[1] * 100 + digits[2] * 10 + digits[3]


# ── Edge cases: None results ─────────────────────────────────────────────────

def test_display_off():
    """Completely dark frame → None."""
    assert decode_image(IMG_DIR / "off.jpg") is None


def test_dashes():
    """Display showing dashes → None."""
    assert decode_image(IMG_DIR / "kreski.jpg") is None


# ── Digit images ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename,expected_mm", [
    ("capture.jpg",      3074),
    ("capture (1).jpg",  2078),
    ("capture (2).jpg",  3554),
    ("capture (3).jpg",  1082),
    ("capture (4).jpg",  1650),
    ("capture (5).jpg",  2050),
    ("capture (6).jpg",   979),
    ("capture (7).jpg",   409),
    ("capture (8).jpg",   332),
    ("capture (9).jpg",  1401),
    ("capture (10).jpg", 2924),
    ("capture (11).jpg", 3200),
    ("capture (12).jpg", 1884),
    ("capture (13).jpg", 1551),
    ("capture (14).jpg", 1481),
])
def test_decode(filename, expected_mm):
    result = decode_image(IMG_DIR / filename)
    assert result == expected_mm, f"{filename}: expected {expected_mm} mm, got {result}"
