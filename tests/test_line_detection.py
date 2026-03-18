from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np

from talk_electronic.services.line_detection import (
    LineDetectionConfig,
    LineNode,
    LineSegment,
    _merge_straight_chains,
    _prune_textual_spurs,
    _score_segments,
    _should_remove_endpoint,
    detect_lines,
)
from talk_electronic.services.skeleton import SkeletonConfig


def _draw_cross_image(size: int = 160, thickness: int = 5) -> np.ndarray:
    image = np.zeros((size, size), dtype=np.uint8)
    center = size // 2
    cv2.line(image, (20, center), (size - 20, center), 255, thickness)
    cv2.line(image, (center, 20), (center, size - 20), 255, thickness)
    return image


def _draw_stub_image(width: int = 200, height: int = 160) -> np.ndarray:
    image = np.zeros((height, width), dtype=np.uint8)
    mid_y = height // 2
    cv2.line(image, (20, mid_y), (width - 20, mid_y), 255, 5)
    cv2.line(image, (width // 2, mid_y - 3), (width // 2, mid_y - 25), 255, 5)
    return image


def _draw_square_image(size: int = 200, inset: int = 40, thickness: int = 4) -> np.ndarray:
    image = np.zeros((size, size), dtype=np.uint8)
    top_left = (inset, inset)
    bottom_right = (size - inset, size - inset)
    cv2.rectangle(image, top_left, bottom_right, 255, thickness)
    return image


def _draw_triangle_image(size: int = 240, inset: int = 40) -> np.ndarray:
    image = np.zeros((size, size), dtype=np.uint8)
    points = np.array(
        [
            [size // 2, inset],
            [size - inset, size - inset],
            [inset, size - inset],
        ]
    )
    cv2.fillPoly(image, [points], 255)
    return image


def _build_endpoint_thresholds(min_edge_length: float, node_merge_tolerance: float) -> dict[str, float]:
    sample_radius = int(round(max(node_merge_tolerance * 2.8, min_edge_length * 0.9, 12.0)))
    return {
        "area_dense": float(max(140.0, min_edge_length * min_edge_length * 0.9)),
        "ink_dense": 0.28,
        "fill_dense": 0.56,
        "aspect_dense": 2.7,
        "skeleton_min": 0.019,
        "area_cluster": float(max(110.0, min_edge_length * min_edge_length * 0.7)),
        "ink_cluster": 0.24,
        "fill_cluster": 0.52,
        "neighbor_radius": float(sample_radius * 0.9),
        "area_local": float(max(90.0, min_edge_length * min_edge_length * 0.6)),
        "ink_local": 0.26,
        "aspect_local": 2.3,
        "density_margin": 0.11,
    }


def test_detect_lines_builds_graph_for_cross_shape():
    image = _draw_cross_image()
    cfg = LineDetectionConfig(
        gaussian_kernel_size=(3, 3),
        gaussian_sigma=0.0,
        morph_iterations=0,
        skeleton_config=SkeletonConfig(prune_short_branches=2),
        min_edge_length=12.0,
    )

    result = detect_lines(image, binary=False, config=cfg)

    assert len(result.lines) == 4, "Expected four edges for the cross"
    assert len(result.nodes) == 5, "Expected central junction plus four endpoints"

    degrees = {node.id: len(node.attached_segments) for node in result.nodes}
    assert any(value >= 4 for value in degrees.values()), "Central node should have degree >= 4"
    classifications = {node.classification for node in result.nodes}
    assert "essential" in classifications, "Central node should be tagged as essential"
    assert sum(1 for node in result.nodes if node.classification == "endpoint") == 4
    assert result.metadata["merged_segments"] == len(result.lines)
    assert result.metadata["nodes"] == len(result.nodes)
    node_stats = result.metadata.get("node_classification", {})
    assert node_stats.get("essential") == 1
    assert node_stats.get("endpoints") == 4
    confidence = result.metadata.get("confidence", {})
    assert confidence.get("low_confidence") == []
    assert all(segment.confidence_label in {"high", "medium"} for segment in result.lines)

    for segment in result.lines:
        dx = segment.end[0] - segment.start[0]
        dy = segment.end[1] - segment.start[1]
        length = math.hypot(dx, dy)
        assert length >= cfg.min_edge_length


def test_detect_lines_removes_short_stub_branch():
    image = _draw_stub_image()
    cfg = LineDetectionConfig(
        gaussian_kernel_size=(5, 5),
        gaussian_sigma=0.0,
        morph_iterations=0,
        skeleton_config=SkeletonConfig(prune_short_branches=30),
        min_edge_length=20.0,
    )

    result = detect_lines(image, binary=False, config=cfg)

    assert len(result.lines) <= 2, "Short stub should not create an extra edge"
    degrees = {node.id: len(node.attached_segments) for node in result.nodes}
    assert sum(1 for degree in degrees.values() if degree == 1) == 2, "Only two endpoint nodes should remain"
    assert all(node.classification == "endpoint" for node in result.nodes), "Remaining nodes should be endpoints"
    node_positions = [node.position for node in result.nodes]
    mid_y = image.shape[0] // 2
    assert all(abs(y - mid_y) <= 2 for _, y in node_positions), "All nodes should lie on the original horizontal axis"
    assert all(abs(segment.angle_deg) < 15 or abs(abs(segment.angle_deg) - 180) < 15 for segment in result.lines)
    confidence = result.metadata.get("confidence", {})
    assert isinstance(confidence.get("high_confidence", []), list)
    assert isinstance(confidence.get("low_confidence", []), list)


def test_detect_lines_detects_square_loop():
    image = _draw_square_image()
    cfg = LineDetectionConfig(
        gaussian_kernel_size=(3, 3),
        gaussian_sigma=0.0,
        morph_iterations=0,
        skeleton_config=SkeletonConfig(bridge_gaps=True),
        min_edge_length=40.0,
    )

    result = detect_lines(image, binary=False, config=cfg)

    assert len(result.lines) == 4, "Expected four edges for square contour"
    assert len(result.nodes) == 4, "Square contour should produce four corner nodes"

    for node in result.nodes:
        assert len(node.attached_segments) == 2, "Each corner should connect exactly two segments"
        assert node.classification == "non_essential"

    xs = sorted(node.position[0] for node in result.nodes)
    ys = sorted(node.position[1] for node in result.nodes)
    assert xs[0] < xs[-1] and ys[0] < ys[-1], "Corner nodes should span square extents"


def test_detect_lines_detects_triangle_contour():
    image = _draw_triangle_image()
    cfg = LineDetectionConfig(
        gaussian_kernel_size=(3, 3),
        gaussian_sigma=0.0,
        morph_iterations=0,
        skeleton_config=SkeletonConfig(bridge_gaps=True, extract_contours=True),
        min_edge_length=50.0,
    )

    result = detect_lines(image, binary=False, config=cfg)

    assert len(result.lines) == 3, "Expected three edges for triangle contour"
    assert len(result.nodes) == 3, "Triangle contour should produce three corner nodes"

    for node in result.nodes:
        assert len(node.attached_segments) == 2, "Each corner should connect two edges"
        assert node.classification == "non_essential"

    angles = sorted(round(seg.angle_deg) % 180 for seg in result.lines)
    assert len(angles) == 3 and len(set(angles)) == 3, "Triangle edges should have distinct orientations"


def test_detect_lines_handles_empty_image():
    image = np.zeros((64, 64), dtype=np.uint8)

    result = detect_lines(image)

    assert result.lines == []
    assert result.nodes == []
    assert result.metadata["merged_segments"] == 0
    assert result.metadata["nodes"] == 0


def test_prune_textual_spurs_removes_dense_stub():
    main_start = (10, 32)
    junction = (54, 32)
    stub_end = (58, 20)

    main_length = math.hypot(junction[0] - main_start[0], junction[1] - main_start[1])
    stub_length = math.hypot(stub_end[0] - junction[0], stub_end[1] - junction[1])

    segments = [
        LineSegment(id="edge-0", start=main_start, end=junction, length=main_length, angle_deg=0.0),
        LineSegment(id="edge-1", start=junction, end=stub_end, length=stub_length, angle_deg=60.0),
    ]
    nodes = [
        LineNode(id="node-0", position=main_start, attached_segments=["edge-0"]),
        LineNode(id="node-1", position=junction, attached_segments=["edge-0", "edge-1"]),
        LineNode(id="node-2", position=stub_end, attached_segments=["edge-1"]),
    ]

    binary_mask = np.zeros((72, 72), dtype=np.uint8)
    skeleton_mask = np.zeros_like(binary_mask)
    cv2.line(binary_mask, main_start, junction, 255, 5)
    cv2.line(binary_mask, junction, stub_end, 255, 5)
    cv2.rectangle(binary_mask, (stub_end[0] - 4, stub_end[1] - 10), (stub_end[0] + 8, stub_end[1] + 2), 255, -1)
    cv2.line(skeleton_mask, main_start, junction, 255, 1)
    cv2.line(skeleton_mask, junction, stub_end, 255, 1)

    filtered_segments, filtered_nodes = _prune_textual_spurs(
        segments,
        nodes,
        binary_mask=binary_mask,
        skeleton_mask=skeleton_mask,
        contour_candidates=[],
        node_merge_tolerance=4.0,
        min_edge_length=8.0,
    )

    assert len(filtered_segments) == 1, "Dense stub should be removed"
    assert len(filtered_nodes) == 2, "Only main line endpoints should remain"
    remaining_segment = filtered_segments[0]
    assert remaining_segment.start in (main_start, junction)
    assert remaining_segment.end in (main_start, junction)


def test_merge_straight_chains_reduces_jitter_node():
    left = (10, 30)
    middle = (30, 30)
    right = (50, 31)

    seg_left = LineSegment(
        id="edge-0",
        start=left,
        end=middle,
        length=math.hypot(middle[0] - left[0], middle[1] - left[1]),
        angle_deg=0.0,
    )
    seg_right = LineSegment(
        id="edge-1",
        start=middle,
        end=right,
        length=math.hypot(right[0] - middle[0], right[1] - middle[1]),
        angle_deg=0.0,
    )

    nodes = [
        LineNode(id="node-0", position=left, attached_segments=["edge-0"]),
        LineNode(id="node-1", position=middle, attached_segments=["edge-0", "edge-1"]),
        LineNode(id="node-2", position=right, attached_segments=["edge-1"]),
    ]

    merged_segments, merged_nodes = _merge_straight_chains(
        [seg_left, seg_right],
        nodes,
        contour_candidates=[],
        node_merge_tolerance=4.0,
        min_edge_length=8.0,
    )

    assert len(merged_segments) == 1, "Nearly colinear edges should merge"
    assert len(merged_nodes) == 2, "Intermediate jitter node should disappear"
    merged = merged_segments[0]
    assert merged.start in (left, right)
    assert merged.end in (left, right)


def test_score_segments_flags_short_endpoint():
    short_segment = LineSegment(
        id="edge-short",
        start=(0, 0),
        end=(6, 0),
        length=6.0,
        angle_deg=0.0,
    )
    long_segment = LineSegment(
        id="edge-long",
        start=(0, 0),
        end=(50, 0),
        length=50.0,
        angle_deg=0.0,
    )
    nodes = [
        LineNode(
            id="node-0", position=(0, 0), attached_segments=["edge-short", "edge-long"], classification="essential"
        ),
        LineNode(id="node-1", position=(50, 0), attached_segments=["edge-long"], classification="endpoint"),
        LineNode(id="node-2", position=(6, 0), attached_segments=["edge-short"], classification="endpoint"),
    ]

    summary = _score_segments([short_segment, long_segment], nodes, min_edge_length=15.0)

    assert "edge-short" in summary["low_confidence"], "Short spur should be marked as low confidence"
    assert "edge-long" in summary["high_confidence"], "Long edge should retain high confidence"
    low_entry = summary["scores"]["edge-short"]
    assert low_entry["label"] == "low"
    assert any(reason in {"short_segment", "isolated_branch"} for reason in low_entry["reasons"])


def test_false_endpoint_samples_flagged():
    fixture_path = Path(__file__).parent / "fixtures" / "false_endpoints_sample.json"
    samples = json.loads(fixture_path.read_text(encoding="utf-8"))

    thresholds = _build_endpoint_thresholds(min_edge_length=8.0, node_merge_tolerance=4.0)
    reasons: set[str] = set()

    for sample in samples:
        decision, reason = _should_remove_endpoint(sample, thresholds, float(sample["short_branch_limit"]))
        assert decision, f"Expected removal for {sample['segment_id']} ({sample['source_id']})"
        reasons.add(reason)

    assert "dense_pair" in reasons


def test_text_cluster_samples_flagged_as_text_pair():
    fixture_path = Path(__file__).parent / "fixtures" / "false_endpoints_text_clusters.json"
    samples = json.loads(fixture_path.read_text(encoding="utf-8"))

    thresholds = _build_endpoint_thresholds(min_edge_length=8.0, node_merge_tolerance=4.0)

    for sample in samples:
        decision, reason = _should_remove_endpoint(sample, thresholds, float(sample["short_branch_limit"]))
        assert decision, f"Expected removal for {sample['segment_id']} ({sample['source_id']})"
        assert reason == "text_pair", f"Expected text_pair for sample {sample['segment_id']}, got {reason}"
