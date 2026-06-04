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
