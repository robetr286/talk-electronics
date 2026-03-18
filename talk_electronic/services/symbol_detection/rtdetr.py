from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import cv2
import numpy as np

from .base import BoundingBox, DetectionResult, DetectorSummary, SymbolDetection, SymbolDetector


class RTDETRDetector(SymbolDetector):
    """Object detector backed by Ultralytics RT-DETR-L weights (PyTorch).

    RT-DETR (Real-Time DEtection TRansformer) to architektura z mechanizmem
    attention (hybrid encoder + DETR decoder), zaimplementowana w Ultralytics
    jako natywny model PyTorch.  Interfejs API jest identyczny z YOLO —
    ``model.predict()``, ``model.train()`` — co pozwala na bezproblemową
    integrację z istniejącym pipeline'em.

    Konfiguracja wag:
        1) Ścieżka jawna przez ``weights_path``
        2) Zmienna env ``TALK_ELECTRONIC_RTDETR_WEIGHTS``
        3) Domyślne lokalizacje w ``weights/``
    """

    name = "rtdetr"
    version = "L-v1"

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

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
        self._device = os.environ.get("TALK_ELECTRONIC_RTDETR_DEVICE", "auto")

    # ------------------------------------------------------------------
    # Weight resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parents[2]

    def _candidate_weights(self) -> Iterable[Path]:
        project_root = self._project_root()
        repo_root = project_root.parent
        env_override = os.environ.get("TALK_ELECTRONIC_RTDETR_WEIGHTS")
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
                    root / "weights" / "rtdetr_best.pt",
                    root / "weights" / "rtdetr-l.pt",
                    root / "weights" / "rtdetr-l-best.pt",
                    root / "runs" / "detect" / "rtdetr" / "weights" / "best.pt",
                    root / "runs" / "detect" / "rtdetr" / "weights" / "last.pt",
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
            "Nie znaleziono pliku wag RT-DETR. "
            "Ustaw TALK_ELECTRONIC_RTDETR_WEIGHTS lub umieść rtdetr-l.pt w katalogu weights/."
        )

    # ------------------------------------------------------------------
    # Device resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_device(preferred: str) -> str:
        if preferred and preferred.lower() != "auto":
            return preferred
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except Exception:  # pragma: no cover
            return "cpu"
        return "cpu"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def warmup(self) -> None:
        """Leniwe ładowanie modelu Ultralytics RT-DETR."""
        if self._model is not None:
            return
        weights = self._resolve_weights()
        try:
            from ultralytics import RTDETR
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Ultralytics RTDETR jest wymagany do działania RTDETRDetector"
            ) from exc

        self._model = RTDETR(str(weights))

        # Ultralytics przechowuje etykiety w dict → zamieniamy na krotkę.
        names_dict = getattr(self._model, "names", {}) or {}
        ordered = (
            [names_dict[key] for key in sorted(names_dict)]
            if isinstance(names_dict, dict)
            else []
        )
        self._names = tuple(str(n) for n in ordered) or ("symbol",)

    def unload(self) -> None:
        """Zwolnij model i pamięć GPU."""
        self._model = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # pragma: no cover
            pass

    def labels(self) -> Iterable[str]:
        """Zwróć znane klasy (po warmup)."""
        return self._names

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(
        self, image: np.ndarray, *, return_summary: bool = True
    ) -> DetectionResult:
        if image is None or image.size == 0:
            return DetectionResult(
                detections=(),
                summary=self._build_summary(0.0, return_summary, None, ()),
            )

        self.warmup()
        assert self._model is not None  # for type-checkers

        prepared = self._prepare_image(image)
        start_ts = perf_counter()

        results = self._model.predict(
            source=prepared,
            imgsz=self._imgsz,
            conf=self._conf,
            iou=self._iou,
            max_det=self._max_det,
            verbose=False,
            device=self._resolve_device(self._device),
        )

        if not results:
            return DetectionResult(
                detections=(),
                summary=self._build_summary(start_ts, return_summary, None, ()),
            )

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or boxes.xywh is None or len(boxes.xywh) == 0:
            return DetectionResult(
                detections=(),
                summary=self._build_summary(start_ts, return_summary, result, ()),
            )

        boxes_xywh = boxes.xywh.cpu().numpy()
        scores = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)

        detections: list[SymbolDetection] = []
        for idx, xywh in enumerate(boxes_xywh):
            score = float(scores[idx]) if idx < len(scores) else 0.0
            class_id = int(classes[idx]) if idx < len(classes) else -1

            width = float(xywh[2])
            height = float(xywh[3])
            x = float(xywh[0] - width / 2)
            y = float(xywh[1] - height / 2)
            box = BoundingBox(
                max(0.0, x), max(0.0, y), max(width, 1.0), max(height, 1.0)
            )

            label = self._lookup_label(class_id)
            metadata: dict[str, Any] = {
                "class_id": class_id,
                "score": score,
            }
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _lookup_label(self, class_id: int) -> str:
        if 0 <= class_id < len(self._names):
            return self._names[class_id]
        return "symbol"

    @staticmethod
    def _prepare_image(image: np.ndarray) -> np.ndarray:
        """Normalizuj obraz do BGR 3-kanałowego."""
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if image.ndim == 3 and image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        return image

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
            raw_speed = {
                key: float(value)
                for key, value in speed.items()
                if isinstance(value, (int, float))
            }

        payload: dict[str, Any] = {
            "count": len(detections_list),
            "classes": dict(histogram),
        }
        if self._resolved_weights is not None:
            payload["weights"] = self._resolved_weights.as_posix()
        if raw_speed:
            payload["speed"] = raw_speed

        return DetectorSummary(latency_ms=latency_ms, raw_output=payload)
