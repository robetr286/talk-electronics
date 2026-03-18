#!/usr/bin/env python3
"""
Wizualizacja bounding-boxów (wielokątów segmentacji) na obrazach datasetu YOLO.

Rysuje kolorowe wielokąty + etykiety klas na każdym obrazie
i zapisuje wynik do katalogu wyjściowego. Służy do wizualnego QA
danych PRZED treningiem detektora.

Użycie:
    python scripts/visualize_dataset_boxes.py \
        --dataset data/yolo_dataset/merged_opamp_14_01_2026 \
        --output test_data_before_training \
        --splits train val test

Autor: Talk_electronic pipeline
Data:  2026-03-05
"""

import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np


# Kolory BGR dla klas (wyraźne, dobrze widoczne na białym i ciemnym tle)
CLASS_COLORS = {
    0: (0, 0, 255),      # resistor  — czerwony
    1: (255, 0, 0),      # capacitor — niebieski
    2: (0, 180, 0),      # inductor  — zielony
    3: (0, 165, 255),    # diode     — pomarańczowy
    4: (255, 0, 255),    # op_amp    — magenta
}

CLASS_NAMES = {
    0: "resistor",
    1: "capacitor",
    2: "inductor",
    3: "diode",
    4: "op_amp",
}


def parse_yolo_label(label_path: str) -> list[tuple[int, list[tuple[float, float]]]]:
    """
    Parsuje plik etykiet YOLO w formacie segmentacji.

    Każda linia: class_id x1 y1 x2 y2 ... xn yn
    Współrzędne znormalizowane 0-1.

    Returns:
        Lista krotek (class_id, [(x1,y1), (x2,y2), ...])
    """
    annotations = []
    if not os.path.exists(label_path):
        return annotations

    with open(label_path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:  # class_id + minimum 2 punkty (4 koordynaty)
                continue

            class_id = int(parts[0])
            coords = list(map(float, parts[1:]))

            # Punkty wielokąta
            points = []
            for i in range(0, len(coords), 2):
                if i + 1 < len(coords):
                    points.append((coords[i], coords[i + 1]))

            annotations.append((class_id, points))

    return annotations


def draw_annotations(
    image: np.ndarray,
    annotations: list[tuple[int, list[tuple[float, float]]]],
    class_names: dict[int, str] | None = None,
    class_colors: dict[int, tuple[int, int, int]] | None = None,
) -> np.ndarray:
    """
    Rysuje wielokąty segmentacji i etykiety klas na obrazie.

    Args:
        image: Obraz BGR (OpenCV).
        annotations: Lista (class_id, [(x_norm, y_norm), ...]).
        class_names: Mapowanie class_id → nazwa.
        class_colors: Mapowanie class_id → kolor BGR.

    Returns:
        Obraz z narysowanymi annotacjami.
    """
    if class_names is None:
        class_names = CLASS_NAMES
    if class_colors is None:
        class_colors = CLASS_COLORS

    h, w = image.shape[:2]
    overlay = image.copy()

    for class_id, norm_points in annotations:
        # Denormalizacja punktów
        pts = np.array(
            [(int(x * w), int(y * h)) for x, y in norm_points],
            dtype=np.int32,
        )

        color = class_colors.get(class_id, (128, 128, 128))
        name = class_names.get(class_id, f"cls_{class_id}")

        # Wielokąt — rysuj wypełniony z przezroczystością
        cv2.fillPoly(overlay, [pts], color)

        # Kontur wielokąta — grubsza linia, pełna widoczność
        cv2.polylines(image, [pts], isClosed=True, color=color, thickness=2)

        # Bounding box z wielokąta (min/max)
        x_min, y_min = pts.min(axis=0)
        x_max, y_max = pts.max(axis=0)

        # Etykieta — nad lewym górnym rogiem
        label = f"{name}"
        font_scale = 0.5
        thickness = 1
        (tw, th), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
        )

        # Tło etykiety
        label_y = max(y_min - 4, th + 4)
        cv2.rectangle(
            image,
            (x_min, label_y - th - 4),
            (x_min + tw + 4, label_y + 2),
            color,
            -1,
        )

        # Tekst etykiety (biały na kolorowym tle)
        cv2.putText(
            image,
            label,
            (x_min + 2, label_y - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )

    # Nałóż przezroczystą warstwę wypełnień (alpha=0.2)
    alpha = 0.2
    cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)

    return image


def add_summary_bar(
    image: np.ndarray,
    filename: str,
    annotations: list[tuple[int, list[tuple[float, float]]]],
    split: str,
    class_names: dict[int, str] | None = None,
    class_colors: dict[int, tuple[int, int, int]] | None = None,
) -> np.ndarray:
    """
    Dodaje pasek informacyjny na górze obrazu z nazwą pliku i statystykami.
    """
    if class_names is None:
        class_names = CLASS_NAMES
    if class_colors is None:
        class_colors = CLASS_COLORS

    h, w = image.shape[:2]
    bar_height = 40
    bar = np.zeros((bar_height, w, 3), dtype=np.uint8)
    bar[:] = (40, 40, 40)  # ciemnoszare tło

    # Nazwa pliku i split
    text = f"[{split}] {filename}  |  "
    cv2.putText(
        bar, text, (10, 26),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA,
    )
    x_offset = 10 + cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
    )[0][0]

    # Liczba obiektów per klasa
    class_counts: dict[int, int] = {}
    for class_id, _ in annotations:
        class_counts[class_id] = class_counts.get(class_id, 0) + 1

    for cls_id in sorted(class_counts.keys()):
        color = class_colors.get(cls_id, (128, 128, 128))
        name = class_names.get(cls_id, f"cls_{cls_id}")
        count_text = f"{name}:{class_counts[cls_id]}  "

        cv2.putText(
            bar, count_text, (x_offset, 26),
            cv2.FONT_HERSHEY_SIMPLEX, 0.50, color, 1, cv2.LINE_AA,
        )
        x_offset += cv2.getTextSize(
            count_text, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1
        )[0][0]

    # Łączna liczba
    total_text = f"| total: {len(annotations)}"
    cv2.putText(
        bar, total_text, (x_offset, 26),
        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA,
    )

    return np.vstack([bar, image])


def process_split(
    dataset_dir: Path,
    split: str,
    output_dir: Path,
) -> dict[str, int]:
    """
    Przetwarza jeden split (train/val/test) — rysuje boxy na wszystkich obrazach.

    Returns:
        dict z podsumowaniem: images_processed, total_annotations, per_class_counts
    """
    images_dir = dataset_dir / split / "images"
    labels_dir = dataset_dir / split / "labels"

    if not images_dir.exists():
        print(f"  [SKIP] Brak katalogu: {images_dir}")
        return {"images": 0, "annotations": 0}

    split_output = output_dir / split
    split_output.mkdir(parents=True, exist_ok=True)

    image_files = sorted(
        f for f in images_dir.iterdir()
        if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".tiff")
    )

    stats = {
        "images": 0,
        "images_no_labels": 0,
        "annotations": 0,
        "per_class": {},
    }

    for img_path in image_files:
        label_path = labels_dir / (img_path.stem + ".txt")
        image = cv2.imread(str(img_path))

        if image is None:
            print(f"  [WARN] Nie można wczytać: {img_path.name}")
            continue

        annotations = parse_yolo_label(str(label_path))

        if not annotations:
            stats["images_no_labels"] += 1

        # Rysuj annotacje
        image = draw_annotations(image, annotations)

        # Dodaj pasek informacyjny
        image = add_summary_bar(image, img_path.name, annotations, split)

        # Zapisz
        out_path = split_output / img_path.name
        cv2.imwrite(str(out_path), image)

        # Statystyki
        stats["images"] += 1
        stats["annotations"] += len(annotations)
        for class_id, _ in annotations:
            stats["per_class"][class_id] = stats["per_class"].get(class_id, 0) + 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Wizualizacja bounding-boxów datasetu YOLO na obrazach schematów."
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="data/yolo_dataset/merged_opamp_14_01_2026",
        help="Ścieżka do katalogu datasetu YOLO (z podkatalogami train/val/test).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="test_data_before_training",
        help="Katalog wyjściowy na obrazy z narysowanymi boxami.",
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        default=["train", "val", "test"],
        help="Splity do przetworzenia (domyślnie: train val test).",
    )
    args = parser.parse_args()

    dataset_dir = Path(args.dataset)
    output_dir = Path(args.output)

    if not dataset_dir.exists():
        print(f"BŁĄD: Katalog datasetu nie istnieje: {dataset_dir}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  Wizualizacja bounding-boxów — QA przed treningiem RT-DETR-L")
    print("=" * 70)
    print(f"  Dataset:  {dataset_dir.resolve()}")
    print(f"  Output:   {output_dir.resolve()}")
    print(f"  Splity:   {', '.join(args.splits)}")
    print(f"  Klasy:    {CLASS_NAMES}")
    print("=" * 70)

    grand_total = {"images": 0, "annotations": 0}

    for split in args.splits:
        print(f"\n>>> Przetwarzanie: {split} ...")
        stats = process_split(dataset_dir, split, output_dir)
        grand_total["images"] += stats["images"]
        grand_total["annotations"] += stats["annotations"]

        print(f"    Obrazów:      {stats['images']}")
        print(f"    Bez etykiet:  {stats.get('images_no_labels', 0)}")
        print(f"    Annotacji:    {stats['annotations']}")
        if stats.get("per_class"):
            for cls_id in sorted(stats["per_class"].keys()):
                name = CLASS_NAMES.get(cls_id, f"cls_{cls_id}")
                print(f"      {name}: {stats['per_class'][cls_id]}")

    print("\n" + "=" * 70)
    print(f"  ŁĄCZNIE: {grand_total['images']} obrazów, "
          f"{grand_total['annotations']} annotacji")
    print(f"  Wyniki zapisane w: {output_dir.resolve()}")
    print("=" * 70)

    # Zapisz podsumowanie do pliku tekstowego
    summary_path = output_dir / "SUMMARY.txt"
    with open(summary_path, "w") as f:
        f.write("Wizualizacja bounding-boxów — QA przed treningiem RT-DETR-L\n")
        f.write(f"Dataset: {dataset_dir.resolve()}\n")
        f.write(f"Łącznie: {grand_total['images']} obrazów, "
                f"{grand_total['annotations']} annotacji\n\n")
        f.write("Kolory klas:\n")
        for cls_id, name in CLASS_NAMES.items():
            r, g, b = CLASS_COLORS[cls_id]
            f.write(f"  {cls_id}: {name} — BGR({r},{g},{b})\n")

    print(f"  Podsumowanie: {summary_path}")


if __name__ == "__main__":
    main()
