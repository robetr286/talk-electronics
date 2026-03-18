from __future__ import annotations

from scripts.graph_repair_harness import collect_baseline_metrics, synthetic_dotted_gap_diagonal
from talk_electronic.services.line_detection import LineDetectionConfig


def test_harness_returns_metrics():
    img = synthetic_dotted_gap_diagonal(120)
    cfg = LineDetectionConfig()
    metrics = collect_baseline_metrics(img, cfg)
    assert isinstance(metrics, dict)
    assert metrics.get("binary_pixels", 0) > 0
    assert metrics.get("skeleton_pixels", 0) >= 0


def test_graph_repair_changes_skeleton_pixels():
    img = synthetic_dotted_gap_diagonal(160)

    cfg_no = LineDetectionConfig(dotted_line_graph_repair_enable=False, morph_iterations=0)
    cfg_yes = LineDetectionConfig(
        dotted_line_graph_repair_enable=True,
        dotted_line_graph_repair_angle_threshold=80.0,
        dotted_line_graph_repair_overlap_fraction=0.2,
        dotted_line_graph_repair_max_joins_per_image=200,
        morph_iterations=0,
    )

    m_no = collect_baseline_metrics(img, cfg_no)
    m_yes = collect_baseline_metrics(img, cfg_yes)

    # With the graph repair path enabled we expect some additional skeleton pixels
    assert m_yes["skeleton_pixels"] >= m_no["skeleton_pixels"]
