from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from talk_electronic.services.line_detection import LineDetectionConfig, detect_lines


def test_transistor_real_case_exists():
    # If the real transistor-like image exists, ensure pipeline runs and doesn't crash
    p = Path("data") / "junction_inputs" / "small" / "schemat_page28_wycinek-prostokat_2025-12-01_19-29-45.png"
    if not p.exists():
        import pytest

        pytest.skip("real transistor test image not available")
    img = cv2.imread(str(p))
    cfg = LineDetectionConfig(dotted_line_graph_repair_enable=True)
    res = detect_lines(img, binary=False, config=cfg)
    assert hasattr(res, "lines")


def test_dense_mesh_no_false_merges():
    # create a moderately dense mesh and ensure conservative defaults avoid mass merging
    size = 220
    img = np.zeros((size, size), dtype=np.uint8)
    for y in range(20, size - 20, 12):
        cv2.line(img, (20, y), (size - 20, y), 255, 2)
    for x in range(20, size - 20, 12):
        cv2.line(img, (x, 20), (x, size - 20), 255, 2)

    cfg = LineDetectionConfig(dotted_line_graph_repair_enable=True)
    res = detect_lines(img, binary=False, config=cfg)
    # expect multiple segments — not a single giant merged line
    assert len(res.lines) > 5


def test_scale_sensitivity():
    # check that upscaling improves connectivity for a dotted diagonal synthetic case
    size = 160
    base = np.zeros((size, size), dtype=np.uint8)
    # dotted diagonal
    for t in range(10, size - 10, 6):
        cv2.circle(base, (t, t), 1, 255, -1)

    cfg = LineDetectionConfig(dotted_line_graph_repair_enable=True)

    # small (1x)
    res1 = detect_lines(base, binary=False, config=cfg)

    # upscaled (2x) — resize & process
    large = cv2.resize(base, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_LINEAR)
    res2 = detect_lines(large, binary=False, config=cfg)

    # at least one of the runs should produce detectable segments; prefer the scaled result
    assert len(res2.lines) >= len(res1.lines)
