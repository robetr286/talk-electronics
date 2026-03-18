"""
Skrypt do nakładania siatki 4x4 na obraz PNG schematu elektronicznego.
Użycie: python scripts/add_grid_overlay.py <input.png> [output.png]
"""

import sys
from pathlib import Path

import cv2


def add_grid_overlay(input_path: str, output_path: str = None, grid_size: tuple = (4, 4)):
    """
    Nakłada siatkę na obraz PNG.

    Args:
        input_path: Ścieżka do pliku wejściowego PNG
        output_path: Ścieżka do pliku wyjściowego PNG (opcjonalnie)
        grid_size: Rozmiar siatki jako (rows, cols), domyślnie (4, 4)
    """
    # Wczytaj obraz
    img = cv2.imread(input_path)
    if img is None:
        raise ValueError(f"Nie można wczytać obrazu: {input_path}")

    height, width = img.shape[:2]
    rows, cols = grid_size

    # Kolory linii (czerwony BGR format)
    line_color = (0, 0, 255)  # Czerwony
    line_thickness = 2

    # Rysuj linie poziome
    for i in range(1, rows):
        y = int(height * i / rows)
        cv2.line(img, (0, y), (width, y), line_color, line_thickness)

    # Rysuj linie pionowe
    for j in range(1, cols):
        x = int(width * j / cols)
        cv2.line(img, (x, 0), (x, height), line_color, line_thickness)

    # Dodaj etykiety pól (A1, B2, itp.)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1.5
    font_thickness = 3
    text_color = (0, 0, 255)  # Czerwony
    bg_color = (255, 255, 255)  # Białe tło

    labels_col = ["A", "B", "C", "D"]
    labels_row = ["1", "2", "3", "4"]

    for i in range(rows):
        for j in range(cols):
            label = f"{labels_col[j]}{labels_row[i]}"

            # Pozycja etykiety (lewy górny róg każdego pola)
            x = int(width * j / cols) + 10
            y = int(height * i / rows) + 40

            # Wymiary tekstu dla tła
            (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, font_thickness)

            # Rysuj białe tło pod tekstem
            cv2.rectangle(img, (x - 5, y - text_height - 5), (x + text_width + 5, y + 5), bg_color, -1)  # Wypełniony

            # Rysuj tekst
            cv2.putText(img, label, (x, y), font, font_scale, text_color, font_thickness)

    # Ustal ścieżkę wyjściową
    if output_path is None:
        input_file = Path(input_path)
        output_path = str(input_file.parent / f"{input_file.stem}_grid_4x4{input_file.suffix}")

    # Zapisz obraz
    cv2.imwrite(output_path, img)
    print(f"✅ Zapisano obraz z siatką 4x4: {output_path}")
    print(f"📐 Wymiary: {width}x{height} px")
    print(f"📦 Rozmiar każdego pola: ~{width//cols}x{height//rows} px")

    return output_path


def main():
    if len(sys.argv) < 2:
        print("Użycie: python scripts/add_grid_overlay.py <input.png> [output.png]")
        print("\nPrzykład:")
        print("  python scripts/add_grid_overlay.py uploads/f9dc74a1300949d98647a244a7081d33_page_5.png")
        print("  python scripts/add_grid_overlay.py input.png output_with_grid.png")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    # Sprawdź czy plik istnieje
    if not Path(input_path).exists():
        print(f"❌ Błąd: Plik nie istnieje: {input_path}")
        sys.exit(1)

    try:
        add_grid_overlay(input_path, output_path)
    except Exception as e:
        print(f"❌ Błąd: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
