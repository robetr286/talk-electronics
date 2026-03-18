#!/usr/bin/env python3
"""Helper to create a stratified COCO split and matching YOLO config in one go."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # pragma: no cover - defensive for CLI usage
    sys.path.append(str(ROOT))

from scripts.split_dataset import (  # noqa: E402
    copy_images_to_split,
    create_split_coco,
    get_category_counts_per_image,
    get_image_annotations,
    load_coco,
    save_coco,
    stratified_split,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split COCO dataset and emit YOLO config")
    parser.add_argument("--input", type=Path, required=True, help="Input COCO JSON file")
    parser.add_argument("--images-dir", type=Path, required=False, help="Directory with source images")
    parser.add_argument("--output-dir", type=Path, required=True, help="Where to place split datasets and config")
    parser.add_argument("--name", type=str, default="yolo_split", help="Base name for the YAML config")
    parser.add_argument(
        "--ratios",
        type=float,
        nargs=3,
        default=[0.7, 0.15, 0.15],
        help="Train/val/test split ratios (default: 0.7 0.15 0.15)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--copy-images", action="store_true", help="Copy images into split folders")
    return parser.parse_args()


def _ensure_output_structure(base: Path) -> None:
    for split in ("train", "val", "test"):
        (base / split).mkdir(parents=True, exist_ok=True)


def _build_yaml(path: Path, category_names: Dict[int, str]) -> str:
    lines: List[str] = []
    lines.append(f"path: {path.as_posix()}")
    lines.append("train: train/images")
    lines.append("val: val/images")
    lines.append("test: test/images")
    lines.append(f"nc: {len(category_names)}")
    lines.append("names:")
    for cid, name in sorted(category_names.items()):
        lines.append(f"  {cid}: {name}")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = _parse_args()
    coco = load_coco(str(args.input))
    output_dir: Path = args.output_dir
    _ensure_output_structure(output_dir)

    image_annotations = get_image_annotations(coco)
    category_counts = get_category_counts_per_image(coco, image_annotations)
    train_ids, val_ids, test_ids = stratified_split(coco["images"], category_counts, args.ratios, seed=args.seed)

    splits = {
        "train": train_ids,
        "val": val_ids,
        "test": test_ids,
    }

    for split_name, ids in splits.items():
        split_coco = create_split_coco(coco, ids, image_annotations, split_name)
        save_coco(split_coco, str(output_dir / split_name / "annotations.json"))
        if args.copy_images and args.images_dir:
            copy_images_to_split(split_coco["images"], args.images_dir, output_dir, split_name)

    category_map = {cat["id"]: cat["name"] for cat in coco.get("categories", [])}
    yaml_payload = _build_yaml(output_dir, category_map)
    yaml_path = output_dir / f"{args.name}.yaml"
    yaml_path.write_text(yaml_payload, encoding="utf-8")

    print(f"✅ Split zapisany w: {output_dir}")
    print(f"✅ Konfiguracja YOLO: {yaml_path}")
    if not args.copy_images:
        print("⚠️  --copy-images nie ustawione: upewnij się, że ścieżki do obrazów są dostępne w configu.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
