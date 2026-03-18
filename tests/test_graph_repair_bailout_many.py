import cv2
import numpy as np

from talk_electronic.services.line_detection import LineDetectionConfig, _graph_repair_skeleton


def test_graph_repair_bails_for_large_node_counts():
    size = 800
    skeleton = np.zeros((size, size), dtype=np.uint8)
    binary = np.zeros_like(skeleton)

    # create many small short segments scattered to generate many nodes
    count = 40
    for i in range(count):
        x = 10 + (i * 15) % (size - 30)
        y = 10 + ((i * 7) % (size - 30))
        cv2.line(skeleton, (x, y), (x + 6, y), 1, 1)
        cv2.line(binary, (x, y), (x + 6, y), 255, 2)

    # build a trivial general mask (won't matter because bail is triggered)
    general = np.zeros_like(skeleton)

    cfg = LineDetectionConfig(
        dotted_line_graph_repair_enable=True,
        dotted_line_graph_repair_max_nodes=20,  # nodes (≈40) exceed this -> bail
        dotted_line_graph_repair_angle_threshold=30.0,
        dotted_line_graph_repair_overlap_fraction=0.2,
        dotted_line_graph_repair_max_joins_per_image=50,
    )

    before = int(skeleton.sum())
    after = int(_graph_repair_skeleton(skeleton.copy(), binary.copy(), general, cfg).sum())
    assert after == before, "Expected graph-repair to skip when nodes count exceeds threshold"
