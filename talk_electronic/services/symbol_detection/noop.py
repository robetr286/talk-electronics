from __future__ import annotations

from time import perf_counter

import numpy as np

from .base import DetectionResult, DetectorSummary, SymbolDetector


class NoOpSymbolDetector(SymbolDetector):
    """Fallback detector returning no predictions."""

    name = "noop"
    version = "1"

    def detect(self, image: np.ndarray, *, return_summary: bool = True) -> DetectionResult:
        start = perf_counter()
        height, width = image.shape[:2]
        summary = None
        if return_summary:
            elapsed = (perf_counter() - start) * 1000.0
            summary = DetectorSummary(latency_ms=elapsed, raw_output={"shape": (height, width)})
        return DetectionResult(detections=(), summary=summary)
