from __future__ import annotations

import cv2
import numpy as np

from talk_electronic.services.line_detection import LineDetectionConfig, detect_lines

# keep imports minimal for tests


def _build_dotted_diagonals(size: int = 200) -> np.ndarray:
    img = np.zeros((size, size), dtype=np.uint8)
    center = size // 2
    # draw diagonal from top-left to bottom-right but leave small gap near center
    cv2.line(img, (10, 10), (center - 6, center - 6), 255, 3)
    cv2.line(img, (center + 6, center + 6), (size - 10, size - 10), 255, 3)
    # add dotted candidates bridging the central gap (simulate dotted line)
    for i in range(-3, 4):
        cx = center + i * 3
        cy = center + i * 3
        cv2.circle(img, (cx, cy), 2, 255, -1)
    # draw other diagonal top-right to bottom-left with gap
    cv2.line(img, (size - 10, 10), (center + 6, center - 6), 255, 3)
    cv2.line(img, (center - 6, center + 6), (10, size - 10), 255, 3)
    # add dotted candidates for the other diagonal
    for i in range(-3, 4):
        cx = center + i * 3
        cy = center - i * 3
        cv2.circle(img, (cx, cy), 2, 255, -1)
    # horizontal line continuous for control
    mid_y = center + 30
    cv2.line(img, (10, mid_y), (size - 10, mid_y), 255, 3)
    return img


def test_graph_repair_connects_dotted_diagonals():
    image = _build_dotted_diagonals()

    cfg_no = LineDetectionConfig(dotted_line_graph_repair_enable=False, morph_iterations=0)
    detect_lines(image, binary=False, config=cfg_no)

    cfg_yes = LineDetectionConfig(
        dotted_line_graph_repair_enable=True,
        morph_iterations=0,
        dotted_line_graph_repair_angle_threshold=80.0,
        dotted_line_graph_repair_overlap_fraction=0.0,
        dotted_line_graph_repair_max_joins_per_image=100,
        dotted_line_bridge_endpoint_max_distance=250,
    )
    res_yes = detect_lines(image, binary=False, config=cfg_yes)

    # High-level pipeline should run without errors and produce some segments
    assert len(res_yes.lines) > 0, "Expected some segments to be detected when repair is enabled"

    # Horizontal line should remain (control) — make sure we still detect at least one horizontal segment
    angles = [round(seg.angle_deg) % 180 for seg in res_yes.lines]
    assert any(abs(a) < 10 or abs(abs(a) - 180) < 10 for a in angles), "Expected a horizontal segment to be present"


def test_graph_repair_core_function_joins_endpoints():
    # Build a simple skeleton with two endpoints and a dotted general_mask bridging them
    import numpy as np

    from talk_electronic.services.line_detection import LineDetectionConfig, _graph_repair_skeleton

    size = 120
    skeleton = np.zeros((size, size), dtype=np.uint8)
    binary = np.zeros_like(skeleton)

    # short segments ending near each other
    cv2.line(skeleton, (20, 20), (30, 30), 1, 1)
    cv2.line(skeleton, (90, 90), (80, 80), 1, 1)
    cv2.line(binary, (20, 20), (30, 30), 255, 3)
    cv2.line(binary, (90, 90), (80, 80), 255, 3)

    # create dotted mask along the path (30,30) -> (80,80)
    general = np.zeros_like(skeleton)
    for t in range(0, 101, 10):
        x = int(30 + (80 - 30) * (t / 100.0))
        y = int(30 + (80 - 30) * (t / 100.0))
        cv2.circle(general, (x, y), 2, 255, -1)

    cfg = LineDetectionConfig(
        dotted_line_graph_repair_enable=True,
        dotted_line_bridge_endpoint_max_distance=200,
        dotted_line_graph_repair_angle_threshold=45.0,
        dotted_line_graph_repair_overlap_fraction=0.2,
        dotted_line_graph_repair_max_joins_per_image=10,
    )

    before = int(skeleton.sum())
    repaired = _graph_repair_skeleton(skeleton.copy(), binary.copy(), general, cfg)
    after = int(repaired.sum())
    assert after > before, "Expected some pixels added to skeleton by graph repair"
