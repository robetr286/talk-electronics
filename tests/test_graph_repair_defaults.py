from talk_electronic.services.line_detection import LineDetectionConfig


def test_graph_repair_defaults_are_conservative():
    cfg = LineDetectionConfig()
    # konserwatywne progi po doprecyzowaniu (mniejsze katy + wieksze pokrycie, mniej falszywych polaczen)
    assert cfg.dotted_line_graph_repair_angle_threshold == 12.0
    assert abs(cfg.dotted_line_graph_repair_overlap_fraction - 0.5) < 1e-6
    assert cfg.dotted_line_graph_repair_max_joins_per_image == 10
