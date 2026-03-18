#!/usr/bin/env python3
"""
Regeneracja pełnego datasetu schematic_* od zera.

Problem: oryginalne parametry generacji (start_seed, min/max components) są nieznane,
więc etykiety nie odpowiadają obrazom. Rozwiązanie: wygenerować nowe obrazy + metadane
+ etykiety YOLO z generatora deterministycznego.

Etapy:
1. Wygeneruj 450 schematic_PNG + metadata JSON (batch_generate.py logic inline)
2. Utwórz poprawne YOLO labels bezpośrednio z metadanych
3. Zastąp schematic_* w merged dataset (synthetic_* i real bez zmian)

Użycie:
    python scripts/regenerate_schematic_dataset.py
    python scripts/regenerate_schematic_dataset.py --dry-run
    python scripts/regenerate_schematic_dataset.py --num-schematics 450 --start-seed 1000

Data: 2026-03-05
"""

import argparse
import json
import math
import os
import random
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("BŁĄD: PIL/Pillow wymagany. pip install Pillow")
    sys.exit(1)


# ── Stałe ──
CLASS_MAP = {"R": 0, "C": 1, "L": 2, "D": 3, "A": 4}
CLASS_NAMES = {0: "resistor", 1: "capacitor", 2: "inductor", 3: "diode", 4: "op_amp"}
CANVAS_SIZE = (1000, 800)


# ═══════════════════════════════════════════════════════════════════════
#  KROK 1: Generator (inline z generate_schematic.py)
# ═══════════════════════════════════════════════════════════════════════

def generate_one_schematic(
    seed: int,
    num_components: int,
    canvas_size: Tuple[int, int] = CANVAS_SIZE,
    output_dir: Path = None,
    filename: str = None,
) -> Dict:
    """
    Generuje jeden schemat syntetyczny (obraz PNG + metadane).

    Logika identyczna jak generate_schematic.py ale inline,
    bez potrzeby subprocess.

    Returns:
        Metadane schematu (config + components)
    """
    rng = random.Random(seed)
    component_types = ["R", "C", "L", "D", "A"]
    margin = 100

    # Generuj komponenty
    components = []
    for i in range(num_components):
        comp_type = rng.choice(component_types)
        x = rng.randint(margin, canvas_size[0] - margin)
        y = rng.randint(margin, canvas_size[1] - margin)

        if comp_type in ["R", "L"]:
            width, height = 60, 20
        elif comp_type == "C":
            width, height = 20, 40
        elif comp_type == "D":
            width, height = 40, 40
        elif comp_type == "A":
            width, height = 80, 60
        else:
            width, height = 50, 50

        rotation = rng.choice([0, 90])

        components.append({
            "id": f"{comp_type}{i + 1}",
            "type": comp_type,
            "position": [x, y],
            "width": width,
            "height": height,
            "rotation": rotation,
        })

    metadata = {
        "config": {
            "seed": seed,
            "num_components": num_components,
            "component_types": component_types,
            "canvas_size": list(canvas_size),
        },
        "components": components,
        "connections": [],
    }

    # Rysuj obraz
    if output_dir and filename:
        img = Image.new("RGB", canvas_size, (255, 255, 255))
        draw = ImageDraw.Draw(img)
        line_color = (0, 0, 0)
        text_color = (0, 0, 0)

        for comp in components:
            cx, cy = comp["position"]
            w, h = comp["width"], comp["height"]
            rot = comp["rotation"]
            label = comp["id"]
            ct = comp["type"]

            if ct == "R":
                _draw_resistor(draw, cx, cy, w, h, rot, label, line_color, text_color)
            elif ct == "C":
                _draw_capacitor(draw, cx, cy, w, h, rot, label, line_color, text_color)
            elif ct == "L":
                _draw_inductor(draw, cx, cy, w, h, rot, label, line_color, text_color)
            elif ct == "D":
                _draw_diode(draw, cx, cy, w, h, rot, label, line_color, text_color)
            elif ct == "A":
                _draw_op_amp(draw, cx, cy, w, h, rot, label, line_color, text_color)

        img_path = output_dir / f"{filename}.png"
        img.save(str(img_path), "PNG")

        meta_path = output_dir / f"{filename}.json"
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

    return metadata


# ── Funkcje rysowania (1:1 z generate_schematic.py) ──

def _draw_resistor(draw, x, y, width, height, rotation, label, lc, tc):
    if rotation == 0:
        bbox = [x - width // 2, y - height // 2, x + width // 2, y + height // 2]
        draw.rectangle(bbox, outline=lc, width=2)
        draw.line([x - width // 2 - 20, y, x - width // 2, y], fill=lc, width=2)
        draw.line([x + width // 2, y, x + width // 2 + 20, y], fill=lc, width=2)
    else:
        bbox = [x - height // 2, y - width // 2, x + height // 2, y + width // 2]
        draw.rectangle(bbox, outline=lc, width=2)
        draw.line([x, y - width // 2 - 20, x, y - width // 2], fill=lc, width=2)
        draw.line([x, y + width // 2, x, y + width // 2 + 20], fill=lc, width=2)
    draw.text((x + 15, y - 20), label, fill=tc)


def _draw_capacitor(draw, x, y, width, height, rotation, label, lc, tc):
    if rotation == 0:
        draw.line([x - 5, y - height // 2, x - 5, y + height // 2], fill=lc, width=2)
        draw.line([x + 5, y - height // 2, x + 5, y + height // 2], fill=lc, width=2)
        draw.line([x - 20, y, x - 5, y], fill=lc, width=2)
        draw.line([x + 5, y, x + 20, y], fill=lc, width=2)
    else:
        draw.line([x - height // 2, y - 5, x + height // 2, y - 5], fill=lc, width=2)
        draw.line([x - height // 2, y + 5, x + height // 2, y + 5], fill=lc, width=2)
        draw.line([x, y - 20, x, y - 5], fill=lc, width=2)
        draw.line([x, y + 5, x, y + 20], fill=lc, width=2)
    draw.text((x + 15, y - 20), label, fill=tc)


def _draw_inductor(draw, x, y, width, height, rotation, label, lc, tc):
    """Rysuje symbol cewki — seria 3 łuków (klasyczny IEC/ANSI)."""
    num_bumps = 3
    if rotation == 0:
        bump_w = width / num_bumps
        start_x = x - width // 2
        draw.line([x - width // 2 - 20, y, x - width // 2, y], fill=lc, width=2)
        draw.line([x + width // 2, y, x + width // 2 + 20, y], fill=lc, width=2)
        for i in range(num_bumps):
            bx = start_x + i * bump_w
            arc_bbox = [bx, y - height // 2, bx + bump_w, y + height // 2]
            draw.arc(arc_bbox, start=180, end=0, fill=lc, width=2)
    else:
        bump_h = width / num_bumps
        start_y = y - width // 2
        draw.line([x, y - width // 2 - 20, x, y - width // 2], fill=lc, width=2)
        draw.line([x, y + width // 2, x, y + width // 2 + 20], fill=lc, width=2)
        for i in range(num_bumps):
            by = start_y + i * bump_h
            arc_bbox = [x - height // 2, by, x + height // 2, by + bump_h]
            draw.arc(arc_bbox, start=270, end=90, fill=lc, width=2)
    draw.text((x + 15, y - 20), label, fill=tc)


def _draw_diode(draw, x, y, width, height, rotation, label, lc, tc):
    """Rysuje symbol diody — losowy wariant (standard/zener/LED), wypełniony trójkąt + kreska."""
    variant = (x * 31 + y * 17) % 3  # 0=standard, 1=zener, 2=LED
    if rotation == 0:
        tri = [(x - width // 4, y - height // 2),
               (x - width // 4, y + height // 2),
               (x + width // 4, y)]
        draw.polygon(tri, fill=lc, outline=lc, width=2)
        kx = x + width // 4
        ky_top, ky_bot = y - height // 2, y + height // 2
        if variant == 1:  # Zener
            bend = height // 6
            draw.line([kx, ky_top, kx - bend, ky_top - bend], fill=lc, width=2)
            draw.line([kx, ky_top, kx, ky_bot], fill=lc, width=2)
            draw.line([kx, ky_bot, kx + bend, ky_bot + bend], fill=lc, width=2)
        else:
            draw.line([kx, ky_top, kx, ky_bot], fill=lc, width=2)
        draw.line([x - width // 2, y, x - width // 4, y], fill=lc, width=2)
        draw.line([x + width // 4, y, x + width // 2, y], fill=lc, width=2)
        if variant == 2:  # LED — strzałki emisji ~22° od normalnej
            for i in range(2):
                t = 0.3 + i * 0.35
                sx = int((x - width / 4) + t * (width / 2)) + 2
                sy = int((y - height / 2) + t * (height / 2)) - 2
                ex, ey = sx + 12, sy - 5
                draw.line([sx, sy, ex, ey], fill=lc, width=2)
                draw.line([ex, ey, ex - 5, ey + 1], fill=lc, width=2)
                draw.line([ex, ey, ex - 3, ey + 4], fill=lc, width=2)
    else:  # 90°
        tri = [(x - height // 2, y - width // 4),
               (x + height // 2, y - width // 4),
               (x, y + width // 4)]
        draw.polygon(tri, fill=lc, outline=lc, width=2)
        ky = y + width // 4
        kx_left, kx_right = x - height // 2, x + height // 2
        if variant == 1:  # Zener
            bend = height // 6
            draw.line([kx_left, ky, kx_left - bend, ky - bend], fill=lc, width=2)
            draw.line([kx_left, ky, kx_right, ky], fill=lc, width=2)
            draw.line([kx_right, ky, kx_right + bend, ky + bend], fill=lc, width=2)
        else:
            draw.line([kx_left, ky, kx_right, ky], fill=lc, width=2)
        draw.line([x, y - width // 2, x, y - width // 4], fill=lc, width=2)
        draw.line([x, y + width // 4, x, y + width // 2], fill=lc, width=2)
        if variant == 2:  # LED — strzałki emisji ~22° od pionu
            for i in range(2):
                t = 0.3 + i * 0.35
                sx = int((x + height / 2) + t * (-height / 2)) + 2
                sy = int((y - width / 4) + t * (width / 2)) + 2
                ex, ey = sx + 5, sy + 12
                draw.line([sx, sy, ex, ey], fill=lc, width=2)
                draw.line([ex, ey, ex - 1, ey - 5], fill=lc, width=2)
                draw.line([ex, ey, ex - 4, ey - 3], fill=lc, width=2)
    draw.text((x + 15, y - 20), label, fill=tc)


def _draw_op_amp(draw, x, y, width, height, rotation, label, lc, tc):
    if rotation in {0, 180}:
        triangle = [(x - width // 2, y - height // 2), (x - width // 2, y + height // 2), (x + width // 2, y)]
        draw.polygon(triangle, outline=lc, width=2)
        in_y_offset = height // 4
        draw.line([(x - width // 2 - 25, y - in_y_offset), (x - width // 2, y - in_y_offset)], fill=lc, width=2)
        draw.line([(x - width // 2 - 25, y + in_y_offset), (x - width // 2, y + in_y_offset)], fill=lc, width=2)
        draw.text((x - width // 2 - 35, y - in_y_offset - 8), "+", fill=tc)
        draw.text((x - width // 2 - 35, y + in_y_offset - 8), "-", fill=tc)
        draw.line([(x + width // 2, y), (x + width // 2 + 30, y)], fill=lc, width=2)
    else:
        triangle = [(x - height // 2, y + width // 2), (x + height // 2, y + width // 2), (x, y - width // 2)]
        draw.polygon(triangle, outline=lc, width=2)
        in_x_offset = height // 4
        draw.line([(x - in_x_offset, y + width // 2 + 25), (x - in_x_offset, y + width // 2)], fill=lc, width=2)
        draw.line([(x + in_x_offset, y + width // 2 + 25), (x + in_x_offset, y + width // 2)], fill=lc, width=2)
        draw.text((x - in_x_offset - 8, y + width // 2 + 28), "+", fill=tc)
        draw.text((x + in_x_offset - 8, y + width // 2 + 28), "-", fill=tc)
        draw.line([(x, y - width // 2), (x, y - width // 2 - 30)], fill=lc, width=2)
    draw.text((x + 15, y - 20), label, fill=tc)


# ═══════════════════════════════════════════════════════════════════════
#  KROK 2: Konwersja metadane → YOLO labels (poprawna, bez bugu)
# ═══════════════════════════════════════════════════════════════════════

def metadata_to_yolo_lines(metadata: Dict) -> List[str]:
    """
    Konwertuje metadane na linie YOLO segmentation.

    position = [cx, cy] jest CENTREM komponentu.
    Wielokąt 4-punktowy z uwzględnieniem rotacji.
    """
    canvas_w, canvas_h = metadata["config"]["canvas_size"]
    lines = []

    for comp in metadata["components"]:
        comp_type = comp["type"]
        class_id = CLASS_MAP.get(comp_type)
        if class_id is None:
            continue

        cx, cy = comp["position"]
        w, h = comp["width"], comp["height"]
        rotation = comp.get("rotation", 0)

        # 4 rogi relatywne do centrum
        hw, hh = w / 2.0, h / 2.0
        corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]

        # Rotacja
        angle_rad = math.radians(rotation)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        points = []
        for dx, dy in corners:
            rx = dx * cos_a - dy * sin_a
            ry = dx * sin_a + dy * cos_a
            abs_x = cx + rx
            abs_y = cy + ry
            # Normalizacja 0-1, clamp
            nx = max(0.0, min(1.0, abs_x / canvas_w))
            ny = max(0.0, min(1.0, abs_y / canvas_h))
            points.extend([nx, ny])

        coords_str = " ".join(f"{c:.6f}" for c in points)
        lines.append(f"{class_id} {coords_str}")

    return lines


# ═══════════════════════════════════════════════════════════════════════
#  KROK 3: Batch generacja + budowa merged dataset
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Regeneracja pełnego datasetu schematic_* (nowe obrazy + etykiety)"
    )
    parser.add_argument("--num-schematics", type=int, default=450,
                        help="Liczba schematów do wygenerowania")
    parser.add_argument("--start-seed", type=int, default=1000,
                        help="Seed startowy (domyślnie 1000 — nowa seria)")
    parser.add_argument("--min-components", type=int, default=5,
                        help="Min komponentów per schemat")
    parser.add_argument("--max-components", type=int, default=20,
                        help="Max komponentów per schemat")
    parser.add_argument("--merged-dir", type=str,
                        default="data/yolo_dataset/merged_opamp_14_01_2026",
                        help="Katalog merged dataset")
    parser.add_argument("--dry-run", action="store_true",
                        help="Tylko pokaż plan, nie generuj")
    args = parser.parse_args()

    merged = Path(args.merged_dir)
    tmp_dir = merged / "_regenerated_schematic_tmp"

    print("=" * 70)
    print("  REGENERACJA SCHEMATIC_* OD ZERA")
    print("=" * 70)
    print(f"  Schematów: {args.num_schematics}")
    print(f"  Start seed: {args.start_seed}")
    print(f"  Komponenty: {args.min_components}-{args.max_components}")
    print(f"  Canvas: {CANVAS_SIZE[0]}x{CANVAS_SIZE[1]}")
    print(f"  Merged dir: {merged}")
    print(f"  Dry run: {args.dry_run}")
    print("=" * 70)

    if args.dry_run:
        # Pokaż przykładowe parametry
        rng = random.Random(args.start_seed)
        print("\nPrzykładowe parametry (pierwsze 10):")
        for i in range(min(10, args.num_schematics)):
            nc = rng.randint(args.min_components, args.max_components)
            seed = args.start_seed + i
            print(f"  schematic_{i+1:03d}: seed={seed}, components={nc}")
        return

    # ── Utwórz katalog tymczasowy ──
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # ── Generuj parametry batcha ──
    rng = random.Random(args.start_seed)
    batch_params = []
    for i in range(args.num_schematics):
        nc = rng.randint(args.min_components, args.max_components)
        seed = args.start_seed + i
        batch_params.append((i + 1, seed, nc))

    # ── Generuj schematy + labels ──
    print(f"\n>>> Generowanie {args.num_schematics} schematów...")
    total_annotations = 0
    class_counts = {}

    for idx, seed, nc in batch_params:
        fname = f"schematic_{idx:03d}"

        # Generuj obraz + metadane
        metadata = generate_one_schematic(
            seed=seed,
            num_components=nc,
            canvas_size=CANVAS_SIZE,
            output_dir=tmp_dir,
            filename=fname,
        )

        # Generuj YOLO labels
        yolo_lines = metadata_to_yolo_lines(metadata)
        lbl_path = tmp_dir / f"{fname}.txt"
        with open(lbl_path, "w") as f:
            f.write("\n".join(yolo_lines) + "\n" if yolo_lines else "")

        total_annotations += len(yolo_lines)
        for line in yolo_lines:
            cls = int(line.split()[0])
            class_counts[cls] = class_counts.get(cls, 0) + 1

        if idx % 50 == 0 or idx == args.num_schematics:
            print(f"  [{idx}/{args.num_schematics}] seed={seed}, components={nc}")

    print(f"\n  Wygenerowano: {args.num_schematics} schematów")
    print(f"  Annotacji: {total_annotations}")
    for cls_id in sorted(class_counts):
        print(f"    {CLASS_NAMES[cls_id]:>12}: {class_counts[cls_id]}")

    # ── Zastąp schematic_* w merged dataset ──
    train_images = merged / "train" / "images"
    train_labels = merged / "train" / "labels"

    # Backup starych schematic_*
    backup_dir = merged / "_old_schematic_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n>>> Backup starych schematic_* do {backup_dir}")
    backed_up = 0
    for f in sorted(train_images.iterdir()):
        if f.name.startswith("schematic_") and f.suffix == ".png":
            shutil.move(str(f), str(backup_dir / f.name))
            backed_up += 1
    for f in sorted(train_labels.iterdir()):
        if f.name.startswith("schematic_") and f.suffix == ".txt":
            shutil.move(str(f), str(backup_dir / f.name))
    print(f"  Przeniesiono {backed_up} starych obrazów + etykiet")

    # Kopiuj nowe schematic_* do merged
    print(f"\n>>> Kopiowanie nowych schematic_* do merged dataset...")
    copied = 0
    for f in sorted(tmp_dir.iterdir()):
        if f.suffix == ".png":
            shutil.copy2(str(f), str(train_images / f.name))
            copied += 1
        elif f.suffix == ".txt":
            shutil.copy2(str(f), str(train_labels / f.name))
    print(f"  Skopiowano {copied} obrazów + etykiet")

    # ── Zapisz parametry generacji ──
    gen_info = {
        "date": "2026-03-05",
        "num_schematics": args.num_schematics,
        "start_seed": args.start_seed,
        "min_components": args.min_components,
        "max_components": args.max_components,
        "canvas_size": list(CANVAS_SIZE),
        "total_annotations": total_annotations,
        "class_counts": {CLASS_NAMES[k]: v for k, v in class_counts.items()},
        "batch_params": [
            {"index": idx, "seed": seed, "num_components": nc}
            for idx, seed, nc in batch_params
        ],
    }
    info_path = merged / "schematic_generation_info.json"
    with open(info_path, "w") as f:
        json.dump(gen_info, f, indent=2)
    print(f"\n  Parametry generacji zapisane: {info_path}")

    # ── Cleanup tmp ──
    shutil.rmtree(tmp_dir)
    print(f"  Katalog tymczasowy usunięty")

    # ── Podsumowanie merged ──
    n_images = sum(1 for f in train_images.iterdir() if f.suffix == ".png")
    n_labels = sum(1 for f in train_labels.iterdir() if f.suffix == ".txt")
    n_real = sum(1 for f in train_images.iterdir() if f.name.startswith("schemat_page"))
    n_synth = sum(1 for f in train_images.iterdir() if f.name.startswith("synthetic_"))
    n_schem = sum(1 for f in train_images.iterdir() if f.name.startswith("schematic_"))

    print("\n" + "=" * 70)
    print("  GOTOWE — Merged dataset zaktualizowany")
    print("=" * 70)
    print(f"  Obrazy train:    {n_images}")
    print(f"    schematic_*:   {n_schem}")
    print(f"    synthetic_*:   {n_synth}")
    print(f"    real:          {n_real}")
    print(f"  Etykiety train:  {n_labels}")
    print(f"  Backup starych:  {backup_dir}")
    print("=" * 70)
    print("\n  Następny krok: wizualna weryfikacja")
    print("  python scripts/visualize_dataset_boxes.py \\")
    print(f"      --dataset {merged} \\")
    print("      --output test_data_after_regen \\")
    print("      --splits train")


if __name__ == "__main__":
    main()
