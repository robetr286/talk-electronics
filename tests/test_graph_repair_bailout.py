import cv2
import numpy as np

from talk_electronic.services.line_detection import LineDetectionConfig, _graph_repair_skeleton


def test_graph_repair_bails_when_nodes_exceed_max():
    size = 120
    skeleton = np.zeros((size, size), dtype=np.uint8)
    binary = np.zeros_like(skeleton)

    # two short segments (two endpoints) - normally would be joined
    cv2.line(skeleton, (20, 20), (30, 30), 1, 1)
    cv2.line(skeleton, (90, 90), (80, 80), 1, 1)
    cv2.line(binary, (20, 20), (30, 30), 255, 3)
    cv2.line(binary, (90, 90), (80, 80), 255, 3)

    # dotted general mask along the connecting path
    general = np.zeros_like(skeleton)
    for t in range(0, 101, 10):
        x = int(30 + (80 - 30) * (t / 100.0))
        y = int(30 + (80 - 30) * (t / 100.0))
        cv2.circle(general, (x, y), 2, 255, -1)

    cfg = LineDetectionConfig(
        dotted_line_graph_repair_enable=True,
        dotted_line_graph_repair_max_nodes=1,  # force bailout (nodes = 2 > 1)
        dotted_line_graph_repair_angle_threshold=45.0,
        dotted_line_graph_repair_overlap_fraction=0.0,
        dotted_line_graph_repair_max_joins_per_image=10,
    )

    before = int(skeleton.sum())
    after = int(_graph_repair_skeleton(skeleton.copy(), binary.copy(), general, cfg).sum())
    assert after == before, "Expected graph-repair to skip (bailout) when nodes exceed max_nodes"
