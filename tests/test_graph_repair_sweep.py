from __future__ import annotations

from scripts.graph_repair_harness import run_scale_sweep
from talk_electronic.services.line_detection import LineDetectionConfig


def test_run_scale_sweep_basic():
    angles = [0.0, 45.0]
    scales = [1.0, 1.5]

    def builder(enable: bool) -> LineDetectionConfig:
        return LineDetectionConfig(dotted_line_graph_repair_enable=enable)

    results = run_scale_sweep(angles, scales, config_builder=builder)
    assert len(results) == len(angles) * len(scales)
    for key, value in results.items():
        assert "no_repair" in value and "with_repair" in value
        assert isinstance(value["no_repair"], dict)
        assert isinstance(value["with_repair"], dict)
