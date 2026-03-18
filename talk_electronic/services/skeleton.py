from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

import cv2
import numpy as np

SkeletonArray = np.ndarray


@dataclass(slots=True)
class SkeletonConfig:
    """Konfiguracja procesu generowania szkieletu linii."""

    gaussian_kernel_size: Tuple[int, int] = (3, 3)
    gaussian_sigma: float = 0.0
    use_adaptive_threshold: bool = False
    adaptive_block_size: int = 25
    adaptive_c: int = 5
    binary_threshold: int = 127
    min_component_size: int = 16
    prefer_dark_lines: bool = True
    prune_short_branches: int = 0
    bridge_gaps: bool = True
    extract_contours: bool = False


@dataclass(slots=True)
class SkeletonResult:
    """Efekt działania `SkeletonEngine` wraz z metadanymi."""

    skeleton: SkeletonArray
    binary: SkeletonArray
    metadata: Dict[str, Any] = field(default_factory=dict)


class SkeletonEngine:
    """Odpowiada za sprowadzenie obrazu do jednopikselowego szkieletu."""

    def __init__(self, config: SkeletonConfig | None = None) -> None:
        self._config = config or SkeletonConfig()

    def run(self, image: np.ndarray) -> SkeletonResult:
        if image is None:
            raise ValueError("Parameter 'image' must contain numpy array")

        gray = _ensure_grayscale(image)
        blurred = cv2.GaussianBlur(
            gray,
            self._config.gaussian_kernel_size,
            self._config.gaussian_sigma,
        )

        binary = self._auto_binarize(blurred)
        filtered = _remove_small_components(binary, self._config.min_component_size)
        if self._config.extract_contours:
            extracted = _extract_contour_mask(filtered)
            if extracted.any():
                filtered = extracted
        skeleton = _zhang_suen_thinning(filtered)
        skeleton = _remove_diagonal_spurs(skeleton)
        pruned = _prune_short_branches(skeleton, self._config.prune_short_branches)
        if self._config.bridge_gaps:
            pruned = _bridge_corner_gaps(pruned)

        metadata: Dict[str, Any] = {
            "input_shape": tuple(int(dim) for dim in image.shape),
            "binary_pixels_before": int(binary.sum()),
            "binary_pixels_after": int(filtered.sum()),
            "skeleton_pixels": int(pruned.sum()),
        }

        return SkeletonResult(
            skeleton=(pruned * 255).astype(np.uint8),
            binary=(filtered * 255).astype(np.uint8),
            metadata=metadata,
        )

    def _auto_binarize(self, image: np.ndarray) -> np.ndarray:
        unique = np.unique(image)
        if unique.size <= 2:
            return (image > 0).astype(np.uint8)

        if self._config.use_adaptive_threshold:
            thresholded = cv2.adaptiveThreshold(
                image,
                255,
                cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY,
                self._config.adaptive_block_size,
                self._config.adaptive_c,
            )
        else:
            _, thresholded = cv2.threshold(
                image,
                self._config.binary_threshold,
                255,
                cv2.THRESH_BINARY | cv2.THRESH_OTSU,
            )

        thresholded = thresholded.astype(np.uint8)

        if not self._config.prefer_dark_lines:
            return (thresholded > 0).astype(np.uint8)

        foreground = int(np.count_nonzero(thresholded))
        background = thresholded.size - foreground
        if foreground > background:
            thresholded = cv2.bitwise_not(thresholded)

        return (thresholded > 0).astype(np.uint8)


def _ensure_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    raise ValueError("Unsupported image shape for skeletonization")


def _remove_small_components(image: np.ndarray, min_pixels: int) -> np.ndarray:
    if min_pixels <= 0:
        return image.copy()

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        image.astype(np.uint8),
        connectivity=8,
    )

    filtered = np.zeros_like(image, dtype=np.uint8)
    for label_idx in range(1, num_labels):
        area = stats[label_idx, cv2.CC_STAT_AREA]
        if area >= min_pixels:
            filtered[labels == label_idx] = 1
    return filtered


def _zhang_suen_thinning(image: np.ndarray) -> np.ndarray:
    skeleton = image.copy().astype(np.uint8)
    changed = True

    while changed:
        changed = False
        to_remove: List[Tuple[int, int]] = []

        rows, cols = skeleton.shape
        for step in (0, 1):
            to_remove.clear()
            for row in range(1, rows - 1):
                for col in range(1, cols - 1):
                    if skeleton[row, col] == 0:
                        continue

                    neighbors = _collect_neighbors(skeleton, row, col)
                    transitions = _count_transitions(neighbors)
                    neighbor_sum = sum(neighbors)
                    cardinal_sum = neighbors[0] + neighbors[2] + neighbors[4] + neighbors[6]

                    if cardinal_sum <= 1 and transitions <= 1:
                        continue
                    if not (2 <= neighbor_sum <= 6):
                        continue
                    if transitions != 1:
                        continue

                    if step == 0:
                        if neighbors[0] * neighbors[2] * neighbors[4] != 0:
                            continue
                        if neighbors[2] * neighbors[4] * neighbors[6] != 0:
                            continue
                    else:
                        if neighbors[0] * neighbors[2] * neighbors[6] != 0:
                            continue
                        if neighbors[0] * neighbors[4] * neighbors[6] != 0:
                            continue

                    to_remove.append((row, col))

            if to_remove:
                changed = True
                for row, col in to_remove:
                    skeleton[row, col] = 0

    return skeleton


def _bridge_corner_gaps(image: np.ndarray) -> np.ndarray:
    if image.ndim != 2:
        return image

    working = (image > 0).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(working, cv2.MORPH_CLOSE, kernel)
    if np.array_equal(closed, working):
        return working
    thinned = _zhang_suen_thinning(closed)
    return thinned.astype(np.uint8)


def _collect_neighbors(image: np.ndarray, row: int, col: int) -> List[int]:
    return [
        int(image[row - 1, col]),
        int(image[row - 1, col + 1]),
        int(image[row, col + 1]),
        int(image[row + 1, col + 1]),
        int(image[row + 1, col]),
        int(image[row + 1, col - 1]),
        int(image[row, col - 1]),
        int(image[row - 1, col - 1]),
    ]


def _count_transitions(neighbors: Sequence[int]) -> int:
    transitions = 0
    for idx in range(len(neighbors)):
        current = neighbors[idx]
        nxt = neighbors[(idx + 1) % len(neighbors)]
        if current == 0 and nxt == 1:
            transitions += 1
    return transitions


def _prune_short_branches(image: np.ndarray, max_length: int) -> np.ndarray:
    if max_length <= 0:
        return image.copy()

    skeleton = np.pad(image.astype(np.uint8), 1, mode="constant")
    endpoint_offsets = [
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    ]

    def neighbor_count(r: int, c: int) -> int:
        return sum(1 for dr, dc in endpoint_offsets if skeleton[r + dr, c + dc])

    rows, cols = skeleton.shape
    changed = True
    while changed:
        changed = False
        endpoints: List[Tuple[int, int]] = []
        for row in range(1, rows - 1):
            for col in range(1, cols - 1):
                if skeleton[row, col] == 0:
                    continue
                if neighbor_count(row, col) == 1:
                    endpoints.append((row, col))

        for endpoint in endpoints:
            branch = _trace_branch(skeleton, endpoint)
            if len(branch) - 1 <= max_length:
                for r, c in branch[:-1]:
                    skeleton[r, c] = 0
                end_r, end_c = branch[-1]
                if neighbor_count(end_r, end_c) <= 1:
                    skeleton[end_r, end_c] = 0
                changed = True

    return skeleton[1:-1, 1:-1]


def _remove_diagonal_spurs(image: np.ndarray) -> np.ndarray:
    skeleton = image.copy().astype(np.uint8)
    rows, cols = skeleton.shape

    changed = True
    while changed:
        changed = False
        to_remove: List[Tuple[int, int]] = []
        for row in range(1, rows - 1):
            for col in range(1, cols - 1):
                if skeleton[row, col] == 0:
                    continue

                neighbors = _collect_neighbors(skeleton, row, col)
                cardinal_sum = neighbors[0] + neighbors[2] + neighbors[4] + neighbors[6]
                total_sum = sum(neighbors)

                if cardinal_sum <= 1 and total_sum > cardinal_sum and total_sum >= 3:
                    to_remove.append((row, col))

        if to_remove:
            changed = True
            for row, col in to_remove:
                skeleton[row, col] = 0

    return skeleton


def _extract_contour_mask(image: np.ndarray) -> np.ndarray:
    if image.ndim != 2:
        return image.copy()

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    eroded = cv2.erode(image.astype(np.uint8), kernel)
    contour = cv2.subtract(image.astype(np.uint8), eroded)
    return (contour > 0).astype(np.uint8)


def _trace_branch(image: np.ndarray, start: Tuple[int, int]) -> List[Tuple[int, int]]:
    offsets = [
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    ]

    path: List[Tuple[int, int]] = [start]
    previous = start
    current = start

    max_row, max_col = image.shape

    while True:
        neighbors = [
            (current[0] + dr, current[1] + dc)
            for dr, dc in offsets
            if 0 <= current[0] + dr < max_row
            and 0 <= current[1] + dc < max_col
            and image[current[0] + dr, current[1] + dc]
        ]

        neighbors = [point for point in neighbors if point != previous]
        if not neighbors:
            break

        next_point = neighbors[0]
        path.append(next_point)

        degree = sum(
            1
            for dr, dc in offsets
            if 0 <= next_point[0] + dr < max_row
            and 0 <= next_point[1] + dc < max_col
            and image[next_point[0] + dr, next_point[1] + dc]
        )
        if degree != 2:
            break

        previous = current
        current = next_point

    return path
