import nab_core
from nab_core import make_mask, shape_bbox


def test_sub_and_union_masks():
    a = {"type": "rect", "x1": 10, "y1": 10, "x2": 60, "y2": 60}
    b = {"type": "rect", "x1": 30, "y1": 30, "x2": 80, "y2": 80}
    sub = {"type": "sub", "base": a, "cut": b}
    uni = {"type": "union", "parts": [a, b]}
    ms, mu = make_mask((100, 100), sub), make_mask((100, 100), uni)
    assert ms.getpixel((20, 20)) == 255 and ms.getpixel((40, 40)) == 0 and ms.getpixel((70, 70)) == 0
    assert mu.getpixel((20, 20)) == 255 and mu.getpixel((70, 70)) == 255 and mu.getpixel((5, 5)) == 0
    assert shape_bbox(uni, (100, 100)) == (10, 10, 81, 81)
    assert shape_bbox(sub, (100, 100)) == shape_bbox(a, (100, 100))
