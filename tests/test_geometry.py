import pytest


def derive_segment_centers(a, g, bx):
    """Derive all 7 segment centers from 3 anchor points.

    Args:
        a: (x, y) center of top horizontal segment
        g: (x, y) center of middle horizontal segment
        bx: x-coordinate of right vertical segments

    Returns:
        dict mapping segment names to (x, y) centers
    """
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


def test_symmetric_digit():
    # Digit centered at x=100, a at y=10, g at y=50, b at x=130
    centers = derive_segment_centers(a=(100, 10), g=(100, 50), bx=130)
    assert centers['a'] == (100, 10)   # top horiz
    assert centers['g'] == (100, 50)   # mid horiz
    assert centers['d'] == (100, 90)   # bot horiz: reflected (2*50 - 10 = 90)
    assert centers['b'] == (130, 30)   # top-right vert: x=bx, y=(10+50)//2=30
    assert centers['c'] == (130, 70)   # bot-right vert: x=bx, y=(50+90)//2=70
    assert centers['f'] == (70, 30)    # top-left vert: x=2*100-130=70, y=30
    assert centers['e'] == (70, 70)    # bot-left vert: x=70, y=70


def test_asymmetric_x():
    # Digit where a.x != g.x (slight camera angle)
    centers = derive_segment_centers(a=(100, 10), g=(102, 50), bx=135)
    # x_left derived from a.x: 2*100 - 135 = 65
    assert centers['f'][0] == 65
    assert centers['e'][0] == 65
    assert centers['b'][0] == 135
    assert centers['c'][0] == 135


def test_y_bot_symmetric():
    centers = derive_segment_centers(a=(200, 20), g=(200, 60), bx=240)
    # y_bot = 2*60 - 20 = 100
    assert centers['d'][1] == 100
    # y_th = (20+60)//2 = 40
    assert centers['b'][1] == 40
    assert centers['f'][1] == 40
    # y_bh = (60+100)//2 = 80
    assert centers['c'][1] == 80
    assert centers['e'][1] == 80
