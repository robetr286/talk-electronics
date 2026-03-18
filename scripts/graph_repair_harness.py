"""Small harness for synthetic experiments used by the graph-repair diagnostics.

Provides helpers to build synthetic dotted / broken lines and run the
line-detection pipeline collecting a few useful baseline metrics.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, Sequence, Tuple

import cv2
import numpy as np

from talk_electronic.services.line_detection import (
    LineDetectionConfig,
    SkeletonEngine,
    _detect_dotted_candidates,
    _fast_skeletonize,
    _graph_repair_skeleton,
    _prepare_image,
    detect_lines,
)


def synthetic_dotted_gap_diagonal(size: int = 200, gap_half: int = 6, dot_spacing: int = 5) -> np.ndarray:
    img = np.zeros((size, size), dtype=np.uint8)
    center = size // 2
    # draw diagonal from top-left to bottom-right but leave a central gap
    cv2.line(img, (10, 10), (center - gap_half, center - gap_half), 255, 3)
    cv2.line(img, (center + gap_half, center + gap_half), (size - 10, size - 10), 255, 3)
    # add dotted candidates bridging the central gap
    for i in range(-6, 7):
        cx = center + i * dot_spacing
        cy = center + i * dot_spacing
        cv2.circle(img, (cx, cy), 2, 255, -1)
    return img


def collect_baseline_metrics(image: np.ndarray, config: LineDetectionConfig) -> Dict[str, int]:
    """Run the detection pipeline and collect a few numeric metrics.

    Returns a dict with at minimum: binary_pixels, skeleton_pixels, lines_count.
    """
    # run full pipeline to populate config-dependent behavior
    res = detect_lines(image, binary=False, config=config)

    # Compute skeleton/binary masks using internal helpers so we can also
    # produce repaired vs non-repaired skeletons for comparison if needed.
    prepared = _prepare_image(image, binary=False, config=config)
    engine = SkeletonEngine(config.skeleton_config)
    sk_res = engine.run(prepared)
    binary_mask = (sk_res.binary > 0).astype(np.uint8)
    skeleton_mask = (sk_res.skeleton > 0).astype(np.uint8)

    metrics: Dict[str, int] = {
        "binary_pixels": int(binary_mask.sum()),
        "skeleton_pixels": int(skeleton_mask.sum()),
        "lines_count": len(res.lines) if res and res.lines else 0,
    }
    # endpoints count from detect_lines result nodes
    endpoints = sum(1 for n in res.nodes if len(n.attached_segments) == 1) if res and res.nodes else 0
    metrics["endpoints"] = int(endpoints)
    # component count in binary mask
    num_c, _, _, _ = cv2.connectedComponentsWithStats(binary_mask, connectivity=8)
    # subtract background label
    metrics["components"] = int(max(0, num_c - 1))
    return metrics


def synthetic_continuous_line_at_angle(size: int = 240, angle_deg: float = 0.0) -> np.ndarray:
    """Create a continuous single-line (no gap) at given angle for ground truth."""
    img = np.zeros((size, size), dtype=np.uint8)
    cx = size // 2
    cy = size // 2
    half_len = int(size * 0.45)
    rad = np.deg2rad(angle_deg)
    dx = math.cos(rad)
    dy = math.sin(rad)
    x1 = int(cx + dx * half_len)
    y1 = int(cy + dy * half_len)
    x2 = int(cx - dx * half_len)
    y2 = int(cy - dy * half_len)
    cv2.line(img, (x2, y2), (x1, y1), 255, 3)
    return img


def collect_baseline_metrics_extended(image: np.ndarray, config: LineDetectionConfig) -> Dict[str, int]:
    """Collect extended metrics including endpoints, components, and return skeleton mask info.

    Returns a dict similar to collect_baseline_metrics plus 'endpoints' and 'components'.
    """
    # reuse the standard collector which already computes endpoints and components
    return collect_baseline_metrics(image, config)


def _compute_masks_for_config(
    image: np.ndarray, config: LineDetectionConfig
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (binary_mask, skeleton_mask_before_repair, skeleton_mask_after_repair)

    Both skeleton masks are uint8 0/1 arrays.
    """
    prepared = _prepare_image(image, binary=False, config=config)
    engine = SkeletonEngine(config.skeleton_config)
    sk_res = engine.run(prepared)
    binary_mask = (sk_res.binary > 0).astype(np.uint8)
    skeleton_mask = (sk_res.skeleton > 0).astype(np.uint8)

    # compute repaired skeleton if graph-repair enabled
    if getattr(config, "dotted_line_graph_repair_enable", False):
        img_for_detect = image if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        candidates = _detect_dotted_candidates(img_for_detect, config)
        general = candidates[0] if candidates is not None else None
        repaired = _graph_repair_skeleton(skeleton_mask.copy(), binary_mask.copy(), general, config)
        repaired_mask = (repaired > 0).astype(np.uint8)
    else:
        repaired_mask = skeleton_mask.copy()

    return binary_mask, skeleton_mask, repaired_mask


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    a_bool = (a > 0).astype(np.uint8)
    b_bool = (b > 0).astype(np.uint8)
    inter = int((a_bool & b_bool).sum())
    union = int((a_bool | b_bool).sum())
    if union == 0:
        return 0.0
    return float(inter) / float(union)


if __name__ == "__main__":
    cfg = LineDetectionConfig()
    img = synthetic_dotted_gap_diagonal(300)
    metrics = collect_baseline_metrics(img, cfg)
    print(metrics)


def synthetic_broken_line_at_angle(
    size: int = 240, angle_deg: float = 0.0, gap: int = 12, dot_spacing: int = 6
) -> np.ndarray:
    """Create a synthetic broken line at a given angle with dotted candidates in the gap.

    This produces a grayscale image with a line (thickness 3) that has a centered
    gap and small dot candidates placed in the gap following the same orientation.
    """
    img = np.zeros((size, size), dtype=np.uint8)
    cx = size // 2
    cy = size // 2

    # length from center to border
    half_len = int(size * 0.45)

    # direction vector
    rad = np.deg2rad(angle_deg)
    dx = math.cos(rad)
    dy = math.sin(rad)

    # endpoints of the two halves
    x1 = int(cx + dx * half_len)
    y1 = int(cy + dy * half_len)
    x2 = int(cx - dx * half_len)
    y2 = int(cy - dy * half_len)

    # draw first half up to gap
    gx1 = int(cx + dx * gap)
    gy1 = int(cy + dy * gap)
    gx2 = int(cx - dx * gap)
    gy2 = int(cy - dy * gap)

    cv2.line(img, (x2, y2), (gx2, gy2), 255, 3)
    cv2.line(img, (gx1, gy1), (x1, y1), 255, 3)

    # dotted candidates within the gap
    total_gap = int(math.hypot(gx1 - gx2, gy1 - gy2))
    n = max(3, total_gap // max(1, dot_spacing))
    for i in range(n + 1):
        t = i / max(1, n)
        sx = int(gx2 + (gx1 - gx2) * t)
        sy = int(gy2 + (gy1 - gy2) * t)
        cv2.circle(img, (sx, sy), 2, 255, -1)

    return img


def run_scale_sweep(
    angles: Sequence[float], scales: Sequence[float], *, config_builder: Callable[[bool], LineDetectionConfig]
) -> Dict[Tuple[float, float], Dict[str, int]]:
    """Run detect_lines over combinations of angles and scales.

    Returns a mapping (angle, scale) -> metrics dict.
    The config_builder callable receives a boolean 'enable_graph_repair' flag
    and returns a configured LineDetectionConfig instance.
    """
    results: Dict[Tuple[float, float], Dict[str, int]] = {}
    for angle in angles:
        img = synthetic_broken_line_at_angle(240, angle)
        for scale in scales:
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            scaled = cv2.resize(img, dsize=(0, 0), fx=scale, fy=scale, interpolation=interp)
            # baseline + extended metrics
            cfg_no = config_builder(False)
            cfg_yes = config_builder(True)
            # build ground truth skeleton for IoU comparison
            gt = synthetic_continuous_line_at_angle(size=scaled.shape[0], angle_deg=float(angle))
            gt_skel = _fast_skeletonize((gt > 0).astype(np.uint8) * 255)
            gt_skel = (gt_skel > 0).astype(np.uint8)

            # compute masks and metrics for both configs
            no_bin, no_skel, no_repaired = _compute_masks_for_config(scaled, cfg_no)
            yes_bin, yes_skel, yes_repaired = _compute_masks_for_config(scaled, cfg_yes)

            # use detect_lines for lines_count / attached-nodes based info
            m_no = collect_baseline_metrics(scaled, cfg_no)
            m_yes = collect_baseline_metrics(scaled, cfg_yes)

            # add extended metrics (skeleton IoU wrt ground truth)
            m_no["skeleton_iou_vs_gt"] = _iou(no_skel, gt_skel)
            m_yes["skeleton_iou_vs_gt"] = _iou(yes_repaired, gt_skel)

            # pixel delta and skeleton pixel comparisons
            m_no["skeleton_pixels"] = int(no_skel.sum())
            m_yes["skeleton_pixels"] = int(yes_repaired.sum())
            m_no["skeleton_pixel_delta_vs_gt"] = int(abs(int(no_skel.sum()) - int(gt_skel.sum())))
            m_yes["skeleton_pixel_delta_vs_gt"] = int(abs(int(yes_repaired.sum()) - int(gt_skel.sum())))
            results[(angle, scale)] = {"no_repair": m_no, "with_repair": m_yes}
    return results
