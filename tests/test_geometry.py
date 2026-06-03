import pytest


def derive_segment_centers(a, d, b):
    """Derive all 7 segment centers from 3 anchor points.

    Args:
        a: (x, y) center of top horizontal segment
        d: (x, y) center of bottom horizontal segment
        b: (x, y) center of top-right vertical segment

    Returns:
        dict mapping segment names to (x, y) centers
    """
    ax, ay = a
    dx, dy = d
    bx, by = b
    gx = (ax + dx) // 2  # middle segment x = (a + d) / 2
    gy = (ay + dy) // 2  # middle segment y = (a + d) / 2
    dvx = gx - ax
    dvy = gy - ay
    return {
        'a': (ax,            ay),             # anchor a
        'b': (bx,            by),             # anchor b
        'c': (bx + dvx,      by + dvy),       # b + down
        'd': (dx,            dy),             # anchor d
        'e': (ax + dx - bx,  ay + dy - by),   # a + d - b
        'f': (ax + gx - bx,  ay + gy - by),   # a + g - b
        'g': (gx,            gy),             # (a + d) / 2
    }


def test_symmetric_no_tilt():
    # b placed at y_th = (10+50)//2 = 30 — gy=(10+90)//2=50
    centers = derive_segment_centers(a=(100, 10), d=(100, 90), b=(130, 30))
    assert centers['a'] == (100, 10)
    assert centers['g'] == (100, 50)
    assert centers['d'] == (100, 90)
    assert centers['b'] == (130, 30)
    assert centers['c'] == (130, 70)   # b + down = (130+0, 30+40)
    assert centers['f'] == (70,  30)   # 100+100-130, 10+50-30
    assert centers['e'] == (70,  70)   # a+d-b = 100+100-130, 10+90-30


def test_tilted_display():
    # Display tilted: a and d have different x, b is shifted diagonally
    # a=(100,10), d=(120,90) → g=(110,50), down=(10,40)
    # b placed at top-right: b=(140, 32)
    centers = derive_segment_centers(a=(100, 10), d=(120, 90), b=(140, 32))
    # c = b + down = (140+10, 32+40)
    assert centers['c'] == (150, 72)
    # d = anchor = (120, 90)
    assert centers['d'] == (120, 90)
    # e = a+d-b = (100+120-140, 10+90-32) = (80, 68)
    assert centers['e'] == (80, 68)
    # f = a+g-b = (100+110-140, 10+50-32) = (70, 28)
    assert centers['f'] == (70, 28)


def test_backward_compat_no_tilt():
    # Verify new formula gives same results as old algorithm when no tilt
    # Old: a=(200,20), g=(200,60), bx=240 → y_th=40, by=40; d=(200,100)
    centers = derive_segment_centers(a=(200, 20), d=(200, 100), b=(240, 40))
    assert centers['d'][1] == 100    # 2*60-20
    assert centers['b'][1] == 40     # by
    assert centers['f'][1] == 40     # ay+gy-by = 20+60-40
    assert centers['c'][1] == 80     # by+dy = 40+40
    assert centers['e'][1] == 80     # 2*gy-by = 120-40
    assert centers['b'][0] == 240
    assert centers['f'][0] == 160    # ax+gx-bx = 200+200-240


def test_asymmetric_x_tilt():
    # a.x != d.x (slight camera angle), b placed at y_th height
    # a=(100,10), d=(104,90) → g=(102,50), down=(2,40), y_th=30
    centers = derive_segment_centers(a=(100, 10), d=(104, 90), b=(135, 30))
    # f = a+g-b = (100+102-135, 10+50-30) = (67, 30)
    assert centers['f'][0] == 67
    # e = 2g-b = (204-135, 100-30) = (69, 70)
    assert centers['e'][0] == 69
    assert centers['b'][0] == 135
    # c = b+down = (135+2, 30+40) = (137, 70)
    assert centers['c'][0] == 137
