import pytest

# bit 0=a, 1=b, 2=c, 3=d, 4=e, 5=f, 6=g
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


def test_all_digits_decode():
    expected = {
        0: 0b0111111,  # a,b,c,d,e,f
        1: 0b0000110,  # b,c
        2: 0b1011011,  # a,b,d,e,g
        3: 0b1001111,  # a,b,c,d,g
        4: 0b1100110,  # b,c,f,g
        5: 0b1101101,  # a,c,d,f,g
        6: 0b1111101,  # a,c,d,e,f,g
        7: 0b0000111,  # a,b,c
        8: 0b1111111,  # all
        9: 0b1101111,  # a,b,c,d,f,g
    }
    for digit, pattern in expected.items():
        assert decode_digit(pattern) == digit, f"Pattern {bin(pattern)} should decode to {digit}"


def test_unknown_bitmask_returns_none():
    assert decode_digit(0b0000000) is None  # all off
    assert decode_digit(0b1010101) is None  # random invalid


def test_display_off_detection():
    # Helper: all 28 brightnesses below threshold
    brightnesses = [5] * 28
    display_off_threshold = 10
    assert max(brightnesses) < display_off_threshold
