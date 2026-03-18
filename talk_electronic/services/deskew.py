"""
Moduł do prostowania (deskew) przekrzywionych schematów elektronicznych.

v7 - Implementacja automatycznego wykrywania i korekcji kąta przekrzywienia
używając Hough Lines Transform.
"""

import logging
from typing import Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def detect_skew_angle(image: np.ndarray, debug: bool = False) -> float:
    """
    Wykrywa kąt przekrzywienia obrazu używając Hough Lines.

    Algorytm:
    1. Konwersja do skali szarości
    2. Binaryzacja adaptacyjna
    3. Detekcja krawędzi (Canny)
    4. Wykrycie linii (Hough Lines Transform)
    5. Obliczenie średniej ważonej kątów dominujących linii poziomych

    Args:
        image: Obraz w skali szarości (grayscale) lub kolorowy (BGR)
        debug: Jeśli True, loguje szczegółowe statystyki wszystkich linii

    Returns:
        Kąt w stopniach (dodatni = obrót w prawo, ujemny = w lewo)
        Zwraca 0.0 jeśli nie wykryto linii (obraz prawdopodobnie prosty)
    """
    # Konwersja do skali szarości jeśli kolorowy
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # Binaryzacja adaptacyjna - lepiej wykrywa linie na schematach
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, blockSize=15, C=10)

    # Detekcja krawędzi (Canny)
    edges = cv2.Canny(binary, 50, 150, apertureSize=3)

    # Hough Lines Probabilistic - wykryj linie proste
    # ZMIENIONE PARAMETRY: bardziej czułe wykrywanie
    lines = cv2.HoughLinesP(
        edges,
        rho=1,  # Rozdzielczość w pikselach
        theta=np.pi / 180,  # Rozdzielczość kąta (1 stopień)
        threshold=50,  # OBNIŻONE z 100 - wykrywa więcej linii
        minLineLength=50,  # OBNIŻONE z 100 - akceptuje krótsze linie
        maxLineGap=20,  # ZWIĘKSZONE z 10 - łączy przerywane linie
    )

    if lines is None or len(lines) == 0:
        logger.info("Brak wykrytych linii - obraz prawdopodobnie już prosty lub brak schematów")
        print("⚠️ DESKEW: Brak wykrytych linii")
        return 0.0

    if debug:
        logger.info(f"🔍 DEBUG: Wykryto {len(lines)} linii ogółem")
        print(f"🔍 DESKEW DEBUG: Wykryto {len(lines)} linii ogółem")

    # Oblicz kąty wszystkich wykrytych linii
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]

        # Długość linii - dłuższe linie mają większą wagę
        line_length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

        # Kąt w stopniach względem osi X
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))

        # Normalizuj do zakresu -45° do +45°
        # (ignoruj linie mocno ukośne - prawdopodobnie elementy, nie przekrzywienie)
        if angle < -45:
            angle += 90
        elif angle > 45:
            angle -= 90

        # Zapisz kąt z wagą (długość linii)
        angles.append((angle, line_length))

    if not angles:
        logger.info("Wszystkie linie odrzucone (zbyt ukośne) - obraz prosty")
        return 0.0

    # Separuj linie poziome (±20°) i pionowe (70-90°)
    # ROZSZERZONE zakresy dla lepszego wykrycia przekrzywionych schematów
    horizontal_lines = [(a, l) for a, l in angles if abs(a) <= 20]
    vertical_lines = [(a, l) for a, l in angles if abs(abs(a) - 90) <= 20]

    if debug:
        logger.info(f"🔍 DEBUG: Linie poziome (±20°): {len(horizontal_lines)}")
        logger.info(f"🔍 DEBUG: Linie pionowe (70-90°): {len(vertical_lines)}")
        print(f"🔍 DESKEW: Linie poziome (±20°): {len(horizontal_lines)}")
        print(f"🔍 DESKEW: Linie pionowe (70-90°): {len(vertical_lines)}")
        if horizontal_lines:
            h_angles = [a for a, _ in horizontal_lines]
            h_min = min(h_angles)
            h_max = max(h_angles)
            h_mean = float(np.mean(h_angles))
            h_median = float(np.median(h_angles))
            logger.info(
                "🔍 DEBUG: Kąty poziome: min=%.2f°, max=%.2f°, śr=%.2f°",
                h_min,
                h_max,
                h_mean,
            )
            print(
                "🔍 DESKEW: Kąty poziome: "
                f"min={h_min:.2f}°, max={h_max:.2f}°, śr={h_mean:.2f}°, mediana={h_median:.2f}°"
            )

    # Priorytet: linie poziome (schematy są zwykle orientowane poziomo)
    if horizontal_lines:
        # Średnia ważona kątów linii poziomych (dłuższe linie = większa waga)
        total_weight = sum(l for _, l in horizontal_lines)
        weighted_angle = sum(a * l for a, l in horizontal_lines) / total_weight

        logger.info(
            f"Wykryto {len(horizontal_lines)} linii poziomych, "
            f"średnia ważona: {weighted_angle:.2f}°, "
            f"zakres: [{min(a for a, _ in horizontal_lines):.2f}°, "
            f"{max(a for a, _ in horizontal_lines):.2f}°]"
        )
        print(f"✅ DESKEW: Wykryty kąt (poziome): {weighted_angle:.2f}° (z {len(horizontal_lines)} linii)")

        return weighted_angle
    elif vertical_lines:
        # Jeśli nie ma poziomych, użyj pionowych (rzadki przypadek)
        total_weight = sum(l for _, l in vertical_lines)
        weighted_angle = sum((a - 90) * l for a, l in vertical_lines) / total_weight

        logger.info(
            f"Brak linii poziomych. Wykryto {len(vertical_lines)} linii pionowych, " f"kąt: {weighted_angle:.2f}°"
        )

        return weighted_angle
    else:
        # Fallback: wszystkie linie
        total_weight = sum(l for _, l in angles)
        weighted_angle = sum(a * l for a, l in angles) / total_weight

        logger.info(f"Wykryto {len(angles)} linii mieszanych, " f"średnia ważona: {weighted_angle:.2f}°")

        return weighted_angle


def rotate_image(
    image: np.ndarray, angle: float, background_color: Tuple[int, int, int] = (255, 255, 255)
) -> np.ndarray:
    """
    Obraca obraz o podany kąt z automatycznym paddingiem.

    Args:
        image: Obraz do obrócenia (grayscale lub BGR)
        angle: Kąt w stopniach (dodatni = obrót w prawo, ujemny = w lewo)
        background_color: Kolor tła (domyślnie biały)

    Returns:
        Obrócony obraz z odpowiednim paddingiem (nie przycina krawędzi)
    """
    if abs(angle) < 0.1:  # Ignoruj bardzo małe kąty (poniżej 0.1°)
        logger.info(f"Kąt {angle:.2f}° zbyt mały - pomijam rotację")
        return image.copy()

    # Wymiary obrazu
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)

    # OpenCV używa konwencji dodatni=CCW, więc odwracamy znak aby nasz interfejs
    # zachował semantykę dodatni=obrót w prawo (zgodnie z deskew/detekcją)
    M = cv2.getRotationMatrix2D(center, -angle, scale=1.0)

    # Oblicz nowe wymiary aby pomieścić cały obrócony obraz (bez przycinania)
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))

    # Dostosuj macierz rotacji do nowych wymiarów (translacja środka)
    M[0, 2] += (new_w / 2) - center[0]
    M[1, 2] += (new_h / 2) - center[1]

    # Dla obrazu w skali szarości użyj skalara, dla kolorowego tuple
    if len(image.shape) == 2:
        border_value = background_color[0]  # Użyj pierwszej wartości
    else:
        border_value = background_color

    # Wykonaj rotację
    rotated = cv2.warpAffine(
        image,
        M,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,  # Interpolacja kubiczna (wysoka jakość)
        borderMode=cv2.BORDER_CONSTANT,  # Stałe tło
        borderValue=border_value,  # Kolor tła
    )

    logger.info(f"Obraz obrócony o {angle:.2f}° " f"(z {w}×{h} px do {new_w}×{new_h} px)")

    return rotated


def deskew_image(image: np.ndarray, manual_angle: float = None, debug: bool = True) -> Tuple[np.ndarray, float]:
    """
    Główna funkcja prostowania obrazu.

    Args:
        image: Obraz do wyprostowania
        manual_angle: Opcjonalny ręczny kąt (jeśli None, wykrywa automatycznie)
        debug: Jeśli True, loguje szczegółowe informacje debugowania

    Returns:
        Tuple (wyprostowany_obraz, użyty_kąt_korekcji)
    """
    if manual_angle is not None:
        # Manualny kąt traktujemy jak wykryty przekos: dodatni = obraz przechylony w prawo,
        # więc korekta jest jego negatywem (spójne z gałęzią automatyczną i oczekiwaniem testów).
        correction_angle = -float(manual_angle)
        logger.info("Użyto ręcznego kąta: %s° (korekta = negatyw)", manual_angle)
    else:
        # Automatyczne wykrycie z debugowaniem
        detected_angle = detect_skew_angle(image, debug=debug)
        logger.info(f"Automatycznie wykryty kąt: {detected_angle}°")

        # Korekcja = negatyw wykrytego kąta
        # (jeśli obraz przekrzywiony o +5°, obracamy o -5° aby wyprostować)
        correction_angle = -detected_angle

    # Obroć obraz
    rotated = rotate_image(image, correction_angle)

    return rotated, correction_angle
