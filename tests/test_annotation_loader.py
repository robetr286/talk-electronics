"""
Testy dla automatycznego loadera anotacji.
"""

import json
from pathlib import Path

import pytest

from talk_electronic.services.annotation_loader import (
    convert_rotated_to_segmentation,
    detect_annotation_format,
    load_annotations,
    rotated_rect_to_points,
    validate_coco_annotations,
)


@pytest.fixture
def sample_label_studio_annotations(tmp_path):
    """Przykładowe anotacje z Label Studio (z rotacją)."""
    data = {
        "images": [{"id": 1, "file_name": "test.png", "width": 800, "height": 600}],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 1, "bbox": [100, 100, 50, 30], "rotation": 45.0, "area": 1500},
            {"id": 2, "image_id": 1, "category_id": 2, "bbox": [200, 150, 40, 20], "rotation": 0.0, "area": 800},
        ],
        "categories": [{"id": 1, "name": "resistor"}, {"id": 2, "name": "capacitor"}],
    }

    file_path = tmp_path / "label_studio.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    return file_path


@pytest.fixture
def sample_coco_standard(tmp_path):
    """Przykładowe standardowe anotacje COCO (bez rotacji)."""
    data = {
        "images": [{"id": 1, "file_name": "test.png", "width": 800, "height": 600}],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 1,
                "bbox": [100, 100, 50, 30],
                "segmentation": [[100, 100, 150, 100, 150, 130, 100, 130]],
                "area": 1500,
            }
        ],
        "categories": [{"id": 1, "name": "resistor"}],
    }

    file_path = tmp_path / "coco_standard.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    return file_path


def test_detect_label_studio_format(sample_label_studio_annotations):
    """Test wykrywania formatu Label Studio."""
    with open(sample_label_studio_annotations, "r") as f:
        data = json.load(f)

    info = detect_annotation_format(data)

    assert info["needs_conversion"] is True
    assert info["format"] == "label_studio"
    assert info["rotated_count"] == 2
    assert info["total_count"] == 2


def test_detect_coco_standard_format(sample_coco_standard):
    """Test wykrywania standardowego formatu COCO."""
    with open(sample_coco_standard, "r") as f:
        data = json.load(f)

    info = detect_annotation_format(data)

    assert info["needs_conversion"] is False
    assert info["format"] == "coco_standard"
    assert info["rotated_count"] == 0
    assert info["total_count"] == 1


def test_rotated_rect_to_points():
    """Test konwersji rotated rectangle na punkty."""
    # Prostokąt bez rotacji
    points = rotated_rect_to_points(100, 100, 50, 30, 0)

    # Powinno być 8 wartości (4 punkty x 2 współrzędne)
    assert len(points) == 8

    # Sprawdź czy punkty są mniej więcej poprawne (z tolerancją na float)
    # Centrum (100, 100), rozmiar (50, 30), kąt 0°
    expected = [
        75,
        85,  # lewy górny (-w/2, -h/2)
        125,
        85,  # prawy górny (+w/2, -h/2)
        125,
        115,  # prawy dolny (+w/2, +h/2)
        75,
        115,  # lewy dolny (-w/2, +h/2)
    ]

    for i, (actual, exp) in enumerate(zip(points, expected)):
        assert abs(actual - exp) < 1.0, f"Punkt {i}: {actual} != {exp}"


def test_rotated_rect_45_degrees():
    """Test konwersji z rotacją 45 stopni."""
    points = rotated_rect_to_points(100, 100, 50, 30, 45)

    assert len(points) == 8
    # Po rotacji punkty powinny być różne niż bez rotacji
    assert points != rotated_rect_to_points(100, 100, 50, 30, 0)


def test_convert_label_studio_to_segmentation(sample_label_studio_annotations):
    """Test konwersji Label Studio → COCO segmentation."""
    with open(sample_label_studio_annotations, "r") as f:
        data = json.load(f)

    converted = convert_rotated_to_segmentation(data, "label_studio")

    # Sprawdź czy rotation zostało usunięte
    for ann in converted["annotations"]:
        assert "rotation" not in ann
        assert "segmentation" in ann
        assert isinstance(ann["segmentation"], list)
        assert len(ann["segmentation"]) > 0
        assert len(ann["segmentation"][0]) == 8  # 4 punkty × 2 współrzędne


def test_load_annotations_with_conversion(sample_label_studio_annotations):
    """Test całego procesu ładowania z automatyczną konwersją."""
    data = load_annotations(sample_label_studio_annotations)

    # Sprawdź czy dane są w formacie COCO
    assert "annotations" in data
    assert "images" in data
    assert "categories" in data

    # Sprawdź czy wszystkie anotacje mają segmentation
    for ann in data["annotations"]:
        assert "segmentation" in ann
        assert "rotation" not in ann


def test_load_annotations_without_conversion(sample_coco_standard):
    """Test ładowania standardowego COCO (bez konwersji)."""
    data = load_annotations(sample_coco_standard)

    # Powinno zostać bez zmian
    assert "annotations" in data
    assert len(data["annotations"]) == 1
    assert "segmentation" in data["annotations"][0]


def test_validate_coco_annotations_valid(sample_coco_standard):
    """Test walidacji poprawnych anotacji COCO."""
    with open(sample_coco_standard, "r") as f:
        data = json.load(f)

    is_valid, errors = validate_coco_annotations(data)

    assert is_valid is True
    assert len(errors) == 0


def test_validate_coco_annotations_invalid():
    """Test walidacji niepoprawnych anotacji."""
    # Brakuje wymaganych pól
    data = {
        "annotations": [
            {
                "id": 1,
                # Brak image_id, category_id, bbox, segmentation
            }
        ],
        "images": [],
    }

    is_valid, errors = validate_coco_annotations(data)

    assert is_valid is False
    assert len(errors) > 0


def test_load_nonexistent_file():
    """Test ładowania nieistniejącego pliku."""
    with pytest.raises(FileNotFoundError):
        load_annotations(Path("/nonexistent/path/file.json"))


def test_rotated_rect_90_degrees():
    """Test rotacji o 90 stopni."""
    points_0 = rotated_rect_to_points(100, 100, 50, 30, 0)
    points_90 = rotated_rect_to_points(100, 100, 50, 30, 90)

    # Punkty po rotacji 90° powinny być różne
    assert points_0 != points_90

    # Szerokość i wysokość są zamienione (w pewnym sensie)
    # Po rotacji o 90° prostokąt 50×30 → 30×50 (w sensie orientacji)
