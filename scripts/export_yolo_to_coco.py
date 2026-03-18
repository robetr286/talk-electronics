#!/usr/bin/env python3
"""Convert YOLO-seg label files to COCO instance segmentation JSON.

Assumes YOLO segmentation labels where each line is:
  <class_id> x1 y1 x2 y2 ... xn yn
with coordinates normalized to [0,1].

Usage:
  python scripts/export_yolo_to_coco.py --labels-dir data/yolo_dataset/mix_small/labels \
      --images-dir data/yolo_dataset/mix_small/images --data-yaml data/yolo_dataset/mix_small/dataset.yaml \
      --output data/yolo_dataset/mix_small/coco_annotations.json
"""

import argparse
import json
from pathlib import Path
from typing import List

from PIL import Image


def polygon_area(xs: List[float], ys: List[float]) -> float:
    area = 0.0
    n = len(xs)
    for i in range(n):
        j = (i + 1) % n
        area += xs[i] * ys[j]
        area -= xs[j] * ys[i]
    return abs(area) / 2.0


def compute_bbox_from_poly(coords: List[float]):
    xs = coords[0::2]
    ys = coords[1::2]
    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)
    return [x_min, y_min, x_max - x_min, y_max - y_min]


def parse_args():
    p = argparse.ArgumentParser(description="Convert YOLO-seg labels to COCO JSON")
    p.add_argument("--labels-dir", required=True, type=Path)
    p.add_argument("--images-dir", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--data-yaml", type=Path, default=None, help="Optional YOLO dataset.yaml to read class names")
    return p.parse_args()


def main():
    args = parse_args()
    labels_dir = args.labels_dir
    images_dir = args.images_dir
    out_path = args.output

    # Get class names from data yaml if provided
    class_names = None
    if args.data_yaml and args.data_yaml.exists():
        try:
            import yaml

            data = yaml.safe_load(args.data_yaml.read_text())
            names = data.get("names")
            if isinstance(names, dict):
                # yaml format mapping index->name
                # convert to list sorted by index
                class_names = [names[str(i)] if str(i) in names else names[i] for i in range(len(names))]
            elif isinstance(names, list):
                class_names = names
        except Exception:
            class_names = None

    images = []
    annotations = []
    categories = []

    # Build categories placeholder
    if class_names:
        for idx, name in enumerate(class_names, start=1):
            categories.append({"id": idx, "name": name, "supercategory": "component"})
    else:
        # unknown classes -> leave empty, caller can fill later
        pass

    ann_id = 1
    img_id = 1
    supported_ext = {".png", ".jpg", ".jpeg"}

    for img_path in sorted(images_dir.iterdir()):
        if img_path.suffix.lower() not in supported_ext:
            continue
        stem = img_path.stem

        # open image to get size
        with Image.open(img_path) as im:
            w, h = im.size

        images.append({"id": img_id, "file_name": img_path.name, "width": w, "height": h})

        label_file = labels_dir / f"{stem}.txt"
        if not label_file.exists():
            img_id += 1
            continue

        with open(label_file, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 3:
                    continue
                cls = int(parts[0])
                coords = [float(x) for x in parts[1:]]
                # convert normalized coords to pixels
                pix_coords = []
                for i in range(0, len(coords), 2):
                    x = coords[i] * w
                    y = coords[i + 1] * h
                    pix_coords.extend([x, y])

                seg = [round(float(v), 2) for v in pix_coords]
                bbox = compute_bbox_from_poly(seg)
                xs = seg[0::2]
                ys = seg[1::2]
                area = polygon_area(xs, ys)

                annotations.append(
                    {
                        "id": ann_id,
                        "image_id": img_id,
                        "category_id": cls + 1,
                        "segmentation": [seg],
                        "area": area,
                        "bbox": [float(b) for b in bbox],
                        "iscrowd": 0,
                    }
                )
                ann_id += 1

        img_id += 1

    coco = {"images": images, "annotations": annotations, "categories": categories}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(coco, f, indent=2)

    print(f"Wrote COCO annotations: {out_path} (images: {len(images)}, anns: {len(annotations)})")


if __name__ == "__main__":
    main()
