from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import cv2
import numpy as np

from .base import BoundingBox, DetectionResult, DetectorSummary, SymbolDetection, SymbolDetector


class YoloV8SegDetector(SymbolDetector):
    """Segmentation-aware detector backed by Ultralytics YOLOv8 weights."""

    name = "yolov8"
    version = "seg-train6"

    def __init__(
        self,
        *,
        weights_path: str | os.PathLike[str] | None = None,
        conf: float = 0.35,
        iou: float = 0.55,
        imgsz: int = 640,
        max_det: int = 300,
    ) -> None:
        self._explicit_path = Path(weights_path).expanduser().resolve() if weights_path else None
        self._conf = float(conf)
        self._iou = float(iou)
        self._imgsz = int(imgsz)
        self._max_det = int(max_det)
        self._model = None
        self._names: tuple[str, ...] = ()
        self._resolved_weights: Path | None = None
        self._device = os.environ.get("TALK_ELECTRONIC_YOLO_DEVICE", "auto")

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parents[2]

    def _candidate_weights(self) -> Iterable[Path]:
        project_root = self._project_root()
        repo_root = project_root.parent
        env_override = os.environ.get("TALK_ELECTRONIC_YOLO_WEIGHTS")
        candidates: list[Path] = []
        if self._explicit_path is not None:
            candidates.append(self._explicit_path)
        if env_override:
            candidates.append(Path(env_override).expanduser())
        search_roots = [project_root]
        if repo_root not in search_roots:
            search_roots.append(repo_root)

        for root in search_roots:
            candidates.extend(
                (
                    root / "weights" / "train6_best.pt",
                    root / "weights" / "best.pt",
                    root / "weights" / "yolov8s-seg.pt",
                    root / "runs" / "segment" / "train6" / "weights" / "best.pt",
                    root / "weights" / "train6_last.pt",
                    root / "runs" / "segment" / "train6" / "weights" / "last.pt",
                )
            )
        seen: set[Path] = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield resolved

    def _resolve_weights(self) -> Path:
        if self._resolved_weights and self._resolved_weights.exists():
            return self._resolved_weights
        for candidate in self._candidate_weights():
            if candidate.is_file():
                self._resolved_weights = candidate
                return candidate
        raise FileNotFoundError(
            "Nie znaleziono pliku wag YOLO. Ustaw TALK_ELECTRONIC_YOLO_WEIGHTS lub umieść best.pt w katalogu weights/."
        )

    @staticmethod
    def _resolve_device(preferred: str) -> str:
        if preferred and preferred.lower() != "auto":
            return preferred
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except Exception:  # pragma: no cover - środowisko bez torch/cuda
            return "cpu"
        return "cpu"

    def warmup(self) -> None:  # noqa: D401
        """Leniwe ładowanie modelu Ultralytics YOLOv8."""

        if self._model is not None:
            return
        weights = self._resolve_weights()
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover - zależność opcjonalna
            raise RuntimeError("Ultralytics YOLO jest wymagany do działania YoloV8SegDetector") from exc

        self._model = YOLO(str(weights))
        # Ultralytics przechowuje etykiety w dict -> zamieniamy na krotkę dla deterministyczności.
        names_dict = getattr(self._model, "names", {}) or {}
        ordered = [names_dict[key] for key in sorted(names_dict)] if isinstance(names_dict, dict) else []
        self._names = tuple(str(name) for name in ordered) or tuple("symbol" for _ in range(32))

    def unload(self) -> None:
        self._model = None

    def detect(
        self, image: np.ndarray, *, return_summary: bool = True
    ) -> DetectionResult:  # noqa: C901 - kompleksowa ścieżka
        if image is None or image.size == 0:
            return DetectionResult(detections=(), summary=self._build_summary(0.0, return_summary, None, ()))

        self.warmup()
        assert self._model is not None  # for type-checkers

        prepared = self._prepare_image(image)
        start_ts = perf_counter()

        results = self._model.predict(  # type: ignore[call-arg]
            source=prepared,
            imgsz=self._imgsz,
            conf=self._conf,
            iou=self._iou,
            max_det=self._max_det,
            verbose=False,
            device=self._resolve_device(self._device),
        )
        if not results:
            return DetectionResult(detections=(), summary=self._build_summary(start_ts, return_summary, None, ()))

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or boxes.xywh is None or len(boxes.xywh) == 0:
            return DetectionResult(detections=(), summary=self._build_summary(start_ts, return_summary, result, ()))

        boxes_xywh = boxes.xywh.cpu().numpy()
        scores = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)

        masks = getattr(result, "masks", None)
        polygons: list[np.ndarray | None] = []
        if masks is not None and getattr(masks, "xy", None) is not None:
            polygons = list(masks.xy)

        detections: list[SymbolDetection] = []
        for idx, xywh in enumerate(boxes_xywh):
            score = float(scores[idx]) if idx < len(scores) else 0.0
            class_id = int(classes[idx]) if idx < len(classes) else -1
            width = float(xywh[2])
            height = float(xywh[3])
            x = float(xywh[0] - width / 2)
            y = float(xywh[1] - height / 2)
            box = BoundingBox(max(0.0, x), max(0.0, y), max(width, 1.0), max(height, 1.0))
            label = self._lookup_label(class_id)
            metadata = {
                "class_id": class_id,
                "score": score,
            }
            if polygons and idx < len(polygons) and polygons[idx] is not None:
                metadata["segmentation"] = self._normalize_polygon(polygons[idx])
            detections.append(
                SymbolDetection(
                    label=label,
                    score=score,
                    box=box,
                    rotation=0.0,
                    metadata=metadata,
                )
            )

        summary = self._build_summary(start_ts, return_summary, result, detections)
        return DetectionResult(detections=detections, summary=summary)

    def _lookup_label(self, class_id: int) -> str:
        if 0 <= class_id < len(self._names):
            return self._names[class_id]
        return "symbol"

    @staticmethod
    def _prepare_image(image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if image.ndim == 3 and image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        return image

    @staticmethod
    def _normalize_polygon(polygon: np.ndarray) -> list[list[float]]:
        array = np.asarray(polygon, dtype=float).reshape(-1, 2)
        return [[float(x), float(y)] for x, y in array]

    def _build_summary(
        self,
        start_ts: float,
        return_summary: bool,
        raw_result: Any,
        detections: Iterable[SymbolDetection],
    ) -> DetectorSummary | None:
        if not return_summary:
            return None

        latency_ms = 0.0
        if start_ts:
            latency_ms = (perf_counter() - start_ts) * 1000.0

        detections_list = list(detections)
        histogram = Counter(detection.label for detection in detections_list)
        speed = getattr(raw_result, "speed", None)
        raw_speed = None
        if isinstance(speed, dict):
            raw_speed = {key: float(value) for key, value in speed.items() if isinstance(value, (int, float))}

        payload = {
            "count": len(detections_list),
            "classes": dict(histogram),
        }
        if self._resolved_weights is not None:
            payload["weights"] = self._resolved_weights.as_posix()
        if raw_speed:
            payload["speed"] = raw_speed

        return DetectorSummary(latency_ms=latency_ms, raw_output=payload)
