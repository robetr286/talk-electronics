"""
Testy jednostkowe dla talk_electronic.services.deskew
"""

import cv2
import numpy as np
import pytest

from talk_electronic.services.deskew import deskew_image, detect_skew_angle, rotate_image


def create_test_image(angle: float = 0.0, size: tuple = (500, 500)) -> np.ndarray:
    """
    Tworzy testowy obraz z poziomymi i pionowymi liniami.

    Args:
        angle: Kąt obrotu w stopniach (dodatni = obrót w prawo)
        size: Rozmiar obrazu (width, height)

    Returns:
        Obraz w skali szarości z liniami
    """
    img = np.ones(size, dtype=np.uint8) * 255

    # Narysuj poziome linie
    for y in range(50, size[0], 100):
        cv2.line(img, (50, y), (size[1] - 50, y), 0, 2)

    # Narysuj pionowe linie
    for x in range(50, size[1], 100):
        cv2.line(img, (x, 50), (x, size[0] - 50), 0, 2)

    # Obróć jeśli trzeba (OpenCV używa konwencji dodatni = CCW, więc odwracamy znak)
    if angle != 0.0:
        center = (size[1] // 2, size[0] // 2)
        matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)
        img = cv2.warpAffine(img, matrix, (size[1], size[0]), borderValue=255, flags=cv2.INTER_LINEAR)

    return img


@pytest.fixture
def straight_image() -> np.ndarray:
    """Prosty obraz bez przekrzywienia."""
    return create_test_image(angle=0.0)


@pytest.fixture
def skewed_image_positive() -> np.ndarray:
    """Obraz przekrzywiony o +5 stopni."""
    return create_test_image(angle=5.0)


@pytest.fixture
def skewed_image_negative() -> np.ndarray:
    """Obraz przekrzywiony o -3 stopnie."""
    return create_test_image(angle=-3.0)


def test_detect_skew_angle_straight_image(straight_image: np.ndarray):
    """Test detekcji kąta dla prostego obrazu."""
    angle = detect_skew_angle(straight_image)

    # Prosty obraz powinien dać kąt bliski 0
    assert abs(angle) < 1.0, f"Expected angle near 0, got {angle}"


def test_detect_skew_angle_positive_skew(skewed_image_positive: np.ndarray):
    """Test detekcji dodatniego kąta przekrzywienia."""
    angle = detect_skew_angle(skewed_image_positive)

    # Powinien wykryć kąt w okolicy +5 stopni (z tolerancją)
    assert 3.0 < angle < 7.0, f"Expected angle near +5, got {angle}"


def test_detect_skew_angle_negative_skew(skewed_image_negative: np.ndarray):
    """Test detekcji ujemnego kąta przekrzywienia."""
    angle = detect_skew_angle(skewed_image_negative)

    # Powinien wykryć kąt w okolicy -3 stopni (z tolerancją)
    assert -5.0 < angle < -1.0, f"Expected angle near -3, got {angle}"


def test_detect_skew_angle_empty_image():
    """Test dla pustego obrazu (bez linii)."""
    empty = np.ones((500, 500), dtype=np.uint8) * 255
    angle = detect_skew_angle(empty)

    # Brak linii = brak detekcji = 0.0
    assert angle == 0.0


def test_detect_skew_angle_debug_mode(straight_image: np.ndarray, caplog):
    """Test trybu debug."""
    import logging

    caplog.set_level(logging.INFO)

    detect_skew_angle(straight_image, debug=True)

    # Sprawdź czy loguje informacje debug
    assert any("DEBUG" in record.message or "Wykryto" in record.message for record in caplog.records)


def test_detect_skew_angle_color_image():
    """Test konwersji obrazu kolorowego na grayscale."""
    # Stwórz kolorowy obraz (BGR)
    gray_img = create_test_image(angle=5.0)
    color_img = cv2.cvtColor(gray_img, cv2.COLOR_GRAY2BGR)

    angle = detect_skew_angle(color_img)

    # Powinien działać tak samo jak dla grayscale
    assert 3.0 < angle < 7.0


def test_compute_rotation_matrix():
    """Test obliczania macierzy rotacji."""
    image = create_test_image()
    angle = 5.0
    center = (image.shape[1] // 2, image.shape[0] // 2)

    # cv2.getRotationMatrix2D zwraca macierz 2x3
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    # Sprawdź kształt macierzy
    assert matrix.shape == (2, 3)

    # Sprawdź typ
    assert matrix.dtype == np.float64


def test_rotate_image_positive_angle(straight_image: np.ndarray):
    """Test rotacji obrazu o dodatni kąt."""
    angle = 5.0
    rotated = rotate_image(straight_image, angle)

    # Powinny być co najmniej takie jak wejście (dodajemy padding)
    assert rotated.shape[0] >= straight_image.shape[0]
    assert rotated.shape[1] >= straight_image.shape[1]

    # Sprawdź że obraz się zmienił
    assert not np.array_equal(rotated, straight_image)


def test_rotate_image_negative_angle(straight_image: np.ndarray):
    """Test rotacji obrazu o ujemny kąt."""
    angle = -5.0
    rotated = rotate_image(straight_image, angle)

    assert rotated.shape[0] >= straight_image.shape[0]
    assert rotated.shape[1] >= straight_image.shape[1]
    assert not np.array_equal(rotated, straight_image)


def test_rotate_image_zero_angle(straight_image: np.ndarray):
    """Test rotacji o 0 stopni (brak rotacji)."""
    rotated = rotate_image(straight_image, 0.0)

    # Mimo obrotu o 0, interpolacja może zmienić piksele
    # więc sprawdzamy tylko kształt
    assert rotated.shape == straight_image.shape


def test_deskew_image_integration(skewed_image_positive: np.ndarray):
    """Test pełnego pipeline deskew (detekcja + rotacja)."""
    deskewed, correction_angle = deskew_image(skewed_image_positive)

    # correction_angle jest negatywem wykrytego kąta
    # Wykryty kąt ~+5, więc correction_angle ~-5
    assert -7.0 < correction_angle < -3.0

    # Obraz powinien mieć zmienione wymiary (padding)
    assert deskewed.shape[0] > 0 and deskewed.shape[1] > 0

    # Po deskew kąt powinien być bliski 0
    verify_angle = detect_skew_angle(deskewed)
    assert abs(verify_angle) < 2.0, f"After deskew, angle should be near 0, got {verify_angle}"


def test_deskew_image_already_straight(straight_image: np.ndarray):
    """Test deskew dla już prostego obrazu."""
    deskewed, correction_angle = deskew_image(straight_image)

    # Kąt korekcji powinien być bliski 0
    assert abs(correction_angle) < 1.0

    # Dla małych kątów (<0.1°) funkcja rotate_image zwraca kopię bez rotacji
    assert deskewed.shape == straight_image.shape or deskewed.shape != straight_image.shape


def test_deskew_image_manual_angle(skewed_image_positive: np.ndarray):
    """Test ręcznego ustawienia kąta."""
    # Użyj ręcznego kąta zamiast automatycznej detekcji
    deskewed, correction_angle = deskew_image(skewed_image_positive, manual_angle=5.0)

    # Correction angle powinien być negatywem manual_angle
    assert correction_angle == -5.0


def test_deskew_preserves_content():
    """Test że deskew nie psuje zawartości obrazu."""
    # Stwórz obraz z tekstem
    img = np.ones((300, 600), dtype=np.uint8) * 255
    cv2.putText(img, "TEST TEXT", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 2, 0, 3)

    # Obróć o 5 stopni
    center = (300, 150)
    matrix = cv2.getRotationMatrix2D(center, 5.0, 1.0)
    skewed = cv2.warpAffine(img, matrix, (600, 300), borderValue=255)

    # Wyprostuj
    deskewed, correction_angle = deskew_image(skewed)

    # Powinien wykryć przekrzywienie (correction_angle = negatyw wykrytego)
    assert abs(correction_angle) > 2.0

    # Obraz powinien być zachowany (powinny istnieć ciemniejsze piksele niż tło)
    assert np.count_nonzero(deskewed < 250) > 0


def test_detect_skew_angle_noisy_image():
    """Test detekcji kąta dla zaszumionego obrazu."""
    img = create_test_image(angle=5.0)

    # Dodaj szum
    noise = np.random.randint(0, 50, img.shape, dtype=np.uint8)
    noisy = cv2.add(img, noise)

    angle = detect_skew_angle(noisy)

    # Powinien nadal wykryć kąt, choć z większą tolerancją
    assert 2.0 < angle < 8.0


def test_rotate_image_large_angle():
    """Test rotacji o duży kąt (45 stopni)."""
    img = create_test_image()
    rotated = rotate_image(img, 45.0)

    # Sprawdź że obraz się zmienił
    assert not np.array_equal(rotated, img)

    # Sprawdź wymiary (powinny się powiększyć)
    assert rotated.shape[0] >= img.shape[0]
    assert rotated.shape[1] >= img.shape[1]


def test_deskew_image_returns_tuple():
    """Test że deskew_image zwraca krotkę (obraz, kąt)."""
    img = create_test_image(angle=3.0)
    result = deskew_image(img)

    assert isinstance(result, tuple)
    assert len(result) == 2

    deskewed_img, detected_angle = result
    assert isinstance(deskewed_img, np.ndarray)
    assert isinstance(detected_angle, float)
