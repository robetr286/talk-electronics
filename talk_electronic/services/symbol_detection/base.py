from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned rectangle in pixel coordinates."""

    x: float
    y: float
    width: float
    height: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.width, self.height)


@dataclass(frozen=True)
class SymbolDetection:
    """Single symbol candidate predicted by a detector."""

    label: str
    score: float
    box: BoundingBox
    rotation: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DetectorSummary:
    """Aggregate statistics returned alongside detections."""

    latency_ms: float
    raw_output: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DetectionResult:
    """Structured output from a detector call."""

    detections: Sequence[SymbolDetection]
    summary: DetectorSummary | None = None


class SymbolDetector:
    """Abstract detector; concrete implementations handle weight loading."""

    name: str = "base"
    version: str = "0"

    def warmup(self) -> None:
        """Prepare heavy resources; called once during app startup."""

    def detect(self, image: np.ndarray, *, return_summary: bool = True) -> DetectionResult:
        raise NotImplementedError

    def unload(self) -> None:
        """Release GPU / CPU resources when shutting down."""

    def labels(self) -> Iterable[str]:
        """Return known label identifiers for UI hints."""
        return []
