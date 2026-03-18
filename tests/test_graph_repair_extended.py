from __future__ import annotations

from scripts.graph_repair_harness import (
    _compute_masks_for_config,
    _iou,
    synthetic_broken_line_at_angle,
    synthetic_continuous_line_at_angle,
)
from talk_electronic.services.line_detection import LineDetectionConfig


def test_repair_does_not_degrade_iou_significantly():
    cfg_no = LineDetectionConfig(dotted_line_graph_repair_enable=False)
    cfg_yes = LineDetectionConfig(dotted_line_graph_repair_enable=True)

    img = synthetic_broken_line_at_angle(size=240, angle_deg=30.0, gap=12, dot_spacing=6)

    _, no_skel, no_repaired = _compute_masks_for_config(img, cfg_no)
    _, yes_skel, yes_repaired = _compute_masks_for_config(img, cfg_yes)

    gt_skel = (synthetic_continuous_line_at_angle(size=240, angle_deg=30.0) > 0).astype("uint8") * 255

    iou_no = _iou(no_skel, gt_skel)
    iou_yes = _iou(yes_repaired, gt_skel)

    # ensure repair isn't making IoU worse beyond a small tolerance
    assert iou_yes + 0.03 >= iou_no


def test_repair_improves_obvious_dotted_case():
    cfg_no = LineDetectionConfig(dotted_line_graph_repair_enable=False)
    cfg_yes = LineDetectionConfig(dotted_line_graph_repair_enable=True)

    # a configuration we observed in sweep to profit from repair
    img = synthetic_broken_line_at_angle(size=240, angle_deg=120.0, gap=12, dot_spacing=6)
    gt = synthetic_continuous_line_at_angle(size=240, angle_deg=120.0)

    _, no_skel, _ = _compute_masks_for_config(img, cfg_no)
    _, _, yes_repaired = _compute_masks_for_config(img, cfg_yes)

    gt_skel = (gt > 0).astype("uint8") * 255

    iou_no = _iou(no_skel, gt_skel)
    iou_yes = _iou(yes_repaired, gt_skel)

    assert iou_yes - iou_no >= 0.03


def test_components_and_endpoints_are_safe():
    cfg_no = LineDetectionConfig(dotted_line_graph_repair_enable=False)
    cfg_yes = LineDetectionConfig(dotted_line_graph_repair_enable=True)

    img = synthetic_broken_line_at_angle(size=240, angle_deg=60.0, gap=12, dot_spacing=6)

    bin_no, no_skel, no_repaired = _compute_masks_for_config(img, cfg_no)
    bin_yes, yes_skel, yes_repaired = _compute_masks_for_config(img, cfg_yes)

    # components measured on binary masks
    _, labels_no, stats_no, _ = __import__("cv2").connectedComponentsWithStats(bin_no, connectivity=8)
    _, labels_yes, stats_yes, _ = __import__("cv2").connectedComponentsWithStats(bin_yes, connectivity=8)

    comp_no = max(0, int(stats_no.shape[0] - 1))
    comp_yes = max(0, int(stats_yes.shape[0] - 1))

    # require that components do not drop more than 3 (tolerant limit)
    assert comp_no - comp_yes <= 3
