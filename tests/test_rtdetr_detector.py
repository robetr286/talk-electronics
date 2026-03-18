"""Unit tests for RTDETRDetector (A.4.1).

Tests cover:
  - Import
  - Registry registration
  - Labels
  - Detection with mocked model
  - Empty / null image handling
  - Weight resolution
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from talk_electronic.services.symbol_detection.base import (
    DetectionResult,
    SymbolDetection,
)
from talk_electronic.services.symbol_detection.registry import (
    available_detectors,
)
from talk_electronic.services.symbol_detection.rtdetr import RTDETRDetector


# ------------------------------------------------------------------ #
# A.4.1-a  test_rtdetr_importable
# ------------------------------------------------------------------ #

class TestRTDETRImportable:
    def test_class_exists(self) -> None:
        assert RTDETRDetector is not None

    def test_is_subclass_of_symbol_detector(self) -> None:
        from talk_electronic.services.symbol_detection.base import SymbolDetector
        assert issubclass(RTDETRDetector, SymbolDetector)

    def test_name_attribute(self) -> None:
        assert RTDETRDetector.name == "rtdetr"

    def test_version_attribute(self) -> None:
        assert RTDETRDetector.version == "L-v1"


# ------------------------------------------------------------------ #
# A.4.1-b  test_rtdetr_registered_in_registry
# ------------------------------------------------------------------ #

class TestRTDETRRegistered:
    @pytest.fixture(autouse=True)
    def _create_app(self) -> None:
        """Call create_app() once to populate the global detector registry."""
        from talk_electronic import create_app
        create_app({"TESTING": True})

    def test_rtdetr_in_available_detectors(self) -> None:
        names = tuple(available_detectors())
        assert "rtdetr" in names

    def test_all_five_detectors_present(self) -> None:
        names = set(available_detectors())
        expected = {"noop", "rtdetr", "simple", "template_matching", "yolov8"}
        assert expected.issubset(names)


# ------------------------------------------------------------------ #
# A.4.1-c  test_rtdetr_labels
# ------------------------------------------------------------------ #

class TestRTDETRLabels:
    def test_labels_default_before_warmup(self) -> None:
        detector = RTDETRDetector.__new__(RTDETRDetector)
        detector._names = ()
        # Before warmup, labels() returns the raw tuple
        assert tuple(detector.labels()) == ()

    def test_labels_returns_names_after_warmup(self) -> None:
        detector = RTDETRDetector.__new__(RTDETRDetector)
        detector._names = ("resistor", "capacitor", "inductor", "diode")
        assert tuple(detector.labels()) == ("resistor", "capacitor", "inductor", "diode")


# ------------------------------------------------------------------ #
# Helpers  — build fake Ultralytics result
# ------------------------------------------------------------------ #

def _make_fake_result(n: int = 3) -> SimpleNamespace:
    """Create a fake Ultralytics result object with *n* detections."""
    import torch

    xywh = torch.tensor([[100.0, 200.0, 50.0, 60.0]] * n, dtype=torch.float32)
    conf = torch.tensor([0.9] * n, dtype=torch.float32)
    cls = torch.tensor([0] * n, dtype=torch.float32)

    boxes = SimpleNamespace(xywh=xywh, conf=conf, cls=cls)
    speed = {"preprocess": 0.1, "inference": 35.0, "postprocess": 1.0}

    return SimpleNamespace(boxes=boxes, speed=speed)


def _make_empty_result() -> SimpleNamespace:
    """Result with no detections."""
    import torch

    xywh = torch.zeros((0, 4), dtype=torch.float32)
    conf = torch.zeros((0,), dtype=torch.float32)
    cls = torch.zeros((0,), dtype=torch.float32)

    boxes = SimpleNamespace(xywh=xywh, conf=conf, cls=cls)
    return SimpleNamespace(boxes=boxes, speed={})


# ------------------------------------------------------------------ #
# A.4.1-d  test_rtdetr_detect_returns_detection_result (mocked)
# ------------------------------------------------------------------ #

class TestRTDETRDetect:
    @pytest.fixture()
    def detector(self) -> RTDETRDetector:
        """Return a detector with mocked model (no actual weights)."""
        det = RTDETRDetector.__new__(RTDETRDetector)
        det._conf = 0.35
        det._iou = 0.55
        det._imgsz = 640
        det._max_det = 300
        det._names = ("resistor", "capacitor", "inductor", "diode")
        det._resolved_weights = Path("/fake/rtdetr_best.pt")
        det._device = "cpu"

        mock_model = MagicMock()
        mock_model.predict.return_value = [_make_fake_result(3)]
        mock_model.names = {0: "resistor", 1: "capacitor", 2: "inductor", 3: "diode"}
        det._model = mock_model
        return det

    def test_returns_detection_result(self, detector: RTDETRDetector) -> None:
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(image)
        assert isinstance(result, DetectionResult)

    def test_detections_count(self, detector: RTDETRDetector) -> None:
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(image)
        assert len(result.detections) == 3

    def test_detection_fields(self, detector: RTDETRDetector) -> None:
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(image)
        det = result.detections[0]
        assert isinstance(det, SymbolDetection)
        assert det.label == "resistor"
        assert det.score == pytest.approx(0.9)
        assert det.box.width > 0
        assert det.box.height > 0

    def test_summary_present(self, detector: RTDETRDetector) -> None:
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(image, return_summary=True)
        assert result.summary is not None
        assert result.summary.latency_ms >= 0

    def test_summary_absent_when_disabled(self, detector: RTDETRDetector) -> None:
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(image, return_summary=False)
        assert result.summary is None

    def test_summary_raw_output_contains_count(self, detector: RTDETRDetector) -> None:
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(image)
        assert result.summary is not None
        assert result.summary.raw_output["count"] == 3

    def test_empty_image(self, detector: RTDETRDetector) -> None:
        """detect() with size-0 array returns empty result."""
        image = np.array([], dtype=np.uint8)
        result = detector.detect(image)
        assert len(result.detections) == 0

    def test_none_image(self, detector: RTDETRDetector) -> None:
        result = detector.detect(None)
        assert len(result.detections) == 0

    def test_grayscale_image(self, detector: RTDETRDetector) -> None:
        image = np.zeros((480, 640), dtype=np.uint8)
        result = detector.detect(image)
        assert isinstance(result, DetectionResult)

    def test_rgba_image(self, detector: RTDETRDetector) -> None:
        image = np.zeros((480, 640, 4), dtype=np.uint8)
        result = detector.detect(image)
        assert isinstance(result, DetectionResult)


# ------------------------------------------------------------------ #
# A.4.1-e  test_rtdetr_no_detections
# ------------------------------------------------------------------ #

class TestRTDETRNoDetections:
    @pytest.fixture()
    def detector(self) -> RTDETRDetector:
        det = RTDETRDetector.__new__(RTDETRDetector)
        det._conf = 0.35
        det._iou = 0.55
        det._imgsz = 640
        det._max_det = 300
        det._names = ("resistor",)
        det._resolved_weights = Path("/fake/weights.pt")
        det._device = "cpu"

        mock_model = MagicMock()
        mock_model.predict.return_value = [_make_empty_result()]
        det._model = mock_model
        return det

    def test_empty_result(self, detector: RTDETRDetector) -> None:
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(image)
        assert len(result.detections) == 0
        assert result.summary is not None
        assert result.summary.raw_output["count"] == 0


# ------------------------------------------------------------------ #
# A.4.1-f  test_weight_resolution
# ------------------------------------------------------------------ #

class TestWeightResolution:
    def test_explicit_path_takes_priority(self, tmp_path: Path) -> None:
        weights = tmp_path / "custom.pt"
        weights.touch()

        det = RTDETRDetector(weights_path=weights)
        resolved = det._resolve_weights()
        assert resolved == weights.resolve()

    def test_env_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        weights = tmp_path / "env_weights.pt"
        weights.touch()
        monkeypatch.setenv("TALK_ELECTRONIC_RTDETR_WEIGHTS", str(weights))

        det = RTDETRDetector()
        resolved = det._resolve_weights()
        assert resolved == weights.resolve()

    def test_raises_when_no_weights_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TALK_ELECTRONIC_RTDETR_WEIGHTS", raising=False)
        # Patch _project_root so candidate search doesn't find real weights
        monkeypatch.setattr(RTDETRDetector, "_project_root", staticmethod(lambda: tmp_path / "empty_project"))
        det = RTDETRDetector(weights_path=tmp_path / "nonexistent" / "path.pt")
        with pytest.raises(FileNotFoundError):
            det._resolve_weights()
