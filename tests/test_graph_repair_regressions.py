from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from talk_electronic.services.line_detection import (
    LineDetectionConfig,
    _detect_dotted_candidates,
    _graph_repair_skeleton,
    _prepare_image,
)
from talk_electronic.services.skeleton import SkeletonEngine


def _component_count(arr: np.ndarray) -> int:
    # expects binary (0/1) array
    num_labels, labels = cv2.connectedComponents(arr.astype(np.uint8))[:2]
    # subtract background
    return max(0, num_labels - 1)


def test_transistor_like_no_false_merge():
    # three short segments arranged like transistor pads — conservative repair
    size = 120
    skeleton = np.zeros((size, size), dtype=np.uint8)
    binary = np.zeros_like(skeleton)

    # left pad (vertical short)
    cv2.line(skeleton, (20, 20), (20, 35), 1, 1)
    cv2.line(binary, (20, 20), (20, 35), 255, 3)

    # right pad (vertical short)
    cv2.line(skeleton, (100, 20), (100, 35), 1, 1)
    cv2.line(binary, (100, 20), (100, 35), 255, 3)

    # bottom pad (horizontal short) centered
    cv2.line(skeleton, (45, 90), (75, 90), 1, 1)
    cv2.line(binary, (45, 90), (75, 90), 255, 3)

    # dotted general_mask that *touches* central area but should NOT cause
    # a global merge under conservative defaults
    general = np.zeros_like(skeleton)
    for x in range(30, 91, 6):
        cv2.circle(general, (x, 55), 2, 255, -1)

    cfg = LineDetectionConfig(
        dotted_line_graph_repair_enable=True,
        dotted_line_graph_repair_angle_threshold=15.0,
        dotted_line_graph_repair_overlap_fraction=0.4,
        dotted_line_graph_repair_max_joins_per_image=10,
        dotted_line_graph_repair_max_nodes=500,
    )

    before_components = _component_count(skeleton)
    repaired = _graph_repair_skeleton(skeleton.copy(), binary.copy(), general, cfg)
    after_components = _component_count(repaired)

    # conservative default should not merge the three distinct pads together
    assert before_components == 3
    assert after_components == 3


def test_dense_grid_bails_for_large_oriented_graphs():
    # create a dense grid that produces many skeleton nodes -> ensure bailout
    size = 200
    skeleton = np.zeros((size, size), dtype=np.uint8)
    binary = np.zeros_like(skeleton)

    # grid of horizontal lines that cross many vertical lines (dense nodes)
    for r in range(20, 180, 15):
        cv2.line(skeleton, (10, r), (190, r), 1, 1)
        cv2.line(binary, (10, r), (190, r), 255, 3)
    for c in range(20, 180, 15):
        cv2.line(skeleton, (c, 10), (c, 190), 1, 1)
        cv2.line(binary, (c, 10), (c, 190), 255, 3)

    general = np.ones_like(skeleton) * 255

    # force max_nodes tiny so bailout triggers
    cfg = LineDetectionConfig(
        dotted_line_graph_repair_enable=True,
        dotted_line_graph_repair_max_nodes=10,
        dotted_line_graph_repair_max_joins_per_image=100,
        dotted_line_graph_repair_angle_threshold=45.0,
        dotted_line_graph_repair_overlap_fraction=0.2,
    )

    # original and repaired should be identical because we bail early
    repaired = _graph_repair_skeleton(skeleton.copy(), binary.copy(), general, cfg)
    assert np.array_equal(repaired, skeleton)


def test_single_gap_is_repaired():
    # two short diagonal segments with dotted candidates bridging them -> expect repair
    size = 140
    skeleton = np.zeros((size, size), dtype=np.uint8)
    binary = np.zeros_like(skeleton)

    cv2.line(skeleton, (20, 20), (40, 40), 1, 1)
    cv2.line(binary, (20, 20), (40, 40), 255, 3)
    cv2.line(skeleton, (100, 100), (80, 80), 1, 1)
    cv2.line(binary, (100, 100), (80, 80), 255, 3)

    general = np.zeros_like(skeleton)
    for t in range(0, 101, 10):
        x = int(40 + (80 - 40) * (t / 100.0))
        y = int(40 + (80 - 40) * (t / 100.0))
        cv2.circle(general, (x, y), 2, 255, -1)

    cfg = LineDetectionConfig(
        dotted_line_graph_repair_enable=True,
        dotted_line_bridge_endpoint_max_distance=200,
        dotted_line_graph_repair_angle_threshold=45.0,
        dotted_line_graph_repair_overlap_fraction=0.2,
        dotted_line_graph_repair_max_joins_per_image=10,
        dotted_line_graph_repair_max_nodes=500,
    )

    before = int(skeleton.sum())
    repaired = _graph_repair_skeleton(skeleton.copy(), binary.copy(), general, cfg)
    after = int(repaired.sum())
    assert after > before


def test_real_small_image_conservative_limits_changes():
    # load a previously seen real image (small) and assert conservative defaults
    # do not introduce massive skeleton changes (regression guard)
    img_path = Path("data") / "junction_inputs" / "small" / "schemat_page28_wycinek-prostokat_2025-12-01_19-29-45.png"
    if not img_path.exists():
        # if file not present in test environment, skip to avoid flaky failure
        import pytest

        pytest.skip("real-image fixture not available")

    image = cv2.imread(str(img_path))
    cfg = LineDetectionConfig()  # conservative defaults

    prepared = _prepare_image(image, binary=False, config=cfg)
    engine = SkeletonEngine(cfg.skeleton_config)
    res = engine.run(prepared)

    general = _detect_dotted_candidates(image, cfg)
    if general is None:
        # no dotted candidates -> nothing to test
        return
    general_mask = general[0]

    before = int((res.skeleton > 0).astype(np.uint8).sum())
    repaired = _graph_repair_skeleton(
        (res.skeleton > 0).astype(np.uint8), (res.binary > 0).astype(np.uint8), general_mask, cfg
    )
    after = int(repaired.sum())

    # guard: conservative defaults must not add more than 100 pixels on this case
    assert (after - before) <= 100
