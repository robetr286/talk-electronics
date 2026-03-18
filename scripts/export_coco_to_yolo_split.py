#!/usr/bin/env python3
"""
COCO -> YOLO (segmentation) exporter with split support.
- Synthetics go to train.
- Real images are split into train/val/test.
- Images are copied into the YOLO folder structure.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List


def load_coco(coco_path: Path) -> dict:
    with coco_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_indexes(coco_data: dict) -> tuple[Dict[int, dict], Dict[int, List[dict]]]:
    images = {img["id"]: img for img in coco_data["images"]}
    annotations_by_image: Dict[int, List[dict]] = {}
    for ann in coco_data["annotations"]:
        annotations_by_image.setdefault(ann["image_id"], []).append(ann)
    return images, annotations_by_image


def index_files(search_dirs: list[Path]) -> dict[str, Path]:
    index: dict[str, Path] = {}
    exts = ("*.png", "*.jpg", "*.jpeg")
    for root in search_dirs:
        if not root.exists():
            continue
        for ext in exts:
            for path in root.rglob(ext):
                if path.name in index:
                    continue
                index[path.name] = path
    return index


def split_images(
    images: Dict[int, dict], synthetic_prefixes: list[str], val_frac: float, test_frac: float, seed: int
) -> tuple[list[int], list[int], list[int]]:
    synthetic_ids = [
        img_id for img_id, info in images.items() if info["file_name"].startswith(tuple(synthetic_prefixes))
    ]
    real_ids = [img_id for img_id in images.keys() if img_id not in synthetic_ids]

    rng = random.Random(seed)
    rng.shuffle(real_ids)

    val_count = int(len(real_ids) * val_frac)
    test_count = int(len(real_ids) * test_frac)

    val_ids = real_ids[:val_count]
    test_ids = real_ids[val_count : val_count + test_count]
    train_real_ids = real_ids[val_count + test_count :]
    train_ids = synthetic_ids + train_real_ids

    return train_ids, val_ids, test_ids


def coco_ann_to_yolo_lines(
    annotations: Iterable[dict], class_lookup: dict[int, int], img_w: int, img_h: int
) -> list[str]:
    lines: list[str] = []
    for ann in annotations:
        category_id = ann["category_id"]
        class_idx = class_lookup[category_id]
        segmentation = ann["segmentation"][0]

        normalized: list[float] = []
        for i in range(0, len(segmentation), 2):
            x = max(0.0, min(1.0, segmentation[i] / img_w))
            y = max(0.0, min(1.0, segmentation[i + 1] / img_h))
            normalized.extend([x, y])

        coords = " ".join(f"{c:.6f}" for c in normalized)
        lines.append(f"{class_idx} {coords}")
    return lines


def write_split(
    split_name: str,
    image_ids: list[int],
    images: Dict[int, dict],
    annotations_by_image: Dict[int, List[dict]],
    class_lookup: dict[int, int],
    file_index: dict[str, Path],
    out_root: Path,
) -> tuple[int, int, list[str]]:
    images_dir = out_root / split_name / "images"
    labels_dir = out_root / split_name / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    converted_images = 0
    converted_annotations = 0
    missing_files: list[str] = []

    for image_id in image_ids:
        image_info = images[image_id]
        filename = image_info["file_name"]
        stem = Path(filename).stem
        annotations = annotations_by_image.get(image_id, [])
        if not annotations:
            continue

        src_path = file_index.get(filename)
        if not src_path:
            missing_files.append(filename)
            continue

        lines = coco_ann_to_yolo_lines(annotations, class_lookup, image_info["width"], image_info["height"])
        if not lines:
            continue

        label_path = labels_dir / f"{stem}.txt"
        with label_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        dst_img = images_dir / filename
        dst_img.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_img)

        converted_images += 1
        converted_annotations += len(lines)

    return converted_images, converted_annotations, missing_files


def write_dataset_yaml(out_root: Path, class_names: list[str]) -> None:
    yaml_lines = [
        "# YOLO dataset configuration",
        f"path: {out_root.resolve()}",
        "train: train/images",
        "val: val/images",
        "test: test/images",
        "names:",
    ]
    for idx, name in enumerate(class_names):
        yaml_lines.append(f"  {idx}: {name}")

    yaml_path = out_root / "dataset.yaml"
    with yaml_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(yaml_lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export COCO segmentation to YOLO with real-only val/test")
    parser.add_argument("--input", "-i", type=Path, required=True, help="COCO JSON path")
    parser.add_argument("--output", "-o", type=Path, required=True, help="YOLO output root")
    parser.add_argument(
        "--search-dirs", type=Path, nargs="*", default=[Path("data")], help="Directories to scan for images"
    )
    parser.add_argument(
        "--synthetic-prefix",
        action="append",
        default=["synthetic_", "schematic_"],
        help="Prefixes marking synthetic images",
    )
    parser.add_argument("--val-frac", type=float, default=0.15, help="Fraction of real images for val")
    parser.add_argument("--test-frac", type=float, default=0.15, help="Fraction of real images for test")
    parser.add_argument("--seed", type=int, default=13, help="Random seed for splitting real images")
    args = parser.parse_args()

    coco_data = load_coco(args.input)
    images, annotations_by_image = build_indexes(coco_data)

    categories = sorted(coco_data["categories"], key=lambda x: x["id"])
    class_lookup = {cat["id"]: idx for idx, cat in enumerate(categories)}
    class_names = [cat["name"] for cat in categories]

    if args.val_frac + args.test_frac >= 1:
        raise SystemExit("val_frac + test_frac must be < 1")

    train_ids, val_ids, test_ids = split_images(images, args.synthetic_prefix, args.val_frac, args.test_frac, args.seed)

    file_index = index_files([p for p in args.search_dirs])

    out_root = args.output
    out_root.mkdir(parents=True, exist_ok=True)

    train_stats = write_split("train", train_ids, images, annotations_by_image, class_lookup, file_index, out_root)
    val_stats = write_split("val", val_ids, images, annotations_by_image, class_lookup, file_index, out_root)
    test_stats = write_split("test", test_ids, images, annotations_by_image, class_lookup, file_index, out_root)

    write_dataset_yaml(out_root, class_names)

    def _class_counts(image_ids: list[int]) -> Counter:
        counts: Counter[int] = Counter()
        for img_id in image_ids:
            for ann in annotations_by_image.get(img_id, []):
                counts[class_lookup[ann["category_id"]]] += 1
        return counts

    split_reports = {
        "train": {
            "images": train_stats[0],
            "annotations": train_stats[1],
            "class_counts": {class_names[idx]: count for idx, count in _class_counts(train_ids).items()},
        },
        "val": {
            "images": val_stats[0],
            "annotations": val_stats[1],
            "class_counts": {class_names[idx]: count for idx, count in _class_counts(val_ids).items()},
        },
        "test": {
            "images": test_stats[0],
            "annotations": test_stats[1],
            "class_counts": {class_names[idx]: count for idx, count in _class_counts(test_ids).items()},
        },
    }

    report_path = out_root / "class_report.json"
    report_path.write_text(json.dumps(split_reports, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Split summary:")
    print(f"  Train images: {train_stats[0]} | anns: {train_stats[1]}")
    print(f"  Val images:   {val_stats[0]} | anns: {val_stats[1]}")
    print(f"  Test images:  {test_stats[0]} | anns: {test_stats[1]}")

    def _warn_small(split_name: str, stats: tuple[int, int, list[str]]):
        if stats[0] < 3:
            print(f"[warn] Split {split_name} ma bardzo mało obrazów ({stats[0]}).")

    _warn_small("val", val_stats)
    _warn_small("test", test_stats)

    for split_name, details in split_reports.items():
        if not details["class_counts"]:
            print(f"[warn] Split {split_name} ma 0 anotacji (class_counts puste).")
        else:
            missing = [name for name in class_names if name not in details["class_counts"]]
            if missing:
                print(f"[warn] Split {split_name} nie zawiera klas: {', '.join(missing)}")

    missing = train_stats[2] + val_stats[2] + test_stats[2]
    if missing:
        print("Missing source images (not copied):")
        for name in missing:
            print(f"  {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
