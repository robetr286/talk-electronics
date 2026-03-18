from __future__ import annotations

import numpy as np
import pytest

from talk_electronic.services.symbol_detection.base import DetectionResult, SymbolDetector
from talk_electronic.services.symbol_detection.noop import NoOpSymbolDetector
from talk_electronic.services.symbol_detection.registry import DetectorRegistry


class SampleDetector(SymbolDetector):
    """Test double to check registry interactions."""

    def __init__(self) -> None:
        self.warmup_called = False

    def warmup(self) -> None:
        self.warmup_called = True

    def detect(self, image: np.ndarray, *, return_summary: bool = True) -> DetectionResult:  # noqa: ARG002
        return DetectionResult(detections=())


def test_register_and_create_invokes_warmup() -> None:
    registry = DetectorRegistry()
    registry.register("sample", SampleDetector)

    detector = registry.create("SAMPLE")

    assert isinstance(detector, SampleDetector)
    assert detector.warmup_called is True


def test_register_prevents_duplicates() -> None:
    registry = DetectorRegistry()
    registry.register("sample", SampleDetector)

    with pytest.raises(ValueError):
        registry.register("Sample", SampleDetector)


def test_create_requires_existing_detector() -> None:
    registry = DetectorRegistry()

    with pytest.raises(KeyError):
        registry.create("missing")


def test_available_returns_sorted_names() -> None:
    registry = DetectorRegistry()
    registry.register("beta", SampleDetector)
    registry.register("alpha", SampleDetector)

    assert tuple(registry.available()) == ("alpha", "beta")


def test_noop_detector_returns_empty_result() -> None:
    detector = NoOpSymbolDetector()
    image = np.zeros((8, 16, 3), dtype=np.uint8)

    result = detector.detect(image)

    assert result.detections == ()
    assert result.summary is not None
    assert result.summary.raw_output == {"shape": (8, 16)}
    assert result.summary.latency_ms >= 0.0
