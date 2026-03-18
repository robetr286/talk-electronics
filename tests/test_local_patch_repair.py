import numpy as np

from debug.graph_repair_validation import local_patch_repair as lpr


def test_bresenham_line_horizontal():
    pts = lpr.bresenham_line((10, 10), (10, 13))
    assert pts == [(10, 10), (10, 11), (10, 12), (10, 13)]


def test_endpoints_from_mask_simple_line():
    # horizontal line of length 3 -> two endpoints
    mask = np.zeros((5, 5), dtype=np.uint8)
    mask[2, 1] = 1
    mask[2, 2] = 1
    mask[2, 3] = 1
    eps = lpr.endpoints_from_mask(mask)
    assert len(eps) == 2
    assert (2, 1) in eps and (2, 3) in eps


def test_try_connect_respects_min_line_ratio():
    # Create a mask with two short stub-lines separated by one pixel gap
    # LHS: (2,0),(2,1)  RHS: (2,3),(2,4) -> endpoints at (2,1) and (2,3)
    mask = np.zeros((5, 5), dtype=np.uint8)
    mask[2, 0] = 1
    mask[2, 1] = 1
    mask[2, 3] = 1
    mask[2, 4] = 1

    # original_binary has a single supporting pixel at (2,2) -> prop = 1/3 ~ 0.333
    original_binary = np.zeros((5, 5), dtype=np.uint8)
    original_binary[2, 2] = 1

    # With min_line_ratio=0.5 no connection should occur
    connected = lpr.try_connect(mask, original_binary, max_dist=3, min_line_ratio=0.5)
    assert connected[2, 2] == 0

    # With min_line_ratio=0.2 connection should occur
    connected2 = lpr.try_connect(mask, original_binary, max_dist=3, min_line_ratio=0.2)
    # middle point should be set to 1
    assert connected2[2, 2] == 1
