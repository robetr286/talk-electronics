from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from talk_electronic.services.symbol_detection import YoloV8SegDetector, register_detector
from talk_electronic.services.symbol_detection.base import (
    BoundingBox,
    DetectionResult,
    DetectorSummary,
    SymbolDetection,
    SymbolDetector,
)


def _make_data_url(size: tuple[int, int] = (8, 8), color: tuple[int, int, int] = (255, 255, 255)) -> str:
    image = Image.new("RGB", size, color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def test_list_detectors_includes_builtin_detectors(client):
    response = client.get("/api/symbols/detectors")
    assert response.status_code == 200
    payload = response.get_json()
    names = [entry["name"] for entry in payload.get("detectors", [])]
    assert "noop" in names
    assert "simple" in names
    assert "yolov8" in names


def test_detect_symbols_returns_noop_result(client):
    response = client.post(
        "/api/symbols/detect",
        json={"imageData": _make_data_url()},
    )

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["detector"]["name"] == "noop"
    assert payload["count"] == 0
    assert payload.get("summary") is not None
    assert payload.get("source", {}).get("source") == "inline"
    shape = payload.get("source", {}).get("imageShape")
    assert shape == [8, 8, 3]


def test_detect_symbols_store_history_creates_entry(app, client):
    upload_folder: Path = app.config["UPLOAD_FOLDER"]

    response = client.post(
        "/api/symbols/detect",
        json={"imageData": _make_data_url(), "storeHistory": True},
    )

    assert response.status_code == 200
    payload = response.get_json()
    entry = payload.get("historyEntry")
    assert entry is not None
    assert entry["type"] == "symbol-detection"

    stored_filename = entry["storage"]["filename"]
    stored_path = upload_folder / stored_filename
    assert stored_path.exists()

    with stored_path.open("r", encoding="utf-8") as handle:
        stored_payload = json.load(handle)

    assert stored_payload["detector"]["name"] == "noop"
    assert stored_payload["count"] == payload["count"]


def _draw_symbol_sample(size: tuple[int, int] = (96, 96)) -> str:
    image = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 50, 50), fill=(0, 0, 0))
    draw.rectangle((60, 30, 86, 70), outline=(0, 0, 0), width=4)
    draw.ellipse((30, 60, 58, 88), outline=(0, 0, 0), width=3)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def test_detect_symbols_simple_detector_returns_candidates(client):
    payload = {
        "detector": "simple",
        "imageData": _draw_symbol_sample(),
    }
    response = client.post("/api/symbols/detect", json=payload)

    assert response.status_code == 200
    result = response.get_json()
    assert result["detector"]["name"] == "simple"
    assert result["count"] > 0
    assert isinstance(result.get("detections"), list)
    for detection in result["detections"]:
        bbox = detection.get("bbox") or (
            [
                detection.get("box", {}).get("x", 0.0),
                detection.get("box", {}).get("y", 0.0),
                detection.get("box", {}).get("width", 0.0),
                detection.get("box", {}).get("height", 0.0),
            ]
        )
        assert bbox[2] > 0
        assert bbox[3] > 0
        break


def test_detect_symbols_unknown_detector(client):
    response = client.post(
        "/api/symbols/detect",
        json={"detector": "missing", "imageData": _make_data_url()},
    )

    assert response.status_code == 400
    error = response.get_json()
    assert "Unknown detector" in error.get("error", "")


def test_detect_symbols_yolov8_smoke(client):
    class StubYolo(SymbolDetector):
        name = "yolov8"
        version = "stub-test"

        def detect(self, image, *, return_summary: bool = True):  # noqa: ARG002
            detection = SymbolDetection(
                label="resistor",
                score=0.91,
                box=BoundingBox(10, 10, 32, 32),
            )
            summary = DetectorSummary(latency_ms=1.5, raw_output={"emitted": 1})
            return DetectionResult(detections=(detection,), summary=summary if return_summary else None)

    register_detector(StubYolo.name, StubYolo, replace=True)

    response = client.post(
        "/api/symbols/detect",
        json={"detector": "yolov8", "imageData": _draw_symbol_sample()},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["detector"]["name"] == "yolov8"
    assert payload["count"] == 1
    assert payload["detections"][0]["label"] == "resistor"
    assert payload["summary"]["rawOutput"]["emitted"] == 1

    register_detector(YoloV8SegDetector.name, YoloV8SegDetector, replace=True)


def test_detect_symbols_applies_stored_ignore_mask(client):
    class IgnoreStub(SymbolDetector):
        name = "ignore-stub"
        version = "test"

        def detect(self, image, *, return_summary: bool = True):  # noqa: ARG002
            detection = SymbolDetection(
                label="symbol",
                score=0.95,
                box=BoundingBox(10, 10, 24, 24),
            )
            return DetectionResult(detections=(detection,), summary=None)

    register_detector(IgnoreStub.name, IgnoreStub, replace=True)

    headers = {"X-Ignore-Token": "test-secret"}
    ignore_payload = {
        "objects": [
            {
                "type": "brush",
                "points": [[5, 5], [25, 25], [35, 35]],
                "brushSize": 20,
            }
        ],
        "imageShape": [64, 64],
        "label": "Maska testowa",
    }
    entry_resp = client.post("/api/ignore-regions", json=ignore_payload, headers=headers)
    assert entry_resp.status_code == 201
    ignore_entry = entry_resp.get_json()["entry"]

    detect_resp = client.post(
        "/api/symbols/detect",
        json={
            "detector": "ignore-stub",
            "imageData": _make_data_url((64, 64)),
            "ignoreEntryId": ignore_entry["id"],
        },
    )

    assert detect_resp.status_code == 200
    payload = detect_resp.get_json()
    assert payload["count"] == 0
    assert payload.get("filteredByIgnore", {}).get("entryId") == ignore_entry["id"]
    assert payload["filteredByIgnore"].get("maskApplied") is True


def test_detect_symbols_inline_ignore_polygon_filters_detection(client):
    class InlineStub(SymbolDetector):
        name = "inline-stub"
        version = "test"

        def detect(self, image, *, return_summary: bool = True):  # noqa: ARG002
            detection = SymbolDetection(
                label="inline",
                score=0.5,
                box=BoundingBox(20, 20, 16, 16),
            )
            return DetectionResult(detections=(detection,), summary=None)

    register_detector(InlineStub.name, InlineStub, replace=True)

    payload = {
        "detector": "inline-stub",
        "imageData": _make_data_url((64, 64)),
        "ignoreRegions": [
            {
                "type": "polygon",
                "points": [[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75]],
            }
        ],
    }

    response = client.post("/api/symbols/detect", json=payload)
    assert response.status_code == 200
    result = response.get_json()
    assert result["count"] == 0
    assert result.get("filteredByIgnore", {}).get("inlineRegions") == 1
    assert result["filteredByIgnore"].get("maskApplied") is False


# ------------------------------------------------------------------ #
# A.4.3 — E2E test RT-DETR via HTTP route
# ------------------------------------------------------------------ #

def test_detect_symbols_rtdetr_e2e(client):
    """Full pipeline: upload inline image → detect with 'rtdetr' → verify JSON."""
    from talk_electronic.services.symbol_detection.rtdetr import RTDETRDetector

    class StubRTDETR(SymbolDetector):
        name = "rtdetr"
        version = "L-v1-stub"

        def detect(self, image, *, return_summary: bool = True):  # noqa: ARG002
            detections = (
                SymbolDetection(label="resistor", score=0.92, box=BoundingBox(10, 20, 40, 30)),
                SymbolDetection(label="capacitor", score=0.87, box=BoundingBox(60, 40, 35, 25)),
                SymbolDetection(label="diode", score=0.78, box=BoundingBox(100, 80, 30, 30)),
            )
            summary = DetectorSummary(latency_ms=38.0, raw_output={"count": 3, "classes": {"resistor": 1, "capacitor": 1, "diode": 1}})
            return DetectionResult(detections=detections, summary=summary if return_summary else None)

    register_detector(StubRTDETR.name, StubRTDETR, replace=True)

    response = client.post(
        "/api/symbols/detect",
        json={"detector": "rtdetr", "imageData": _draw_symbol_sample()},
    )

    assert response.status_code == 200
    payload = response.get_json()

    # Verify detector metadata
    assert payload["detector"]["name"] == "rtdetr"

    # Verify detections
    assert payload["count"] == 3
    labels = [d["label"] for d in payload["detections"]]
    assert "resistor" in labels
    assert "capacitor" in labels
    assert "diode" in labels

    # Verify summary
    assert payload["summary"]["latencyMs"] == 38.0

    # Verify source
    assert payload.get("source", {}).get("source") == "inline"

    # Restore original
    register_detector(RTDETRDetector.name, RTDETRDetector, replace=True)
