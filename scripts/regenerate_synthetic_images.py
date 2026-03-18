#!/usr/bin/env python3
"""
Regeneracja obrazów synthetic_* na podstawie istniejących metadanych JSON.

Problem: Obrazy synthetic_* mają stare (błędne) symbole inductor i diode.
Rozwiązanie: Odczytaj metadane JSON → wygeneruj nowe obrazy z poprawionymi symbolami.
Etykiety YOLO nie wymagają zmian (pozycje się nie zmieniają).

Użycie:
    python scripts/regenerate_synthetic_images.py
    python scripts/regenerate_synthetic_images.py --dry-run
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("BŁĄD: PIL/Pillow wymagany")
    sys.exit(1)


# Import poprawionych funkcji rysowania
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.regenerate_schematic_dataset import (
    _draw_resistor,
    _draw_capacitor,
    _draw_inductor,
    _draw_diode,
    _draw_op_amp,
)


def regenerate_image_from_metadata(metadata: Dict, output_path: Path):
    """Generuje obraz PNG z metadanych JSON z poprawionymi symbolami."""
    canvas_size = tuple(metadata["config"]["canvas_size"])
    img = Image.new("RGB", canvas_size, (255, 255, 255))
    draw = ImageDraw.Draw(img)
    lc = (0, 0, 0)
    tc = (0, 0, 0)

    for comp in metadata["components"]:
        cx, cy = comp["position"]
        w, h = comp["width"], comp["height"]
        rot = comp["rotation"]
        label = comp["id"]
        ct = comp["type"]

        if ct == "R":
            _draw_resistor(draw, cx, cy, w, h, rot, label, lc, tc)
        elif ct == "C":
            _draw_capacitor(draw, cx, cy, w, h, rot, label, lc, tc)
        elif ct == "L":
            _draw_inductor(draw, cx, cy, w, h, rot, label, lc, tc)
        elif ct == "D":
            _draw_diode(draw, cx, cy, w, h, rot, label, lc, tc)
        elif ct == "A":
            _draw_op_amp(draw, cx, cy, w, h, rot, label, lc, tc)

    img.save(str(output_path), "PNG")


def main():
    parser = argparse.ArgumentParser(description="Regeneracja obrazów synthetic_* z poprawionymi symbolami")
    parser.add_argument("--metadata-dir", type=str,
                        default="data/synthetic_op_amp_boost_14_01_2026/metadata",
                        help="Katalog z metadanymi JSON")
    parser.add_argument("--merged-dir", type=str,
                        default="data/yolo_dataset/merged_opamp_14_01_2026",
                        help="Katalog merged dataset")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    meta_dir = Path(args.metadata_dir)
    merged = Path(args.merged_dir)
    train_images = merged / "train" / "images"

    json_files = sorted(meta_dir.glob("synthetic_*.json"))
    print(f"Znaleziono {len(json_files)} metadanych JSON")
    print(f"Cel: {train_images}")

    if args.dry_run:
        for f in json_files[:5]:
            meta = json.loads(f.read_text())
            c = meta["config"]
            n_comp = len(meta["components"])
            types = {}
            for comp in meta["components"]:
                types[comp["type"]] = types.get(comp["type"], 0) + 1
            print(f"  {f.stem}: seed={c['seed']}, canvas={c['canvas_size']}, "
                  f"components={n_comp}, types={types}")
        return

    regenerated = 0
    skipped = 0

    for jf in json_files:
        img_path = train_images / f"{jf.stem}.png"
        if not img_path.exists():
            skipped += 1
            continue

        meta = json.loads(jf.read_text())
        regenerate_image_from_metadata(meta, img_path)
        regenerated += 1

        if regenerated % 50 == 0:
            print(f"  [{regenerated}/{len(json_files)}] {jf.stem}")

    print(f"\nZregenerowano: {regenerated} obrazów")
    if skipped:
        print(f"Pominięto (brak w merged): {skipped}")

    # Regeneruj również w oryginalnym katalogu
    orig_images = meta_dir.parent / "images"
    if orig_images.exists():
        print(f"\nAktualizacja oryginalnych obrazów: {orig_images}")
        orig_count = 0
        for jf in json_files:
            img_path = orig_images / f"{jf.stem}.png"
            if not img_path.exists():
                continue
            meta = json.loads(jf.read_text())
            regenerate_image_from_metadata(meta, img_path)
            orig_count += 1
        print(f"  Zaktualizowano: {orig_count}")


if __name__ == "__main__":
    main()
