#!/usr/bin/env python3
"""
Naprawa etykiet YOLO: korekcja offsetu (width/2, height/2) bezpośrednio w plikach.

Problem: emit_annotations.py::bbox_to_segmentation() traktowała position (x,y)
jako lewy górny róg, gdy w rzeczywistości jest to CENTRUM komponentu.
Wynik: każda anotacja przesunięta o dokładnie (width/2, height/2) pikseli.

Rozwiązanie: odjęcie znanego offsetu od istniejących współrzędnych YOLO.
Offset w znormalizowanych współrzędnych:
  dx = (comp_width / 2) / canvas_width
  dy = (comp_height / 2) / canvas_height

Obsługuje:
  - schematic_001..450 (canvas=1000x800)
  - synthetic_002000..002349 (canvas=zmienny, odczytywany z obrazu)
  - Nie modyfikuje etykiet realnych (schemat_page*)

Użycie:
    python scripts/fix_yolo_label_offset.py
    python scripts/fix_yolo_label_offset.py --dry-run
    python scripts/fix_yolo_label_offset.py --verify-only

Data:  2026-03-05
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from PIL import Image
except ImportError:
    print("BŁĄD: PIL/Pillow nie znalezione. Uruchom: pip install Pillow")
    sys.exit(1)


# ── Rozmiary komponentów wg klasy (unrotated) ──
# class_id: (width, height) w pikselach
COMPONENT_SIZES = {
    0: (60, 20),   # resistor (R)
    1: (20, 40),   # capacitor (C)
    2: (60, 20),   # inductor (L)
    3: (40, 40),   # diode (D)
    4: (80, 60),   # op_amp (A)
}

CLASS_NAMES = {0: "resistor", 1: "capacitor", 2: "inductor", 3: "diode", 4: "op_amp"}


def compute_offset(class_id: int, canvas_w: int, canvas_h: int) -> Tuple[float, float]:
    """
    Oblicza offset w znormalizowanych współrzędnych YOLO do odjęcia.

    Bug dodawał (width/2, height/2) do centrum komponentu PRZED rotacją,
    więc offset jest stały niezależnie od kąta obrotu.

    Returns:
        (dx, dy) — znormalizowany offset do odjęcia od każdego punktu
    """
    w, h = COMPONENT_SIZES[class_id]
    dx = (w / 2.0) / canvas_w
    dy = (h / 2.0) / canvas_h
    return dx, dy


def fix_yolo_line(line: str, canvas_w: int, canvas_h: int) -> str:
    """
    Naprawia jedną linię pliku YOLO labels.

    Format wejściowy:  class_id x1 y1 x2 y2 x3 y3 x4 y4
    Odejmuje offset (width/2, height/2) od każdego punktu.

    Returns:
        Naprawiona linia YOLO
    """
    parts = line.strip().split()
    if len(parts) < 3:
        return line.strip()

    class_id = int(parts[0])
    if class_id not in COMPONENT_SIZES:
        return line.strip()

    dx, dy = compute_offset(class_id, canvas_w, canvas_h)
    coords = [float(p) for p in parts[1:]]

    fixed_coords = []
    for i in range(0, len(coords), 2):
        x = max(0.0, min(1.0, coords[i] - dx))
        y = max(0.0, min(1.0, coords[i + 1] - dy))
        fixed_coords.extend([x, y])

    coords_str = " ".join(f"{c:.6f}" for c in fixed_coords)
    return f"{class_id} {coords_str}"


def get_image_size(image_path: Path) -> Tuple[int, int]:
    """Zwraca (width, height) obrazu."""
    with Image.open(image_path) as img:
        return img.size


def process_split(
    split_dir: Path,
    dry_run: bool = False,
    verify_only: bool = False,
) -> Dict:
    """
    Naprawia etykiety YOLO w jednym splicie (train/val/test).

    Returns:
        Statystyki przetwarzania
    """
    images_dir = split_dir / "images"
    labels_dir = split_dir / "labels"

    if not labels_dir.exists():
        return {"skipped": True, "reason": "no labels dir"}

    stats = {
        "processed": 0,
        "skipped_real": 0,
        "total_annotations": 0,
        "offsets_applied": {},
        "clamped_count": 0,
    }

    # Zbierz syntetyczne pliki etykiet
    label_files = sorted([
        f for f in labels_dir.iterdir()
        if f.suffix == ".txt" and (
            f.stem.startswith("schematic_") or f.stem.startswith("synthetic_")
        )
    ])

    for label_path in label_files:
        stem = label_path.stem
        # Znajdź odpowiadający obraz
        img_path = images_dir / f"{stem}.png"
        if not img_path.exists():
            img_path = images_dir / f"{stem}.jpg"
        if not img_path.exists():
            print(f"  [WARN] Brak obrazu dla {stem}")
            continue

        canvas_w, canvas_h = get_image_size(img_path)

        with open(label_path) as f:
            lines = f.readlines()

        fixed_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            fixed = fix_yolo_line(line, canvas_w, canvas_h)
            fixed_lines.append(fixed)
            stats["total_annotations"] += 1

            # Track offsets
            class_id = int(line.split()[0])
            key = f"{CLASS_NAMES.get(class_id, '?')}@{canvas_w}x{canvas_h}"
            dx, dy = compute_offset(class_id, canvas_w, canvas_h)
            stats["offsets_applied"][key] = f"dx={dx:.6f}, dy={dy:.6f}"

        if not dry_run and not verify_only:
            with open(label_path, "w") as f:
                f.write("\n".join(fixed_lines) + "\n" if fixed_lines else "")

        stats["processed"] += 1

    # Policz realne etykiety (nie modyfikowane)
    real_labels = [f for f in labels_dir.iterdir()
                   if f.suffix == ".txt" and not (
                       f.stem.startswith("schematic_") or f.stem.startswith("synthetic_"))]
    stats["skipped_real"] = len(real_labels)

    return stats


def verify_fix(label_path: Path, canvas_w: int, canvas_h: int) -> List[str]:
    """
    Weryfikuje czy naprawiona etykieta ma sensowne wartości.

    Returns:
        Lista ostrzeżeń (pusta = OK)
    """
    warnings = []
    with open(label_path) as f:
        for i, line in enumerate(f):
            parts = line.strip().split()
            if len(parts) < 3:
                continue
            coords = [float(p) for p in parts[1:]]
            for j in range(0, len(coords), 2):
                x, y = coords[j], coords[j + 1]
                if x == 0 or x == 1 or y == 0 or y == 1:
                    warnings.append(f"  L{i}: punkt clamped to edge ({x:.3f},{y:.3f})")
    return warnings


def main():
    parser = argparse.ArgumentParser(
        description="Naprawa offsetu (width/2, height/2) w syntetycznych etykietach YOLO"
    )
    parser.add_argument(
        "--merged-dir",
        type=str,
        default="data/yolo_dataset/merged_opamp_14_01_2026",
        help="Katalog merged dataset",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tylko pokaż co zostanie naprawione, bez zapisywania",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Weryfikuj istniejące etykiety bez modyfikacji",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Nie twórz backup (domyślnie backup jest tworzony)",
    )
    args = parser.parse_args()

    merged_dir = Path(args.merged_dir)
    if not merged_dir.exists():
        print(f"BŁĄD: Katalog nie istnieje: {merged_dir}")
        sys.exit(1)

    print("=" * 70)
    print("  NAPRAWA ETYKIET YOLO — odjęcie offsetu (width/2, height/2)")
    print("=" * 70)
    print(f"  Merged dataset: {merged_dir}")
    print(f"  Dry run: {args.dry_run}")
    print(f"  Verify only: {args.verify_only}")
    print()
    print("  Offsety wg klasy (px):")
    for cls_id, (w, h) in COMPONENT_SIZES.items():
        print(f"    {CLASS_NAMES[cls_id]:>12}: dx={w/2:.0f}px, dy={h/2:.0f}px")
    print("=" * 70)

    # ── BACKUP ──
    if not args.dry_run and not args.verify_only and not args.no_backup:
        for split in ["train", "val", "test"]:
            labels_dir = merged_dir / split / "labels"
            backup_dir = merged_dir / split / "labels_backup_before_fix"
            if labels_dir.exists() and not backup_dir.exists():
                print(f"\n  Backup {split}: {backup_dir}")
                shutil.copytree(labels_dir, backup_dir)
                n = sum(1 for _ in backup_dir.iterdir())
                print(f"    → {n} plików")
            elif backup_dir.exists():
                print(f"\n  Backup {split}: już istnieje")

    # ── NAPRAWA ──
    total_stats = {"processed": 0, "annotations": 0, "skipped_real": 0}

    for split in ["train", "val", "test"]:
        split_dir = merged_dir / split
        if not split_dir.exists():
            continue

        print(f"\n>>> {split.upper()} ...")
        stats = process_split(split_dir, dry_run=args.dry_run, verify_only=args.verify_only)

        if isinstance(stats.get("skipped"), bool):
            print(f"    Pominięto: {stats.get('reason')}")
            continue

        print(f"    Etykiety syntetyczne naprawione: {stats['processed']}")
        print(f"    Etykiety realne (bez zmian): {stats['skipped_real']}")
        print(f"    Anotacji: {stats['total_annotations']}")

        if stats.get("offsets_applied"):
            print("    Offsety zastosowane:")
            for key, val in sorted(stats["offsets_applied"].items()):
                print(f"      {key}: {val}")

        total_stats["processed"] += stats["processed"]
        total_stats["annotations"] += stats["total_annotations"]
        total_stats["skipped_real"] += stats["skipped_real"]

    # ── PODSUMOWANIE ──
    mode = "DRY RUN" if args.dry_run else ("VERIFY" if args.verify_only else "NAPRAWIONO")
    print("\n" + "=" * 70)
    print(f"  [{mode}]")
    print(f"  Etykiety syntetyczne: {total_stats['processed']}")
    print(f"  Anotacji: {total_stats['annotations']}")
    print(f"  Etykiety realne (nienaruszone): {total_stats['skipped_real']}")
    print("=" * 70)

    if not args.dry_run and not args.verify_only:
        print("\n  Następny krok: wizualna weryfikacja")
        print("  python scripts/visualize_dataset_boxes.py \\")
        print(f"      --dataset {merged_dir} \\")
        print("      --output test_data_after_fix \\")
        print("      --splits train val test")


if __name__ == "__main__":
    main()
