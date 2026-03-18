"""
Template matching detector for electronic symbols.

Prosty detektor baseline wykorzystujący OpenCV template matching
z multiscale search do wykrywania symboli elektronicznych.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image

from .base import BoundingBox, DetectionResult, DetectorSummary, SymbolDetection, SymbolDetector


class TemplateMatchingDetector(SymbolDetector):
    """
    Detektor symboli wykorzystujący template matching.

    Cechy:
    - Multiscale search (różne skale szablonu)
    - Non-maximum suppression (NMS) do usunięcia duplikatów
    - Konfigurowalne progi dopasowania dla różnych symboli
    - Obsługa wielu wariantów orientacji
    """

    name = "template_matching"
    version = "1.0"

    def __init__(
        self,
        templates_dir: Path | str = "data/templates",
        threshold: float = 0.7,
        scales: List[float] = None,
        nms_threshold: float = 0.3,
    ):
        """
        Inicjalizacja detektora.

        Args:
            templates_dir: Katalog z szablonami PNG
            threshold: Próg pewności dopasowania (0.0-1.0)
            scales: Lista skal do przeszukania (domyślnie: [0.5, 0.75, 1.0, 1.25, 1.5])
            nms_threshold: Próg IoU dla non-maximum suppression
        """
        self.templates_dir = Path(templates_dir)
        self.threshold = threshold
        self.scales = scales or [0.5, 0.75, 1.0, 1.25, 1.5]
        self.nms_threshold = nms_threshold

        # Cache dla załadowanych szablonów
        self.templates: Dict[str, List[Tuple[np.ndarray, str]]] = {}

        # Mapowanie nazw plików na kategorie
        self.category_mapping = {
            "resistor": "resistor",
            "capacitor": "capacitor",
            "inductor": "inductor",
            "diode": "diode",
            "transistor": "transistor",
        }

    def labels(self) -> List[str]:
        """Zwraca listę znanych etykiet."""
        return list(self.category_mapping.values())

    def warmup(self) -> None:
        """Wczytuje szablony podczas inicjalizacji."""
        if not self.templates_dir.exists():
            print(f"⚠️  Katalog szablonów nie istnieje: {self.templates_dir}")
            return

        # Wczytaj wszystkie szablony PNG z podkatalogów
        template_files = list(self.templates_dir.glob("**/*.png"))

        if not template_files:
            print(f"⚠️  Brak szablonów PNG w: {self.templates_dir}")
            return

        for template_path in template_files:
            # Wyciągnij kategorię z nazwy pliku (np. resistor_h.png -> resistor)
            # lub z nazwy podkatalogu
            base_name = template_path.stem.split("_")[0]

            # Jeśli plik jest w podkatalogu, użyj nazwy podkatalogu jako kategorii
            if template_path.parent != self.templates_dir:
                category = template_path.parent.name
            else:
                category = self.category_mapping.get(base_name, base_name)

            # Wczytaj szablon jako grayscale
            template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)

            if template is None:
                print(f"⚠️  Nie można wczytać szablonu: {template_path}")
                continue

            # Dodaj do cache
            if category not in self.templates:
                self.templates[category] = []

            self.templates[category].append((template, template_path.stem))

        print(f"✓ Wczytano szablony: {len(template_files)} plików, " f"{len(self.templates)} kategorii")

    def detect(self, image: Image.Image | np.ndarray, *, return_summary: bool = True) -> DetectionResult:
        """
        Wykrywa symbole na obrazie.

        Args:
            image: Obraz PIL lub numpy array do przetworzenia
            return_summary: Czy zwrócić statystyki (zgodne z API)

        Returns:
            DetectionResult z wykrytymi symbolami
        """
        start_time = time.perf_counter()

        # Konwertuj do OpenCV grayscale
        if isinstance(image, np.ndarray):
            # Already numpy array, ensure grayscale
            if len(image.shape) == 3:
                image_np = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                image_np = image
        else:
            # PIL Image
            image_np = np.array(image.convert("L"))

        if len(self.templates) == 0:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return DetectionResult(
                detections=[],
                summary=(
                    DetectorSummary(latency_ms=elapsed_ms, raw_output={"warning": "Brak wczytanych szablonów"})
                    if return_summary
                    else None
                ),
            )

        all_detections = []

        # Dla każdej kategorii
        for category, templates in self.templates.items():
            for template, template_name in templates:
                # Multiscale matching
                detections = self._match_template_multiscale(image_np, template, category, template_name)
                all_detections.extend(detections)

        # Non-maximum suppression
        filtered_detections = self._apply_nms(all_detections)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return DetectionResult(
            detections=filtered_detections,
            summary=(
                DetectorSummary(
                    latency_ms=elapsed_ms,
                    raw_output={
                        "detector": "template_matching",
                        "num_templates": sum(len(t) for t in self.templates.values()),
                        "num_categories": len(self.templates),
                        "scales_used": self.scales,
                        "threshold": self.threshold,
                        "detections_before_nms": len(all_detections),
                        "detections_after_nms": len(filtered_detections),
                    },
                )
                if return_summary
                else None
            ),
        )

    def _match_template_multiscale(
        self, image: np.ndarray, template: np.ndarray, category: str, template_name: str
    ) -> List[SymbolDetection]:
        """
        Dopasowuje szablon w różnych skalach.

        Args:
            image: Obraz wejściowy (grayscale)
            template: Szablon do dopasowania (grayscale)
            category: Kategoria symbolu
            template_name: Nazwa szablonu

        Returns:
            Lista wykrytych dopasowań jako SymbolDetection
        """
        detections = []
        img_height, img_width = image.shape

        for scale in self.scales:
            # Przeskaluj szablon
            scaled_width = int(template.shape[1] * scale)
            scaled_height = int(template.shape[0] * scale)

            # Pomiń jeśli szablon jest większy niż obraz
            if scaled_width > img_width or scaled_height > img_height:
                continue

            scaled_template = cv2.resize(template, (scaled_width, scaled_height), interpolation=cv2.INTER_AREA)

            # Template matching
            result = cv2.matchTemplate(image, scaled_template, cv2.TM_CCOEFF_NORMED)

            # Znajdź lokalizacje powyżej progu
            locations = np.where(result >= self.threshold)

            # Dla każdej lokalizacji
            for pt in zip(*locations[::-1]):
                x, y = pt
                confidence = float(result[y, x])

                detection = SymbolDetection(
                    label=category,
                    score=confidence,
                    box=BoundingBox(x=float(x), y=float(y), width=float(scaled_width), height=float(scaled_height)),
                    rotation=0.0,
                    metadata={
                        "template": template_name,
                        "scale": scale,
                    },
                )

                detections.append(detection)

        return detections

    def _apply_nms(self, detections: List[SymbolDetection], iou_threshold: float = None) -> List[SymbolDetection]:
        """
        Stosuje non-maximum suppression do usunięcia nakładających się detekcji.

        Args:
            detections: Lista detekcji
            iou_threshold: Próg IoU (opcjonalny, domyślnie self.nms_threshold)

        Returns:
            Przefiltrowana lista detekcji
        """
        if not detections:
            return []

        if iou_threshold is None:
            iou_threshold = self.nms_threshold

        # Sortuj według pewności (malejąco)
        sorted_detections = sorted(detections, key=lambda d: d.score, reverse=True)

        kept = []

        while sorted_detections:
            # Weź detekcję z najwyższym score
            best = sorted_detections.pop(0)
            kept.append(best)

            # Usuń wszystkie detekcje z tym samym labelem, które się nakładają
            remaining = []
            for detection in sorted_detections:
                # Sprawdź nakładanie tylko dla tej samej kategorii
                if detection.label == best.label:
                    iou = self._calculate_iou(best.box, detection.box)
                    if iou < iou_threshold:
                        remaining.append(detection)
                else:
                    # Inna kategoria - zachowaj
                    remaining.append(detection)

            sorted_detections = remaining

        return kept

    def _calculate_iou(self, bbox1: BoundingBox, bbox2: BoundingBox) -> float:
        """
        Oblicza Intersection over Union dla dwóch bounding boxów.

        Args:
            bbox1: Pierwszy bbox
            bbox2: Drugi bbox

        Returns:
            IoU w zakresie [0, 1]
        """
        # Współrzędne przecięcia
        x1 = max(bbox1.x, bbox2.x)
        y1 = max(bbox1.y, bbox2.y)
        x2 = min(bbox1.x + bbox1.width, bbox2.x + bbox2.width)
        y2 = min(bbox1.y + bbox1.height, bbox2.y + bbox2.height)

        # Pole przecięcia
        if x2 < x1 or y2 < y1:
            return 0.0

        intersection = (x2 - x1) * (y2 - y1)

        # Pole unii
        area1 = bbox1.width * bbox1.height
        area2 = bbox2.width * bbox2.height
        union = area1 + area2 - intersection

        if union <= 0:
            return 0.0

        return intersection / union
