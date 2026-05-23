"""Tests for determine_state() logic — unit tests + image integration tests."""

import pytest
from pathlib import Path
from PIL import Image

from tests.validate import (
    DASH_BITMASK,
    DISPLAY_OFF_THRESHOLD,
    decode_digit,
    derive_segment_centers,
    determine_state,
    sample_brightness,
)

# ── Unit tests ────────────────────────────────────────────────────────────────

def test_dash_bitmask_is_not_a_digit():
    """DASH_BITMASK must not decode to any digit 0-9."""
    assert decode_digit(DASH_BITMASK) is None


def test_state_off_when_dark():
    all_bright = [5] * 28
    digit_segments = [[5] * 7 for _ in range(4)]
    state, value = determine_state(all_bright, digit_segments)
    assert state == "off"
    assert value is None


def test_state_ready_when_all_dashes():
    # thresh = (5 + 200) // 2 = 102
    # each digit: only segment g (index 6) at 200, rest at 5 → bitmask = DASH_BITMASK
    digit_segments = [[5, 5, 5, 5, 5, 5, 200] for _ in range(4)]
    all_bright = [b for seg in digit_segments for b in seg]
    state, value = determine_state(all_bright, digit_segments)
    assert state == "ready"
    assert value is None


def test_state_ok_when_valid_digits():
    # Digits: 0, 1, 2, 7 → value = 127
    # thresh = (5 + 200) // 2 = 102
    # digit 0: segments a,b,c,d,e,f bright → bitmask 0b0111111 = 63
    d0 = [200, 200, 200, 200, 200, 200, 5]
    # digit 1: segments b,c bright → bitmask 0b0000110 = 6
    d1 = [5, 200, 200, 5, 5, 5, 5]
    # digit 2: segments a,b,d,e,g bright → bitmask 0b1011011 = 91
    d2 = [200, 200, 5, 200, 200, 5, 200]
    # digit 7: segments a,b,c bright → bitmask 0b0000111 = 7
    d7 = [200, 200, 200, 5, 5, 5, 5]
    digit_segments = [d0, d1, d2, d7]
    all_bright = [b for seg in digit_segments for b in seg]
    state, value = determine_state(all_bright, digit_segments)
    assert state == "ok"
    assert value == 127


def test_state_fail_when_one_digit_unknown():
    # Digit 2 has only segment a (bitmask 0b0000001 = 1) — unknown, not a dash
    d_dash = [5, 5, 5, 5, 5, 5, 200]   # DASH_BITMASK
    d_fail = [200, 5, 5, 5, 5, 5, 5]   # only segment a — not a digit, not a dash
    digit_segments = [d_dash, d_dash, d_fail, d_dash]
    all_bright = [b for seg in digit_segments for b in seg]
    state, value = determine_state(all_bright, digit_segments)
    assert state == "fail"
    assert value is None


def test_state_fail_not_confused_with_ready_when_mixed():
    # 3 dashes + 1 unknown bitmask → fail, not ready
    d_dash = [5, 5, 5, 5, 5, 5, 200]
    d_fail = [200, 200, 5, 5, 5, 5, 5]  # a,b only — not a digit
    digit_segments = [d_dash, d_dash, d_dash, d_fail]
    all_bright = [b for seg in digit_segments for b in seg]
    state, value = determine_state(all_bright, digit_segments)
    assert state == "fail"


# ── Integration tests using real size_3 images ────────────────────────────────

IMG_DIR = Path(__file__).parent.parent / "test_cases" / "size_3"

PROD_ANCHORS = [
    {"a": (135, 230), "g": (135, 357), "bx": 172},
    {"a": (292, 230), "g": (292, 357), "bx": 332},
    {"a": (449, 230), "g": (449, 357), "bx": 484},
    {"a": (603, 230), "g": (603, 357), "bx": 636},
]
PROD_SAMPLE_RADIUS = 5
PROD_OFF_THRESHOLD = 20


def _load_state(filename):
    img = Image.open(IMG_DIR / filename).convert("L")
    pixels = img.load()
    w, h = img.size
    all_bright, digit_segs = [], []
    for a in PROD_ANCHORS:
        centers = derive_segment_centers(a["a"], a["g"], a["bx"])
        bright = [sample_brightness(pixels, w, h, *centers[s], radius=PROD_SAMPLE_RADIUS)
                  for s in "abcdefg"]
        digit_segs.append(bright)
        all_bright.extend(bright)
    return determine_state(all_bright, digit_segs, PROD_OFF_THRESHOLD)


def test_real_image_off():
    state, value = _load_state("off.jpg")
    assert state == "off"
    assert value is None


def test_real_image_ready():
    state, value = _load_state("kreski.jpg")
    assert state == "ready"
    assert value is None


def test_real_image_ok():
    state, value = _load_state("capture.jpg")
    assert state == "ok"
    assert value == 3074
