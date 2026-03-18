from __future__ import annotations

from time import perf_counter

import cv2
import numpy as np

from .base import BoundingBox, DetectionResult, DetectorSummary, SymbolDetection, SymbolDetector


class SimpleThresholdDetector(SymbolDetector):
    """Lightweight detector that extracts high-contrast blobs as symbol candidates."""

    name = "simple"
    version = "1"

    def __init__(self) -> None:
        self._min_area = 64
        self._max_candidates = 64

    def detect(
        self, image: np.ndarray, *, return_summary: bool = True
    ) -> DetectionResult:  # noqa: C901 - compact pipeline
        start_ts = perf_counter()

        if image is None or image.size == 0:
            return DetectionResult(detections=(), summary=self._build_summary(start_ts, return_summary, 0, 0))

        if image.ndim == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif image.ndim == 3 and image.shape[2] == 4:
            gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        else:
            gray = image.copy()

        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

        image_area = float(image.shape[0] * image.shape[1]) if image.ndim >= 2 else 1.0
        detections: list[SymbolDetection] = []

        for index in range(1, num_labels):
            area = stats[index, cv2.CC_STAT_AREA]
            if area < self._min_area or area >= image_area * 0.8:
                continue

            width = stats[index, cv2.CC_STAT_WIDTH]
            height = stats[index, cv2.CC_STAT_HEIGHT]
            if width < 4 or height < 4:
                continue

            left = stats[index, cv2.CC_STAT_LEFT]
            top = stats[index, cv2.CC_STAT_TOP]
            box = BoundingBox(float(left), float(top), float(width), float(height))

            # Normalize score based on area and aspect ratio closeness to 1
            normalized_area = min(1.0, float(area) / max(image_area, 1.0))
            aspect_ratio = width / height if height else 1.0
            deviation = abs(np.log(aspect_ratio))
            score = max(0.05, 1.0 - deviation) * (0.5 + normalized_area)
            score = min(score, 0.99)

            centroid = centroids[index]
            detection = SymbolDetection(
                label="component",
                score=float(score),
                box=box,
                rotation=0.0,
                metadata={
                    "area": float(area),
                    "centroid": [float(centroid[0]), float(centroid[1])],
                    "aspect_ratio": float(aspect_ratio),
                },
            )
            detections.append(detection)
            if len(detections) >= self._max_candidates:
                break

        summary = self._build_summary(start_ts, return_summary, num_labels - 1, len(detections))
        return DetectionResult(detections=detections, summary=summary)

    def _build_summary(
        self,
        start_ts: float,
        return_summary: bool,
        inspected: int,
        emitted: int,
    ) -> DetectorSummary | None:
        if not return_summary:
            return None
        return DetectorSummary(
            latency_ms=(perf_counter() - start_ts) * 1000.0,
            raw_output={
                "components": inspected,
                "emitted": emitted,
            },
        )
