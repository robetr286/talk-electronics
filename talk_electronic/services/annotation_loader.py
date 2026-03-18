"""
Automatyczny loader anotacji z detekcją i konwersją rotated rectangles.
"""

import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def load_annotations(annotation_file: Path) -> Dict:
    """
    Ładuje anotacje i automatycznie konwertuje rotated rectangles jeśli potrzeba.

    Args:
        annotation_file: Ścieżka do pliku JSON z anotacjami (Label Studio lub COCO)

    Returns:
        Dict w standardowym formacie COCO (segmentation jako wielokąty)

    Raises:
        FileNotFoundError: Jeśli plik nie istnieje
        ValueError: Jeśli format jest nieprawidłowy
    """
    if not annotation_file.exists():
        raise FileNotFoundError(f"Plik anotacji nie istnieje: {annotation_file}")

    logger.info(f"Ładowanie anotacji z: {annotation_file}")

    with open(annotation_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Wykryj format i sprawdź czy potrzebna konwersja
    conversion_info = detect_annotation_format(data)

    if conversion_info["needs_conversion"]:
        logger.warning(
            f"⚠️  Wykryto {conversion_info['rotated_count']} anotacji z rotacją "
            f"(format: {conversion_info['format']}) - uruchamiam automatyczną konwersję..."
        )

        data = convert_rotated_to_segmentation(data, conversion_info["format"])

        logger.info(
            f"✅ Konwersja zakończona pomyślnie: "
            f"{conversion_info['rotated_count']} prostokątów → wielokąty segmentacji"
        )
    else:
        logger.info("✅ Anotacje już w standardowym formacie COCO - brak konwersji")

    return data


def detect_annotation_format(coco_data: Dict) -> Dict:
    """
    Wykrywa format anotacji i sprawdza czy potrzebna konwersja.

    Returns:
        Dict z informacjami:
        - needs_conversion: bool
        - format: 'label_studio' | 'yolov8_obb' | 'coco_standard'
        - rotated_count: int (liczba anotacji wymagających konwersji)
        - total_count: int
    """
    annotations = coco_data.get("annotations", [])

    if not annotations:
        return {"needs_conversion": False, "format": "empty", "rotated_count": 0, "total_count": 0}

    rotated_count = 0
    detected_format = "coco_standard"

    for ann in annotations:
        # Format Label Studio: rotation jako oddzielne pole
        if "rotation" in ann:
            rotated_count += 1
            detected_format = "label_studio"

        # Format YOLOv8-OBB: bbox z 5 wartościami [x_center, y_center, w, h, angle]
        elif "bbox" in ann and len(ann.get("bbox", [])) == 5:
            rotated_count += 1
            detected_format = "yolov8_obb"

        # Sprawdź czy brakuje segmentation (ale jest bbox + rotation)
        elif "bbox" in ann and not ann.get("segmentation"):
            if "rotation" in ann or len(ann.get("bbox", [])) == 5:
                rotated_count += 1

    return {
        "needs_conversion": rotated_count > 0,
        "format": detected_format,
        "rotated_count": rotated_count,
        "total_count": len(annotations),
    }


def convert_rotated_to_segmentation(coco_data: Dict, format_type: str) -> Dict:
    """
    Konwertuje rotated rectangles na segmentation polygons.

    Args:
        coco_data: Dane COCO z rotated rectangles
        format_type: 'label_studio' lub 'yolov8_obb'

    Returns:
        Dane COCO ze standardowym polem segmentation
    """
    converted_count = 0

    for ann in coco_data["annotations"]:

        # Format Label Studio: rotation jako oddzielne pole
        if "rotation" in ann and "bbox" in ann:
            x, y, w, h = ann["bbox"][:4]  # Może być [x,y,w,h] lub [x,y,w,h,area]
            angle = ann["rotation"]

            # Konwertuj na 4 punkty
            ann["segmentation"] = [rotated_rect_to_points(x, y, w, h, angle)]

            # Usuń niestandadowe pole rotation
            del ann["rotation"]
            converted_count += 1

            logger.debug(f"Konwersja Label Studio: bbox={ann['bbox']}, angle={angle}°")

        # Format YOLOv8-OBB: [x_center, y_center, w, h, angle]
        elif "bbox" in ann and len(ann["bbox"]) == 5:
            x_c, y_c, w, h, angle = ann["bbox"]

            # Konwertuj na 4 punkty
            ann["segmentation"] = [rotated_rect_to_points(x_c, y_c, w, h, angle)]

            # Popraw bbox do standardowego COCO [x_min, y_min, width, height]
            ann["bbox"] = [x_c - w / 2, y_c - h / 2, w, h]
            converted_count += 1

            logger.debug(f"Konwersja YOLOv8-OBB: center=({x_c},{y_c}), size=({w},{h}), angle={angle}°")

        # Jeśli brakuje segmentation, ale jest bbox (bez rotacji) - utwórz prostokątny polygon
        elif "bbox" in ann and not ann.get("segmentation"):
            x, y, w, h = ann["bbox"][:4]
            # Prostokąt bez rotacji: 4 punkty w kolejności lewygórny → prawygórny → prawydolny → lewydolny
            ann["segmentation"] = [
                [x, y, x + w, y, x + w, y + h, x, y + h]  # lewy górny  # prawy górny  # prawy dolny  # lewy dolny
            ]
            converted_count += 1

            logger.debug(f"Konwersja prostokąta bez rotacji: bbox={ann['bbox']}")

    logger.info(f"Przekonwertowano {converted_count} anotacji do formatu segmentacji")

    return coco_data


def rotated_rect_to_points(x: float, y: float, w: float, h: float, angle_deg: float) -> List[float]:
    """
    Konwertuje rotated rectangle na listę 4 punktów (8 wartości: x1,y1,x2,y2,x3,y3,x4,y4).

    Args:
        x, y: Współrzędne centrum prostokąta (Label Studio) lub lewego górnego rogu (COCO)
        w, h: Szerokość i wysokość
        angle_deg: Kąt obrotu w stopniach (przeciwnie do ruchu wskazówek zegara)

    Returns:
        Lista [x1, y1, x2, y2, x3, y3, x4, y4] - 4 rogi prostokąta po obrocie
    """
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # Zakładamy że (x, y) to centrum prostokąta
    # 4 rogi względem centrum (przed rotacją)
    corners = [
        (-w / 2, -h / 2),  # lewy górny
        (w / 2, -h / 2),  # prawy górny
        (w / 2, h / 2),  # prawy dolny
        (-w / 2, h / 2),  # lewy dolny
    ]

    # Obróć każdy róg i przesuń do pozycji globalnej
    points = []
    for cx, cy in corners:
        # Rotacja wokół centrum
        rx = x + cx * cos_a - cy * sin_a
        ry = y + cx * sin_a + cy * cos_a
        points.extend([rx, ry])

    return points


def validate_coco_annotations(coco_data: Dict) -> Tuple[bool, List[str]]:
    """
    Waliduje czy anotacje COCO są poprawne.

    Returns:
        (is_valid, errors): Tuple[bool, List[str]]
    """
    errors = []

    if "annotations" not in coco_data:
        errors.append("Brak pola 'annotations' w danych")
        return False, errors

    if "images" not in coco_data:
        errors.append("Brak pola 'images' w danych")
        return False, errors

    for i, ann in enumerate(coco_data["annotations"]):
        # Sprawdź wymagane pola
        if "id" not in ann:
            errors.append(f"Anotacja {i}: brak pola 'id'")

        if "image_id" not in ann:
            errors.append(f"Anotacja {i}: brak pola 'image_id'")

        if "category_id" not in ann:
            errors.append(f"Anotacja {i}: brak pola 'category_id'")

        # Sprawdź czy jest segmentation LUB bbox
        if "segmentation" not in ann and "bbox" not in ann:
            errors.append(f"Anotacja {i}: brak zarówno 'segmentation' jak i 'bbox'")

        # Sprawdź format segmentation
        if "segmentation" in ann:
            seg = ann["segmentation"]
            if not isinstance(seg, list):
                errors.append(f"Anotacja {i}: 'segmentation' musi być listą")
            elif len(seg) > 0 and not isinstance(seg[0], list):
                errors.append(f"Anotacja {i}: 'segmentation' musi być listą list")
            elif len(seg) > 0 and len(seg[0]) < 6:
                errors.append(f"Anotacja {i}: 'segmentation' musi mieć co najmniej 3 punkty (6 wartości)")

    return len(errors) == 0, errors
