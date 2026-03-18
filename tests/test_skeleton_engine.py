from __future__ import annotations

import numpy as np

from talk_electronic.services.skeleton import SkeletonConfig, SkeletonEngine

OFFSETS = [
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
]


def _neighbor_count(skeleton: np.ndarray, row: int, col: int) -> int:
    return sum(1 for dr, dc in OFFSETS if skeleton[row + dr, col + dc])


def test_cross_thinning_produces_single_pixel_arms():
    image = np.zeros((13, 13), dtype=np.uint8)
    image[2:11, 5:8] = 255
    image[5:8, 2:11] = 255

    engine = SkeletonEngine(SkeletonConfig(min_component_size=1, prune_short_branches=0))
    result = engine.run(image)
    skeleton = (result.skeleton > 0).astype(np.uint8)

    assert skeleton.sum() > 0, "Skeleton should contain the cross"

    endpoints: list[tuple[int, int]] = []
    junctions: list[tuple[int, int]] = []
    for row in range(1, skeleton.shape[0] - 1):
        for col in range(1, skeleton.shape[1] - 1):
            if skeleton[row, col] == 0:
                continue
            degree = _neighbor_count(skeleton, row, col)
            if degree == 1:
                endpoints.append((row, col))
            elif degree >= 3:
                junctions.append((row, col))

    assert len(endpoints) == 4, "Expected four endpoints for the cross"
    assert junctions, "Expected a central junction with degree >= 3"


def test_stub_branch_is_removed_during_pruning():
    image = np.zeros((21, 21), dtype=np.uint8)
    image[9:12, 3:18] = 255
    image[6:10, 10:13] = 255

    engine = SkeletonEngine(SkeletonConfig(min_component_size=1, prune_short_branches=2))
    result = engine.run(image)
    skeleton = (result.skeleton > 0).astype(np.uint8)

    assert skeleton.sum() > 0, "Skeleton should retain the main line"
    unique_rows = np.unique(np.argwhere(skeleton)[:, 0])
    assert np.array_equal(unique_rows, np.array([10])), "All pixels should lie on the main horizontal line"


def test_auto_binarization_detects_dark_lines_on_light_background():
    image = np.full((32, 32), 255, dtype=np.uint8)
    image[:, 14:18] = 0

    engine = SkeletonEngine()
    result = engine.run(image)

    skeleton = (result.skeleton > 0).astype(np.uint8)
    assert skeleton.sum() > 0, "Expected skeleton to contain detected line"
    assert skeleton[:, 14:18].sum() > 0, "Skeleton should follow the dark stripe"
