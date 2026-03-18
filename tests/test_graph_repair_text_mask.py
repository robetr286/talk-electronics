from __future__ import annotations

import cv2
import numpy as np

from talk_electronic.services.line_detection import LineDetectionConfig, _detect_text_mask, _graph_repair_skeleton


def _make_text_like_strip(size: int = 120, cy: int = 60) -> np.ndarray:
    img = np.zeros((size, size), dtype=np.uint8)
    # draw many short small dots forming a horizontal text-like band
    for x in range(40, 80, 6):
        for y in range(cy - 3, cy + 4, 3):
            cv2.circle(img, (x + (y % 5), y), 1, 255, -1)
    return img


def test_detect_text_mask_detects_cluster():
    img = _make_text_like_strip()
    cfg = LineDetectionConfig()  # default enables text masking
    mask = _detect_text_mask(img, cfg)
    assert mask is not None
    # mask should cover at least some pixels where the 'text' exists
    assert int(mask.sum()) > 0


def test_graph_repair_respects_text_mask():
    size = 120
    skeleton = np.zeros((size, size), dtype=np.uint8)
    binary = np.zeros_like(skeleton)

    # two short segments near each other
    cv2.line(skeleton, (20, 20), (30, 30), 1, 1)
    cv2.line(skeleton, (90, 90), (80, 80), 1, 1)
    cv2.line(binary, (20, 20), (30, 30), 255, 3)
    cv2.line(binary, (90, 90), (80, 80), 255, 3)

    # create dotted mask along the entire path (baseline — should allow join)
    general = np.zeros_like(skeleton)
    for t in range(0, 101, 10):
        x = int(30 + (80 - 30) * (t / 100.0))
        y = int(30 + (80 - 30) * (t / 100.0))
        cv2.circle(general, (x, y), 2, 255, -1)

    # add a very dense 'text-like' cluster in the center that overlaps the dotted path
    text_like = np.zeros_like(general)
    cy = size // 2
    for x in range(30, 81, 2):
        for y in range(cy - 6, cy + 7, 2):
            cv2.circle(text_like, (x + (y % 3), y), 1, 255, -1)
    # overlay the 'text' onto the candidate mask
    general_with_text = cv2.bitwise_or(general, text_like)

    cfg = LineDetectionConfig(
        dotted_line_graph_repair_enable=True,
        dotted_line_bridge_endpoint_max_distance=200,
        # be permissive on angle for the synthetic test
        dotted_line_graph_repair_angle_threshold=80.0,
        # require majority overlap to accept join
        dotted_line_graph_repair_overlap_fraction=0.5,
        dotted_line_graph_repair_max_joins_per_image=10,
    )

    before = int(skeleton.sum())
    # repair when the general mask still includes the text area -> should join
    repaired1 = _graph_repair_skeleton(skeleton.copy(), binary.copy(), general_with_text, cfg)
    after1 = int(repaired1.sum())
    assert after1 > before, "Expected join when general mask includes candidate across text"

    # Now simulate text-masking by removing the central cluster from general mask
    # Determine text mask using heuristic and then zero out intersection
    text_mask = _detect_text_mask(text_like, cfg)
    assert text_mask.sum() > 0
    general_without_text = cv2.bitwise_and(general_with_text, cv2.bitwise_not(text_mask))

    repaired2 = _graph_repair_skeleton(skeleton.copy(), binary.copy(), general_without_text, cfg)
    after2 = int(repaired2.sum())

    # With the dotted candidates removed in the text region, the algorithm should not join
    assert after2 == before, "Expected no join when candidates are excluded by text mask"
