#!/usr/bin/env python3
"""Generate QA report (CSV + overlay images) from COCO annotation file.

Usage:
  python scripts/dataset/generate_coco_qa_report.py \
    --coco data/annotations/coco_seg/labelstudio_export_20251209_batch1_coco.json \
    --images-dir png_dla_label-studio \
    --output-dir data/annotations/qa_reports/batch1 \
    --max-overlays 5
"""
import argparse
import csv
import json
from pathlib import Path
from typing import Dict

import cv2
import numpy as np


def load_coco(coco_path: Path) -> Dict:
    with open(coco_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_csv_summary(coco_data: Dict, output_csv: Path):
    """Generate per-image summary CSV."""
    images = {img["id"]: img for img in coco_data["images"]}
    categories = {cat["id"]: cat["name"] for cat in coco_data["categories"]}

    # Count annotations per image per category
    image_stats = {}
    for ann in coco_data["annotations"]:
        img_id = ann["image_id"]
        cat_id = ann["category_id"]
        if img_id not in image_stats:
            image_stats[img_id] = {"total": 0, "by_category": {}}
        image_stats[img_id]["total"] += 1
        cat_name = categories.get(cat_id, f"unknown_{cat_id}")
        image_stats[img_id]["by_category"][cat_name] = image_stats[img_id]["by_category"].get(cat_name, 0) + 1

    # Write CSV
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["image_id", "filename", "width", "height", "total_annotations", "categories_detail"])

        for img_id, img_info in images.items():
            stats = image_stats.get(img_id, {"total": 0, "by_category": {}})
            cat_detail = "; ".join([f"{cat}={count}" for cat, count in sorted(stats["by_category"].items())])
            writer.writerow(
                [
                    img_id,
                    img_info["file_name"],
                    img_info["width"],
                    img_info["height"],
                    stats["total"],
                    cat_detail,
                ]
            )

    print(f"✅ CSV summary saved to: {output_csv}")


def draw_overlays(coco_data: Dict, images_dir: Path, output_dir: Path, max_count: int = 5, color_by_class: bool = True):
    """Draw annotation overlays on sample images.

    Args:
        color_by_class: If True, all objects of the same class get the same color.
                       If False, each annotation gets a random color.
    """
    images = {img["id"]: img for img in coco_data["images"]}
    categories = {cat["id"]: cat["name"] for cat in coco_data["categories"]}

    # Define consistent colors for each class (if color_by_class=True)
    class_colors = {}
    if color_by_class:
        # Manually designed color palette with maximum contrast (BGR format for OpenCV)
        # Colors chosen to be maximally distinguishable from each other
        predefined_colors = {
            "resistor": (0, 0, 255),  # Jasny czerwony
            "capacitor": (255, 165, 0),  # Jasny niebieski
            "diode": (0, 255, 255),  # Żółty
            "transistor": (255, 0, 255),  # Magenta
            "op_amp": (0, 255, 0),  # Jaskrawy zielony (limonkowy)
            "connector": (128, 0, 128),  # Fioletowy
            "power_rail": (255, 140, 0),  # Ciemny pomarańczowy
            "ground": (0, 100, 0),  # Ciemny zielony (butelkowy)
            "ic_pin": (255, 192, 203),  # Różowy (pink)
            "net_label": (0, 165, 255),  # Pomarańczowy
            "measurement_point": (255, 255, 0),  # Cyjan (jasnoniebieski)
            "misc_symbol": (203, 192, 255),  # Lawendowy
            "ic": (128, 128, 0),  # Oliwkowy (ciemny cyjan)
            "inductor": (0, 255, 127),  # Wiosenna zieleń (spring green)
            "ignore_region": (128, 128, 128),  # Szary
            "broken_line": (139, 69, 19),  # Brązowy (saddle brown)
            "edge_connector": (128, 128, 0),  # Ciemny turkusowy (teal) — BGR for OpenCV corresponds to RGB #008080
        }

        # Map category IDs to colors based on category names
        for cat_id, cat_name in categories.items():
            if cat_name in predefined_colors:
                class_colors[cat_id] = predefined_colors[cat_name]
            else:
                # Fallback to gray for unknown categories
                class_colors[cat_id] = (128, 128, 128)

    # Group annotations by image
    anns_by_image = {}
    for ann in coco_data["annotations"]:
        img_id = ann["image_id"]
        anns_by_image.setdefault(img_id, []).append(ann)

    # Draw overlays for up to max_count images
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for img_id, anns in list(anns_by_image.items())[:max_count]:
        img_info = images[img_id]
        img_path = images_dir / img_info["file_name"]

        if not img_path.exists():
            print(f"⚠️  Image not found: {img_path}")
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            print(f"⚠️  Could not read image: {img_path}")
            continue

        overlay = img.copy()

        # Draw each annotation
        for ann in anns:
            cat_name = categories.get(ann["category_id"], "unknown")

            # Choose color: consistent per class or random per annotation
            if color_by_class:
                color = class_colors.get(ann["category_id"], (128, 128, 128))
            else:
                color = tuple(np.random.randint(50, 255, 3).tolist())

            # Draw segmentation if available
            if "segmentation" in ann and ann["segmentation"]:
                for seg in ann["segmentation"]:
                    pts = np.array(seg, dtype=np.int32).reshape((-1, 1, 2))
                    cv2.polylines(overlay, [pts], isClosed=True, color=color, thickness=2)

            # Draw bbox
            if "bbox" in ann:
                x, y, w, h = [int(v) for v in ann["bbox"]]
                cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 1)

                # Add label
                label = f"{cat_name}"
                cv2.putText(overlay, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Save overlay
        output_path = output_dir / f"overlay_{img_info['file_name']}"
        cv2.imwrite(str(output_path), overlay)
        print(f"✅ Overlay saved: {output_path}")
        count += 1

    print(f"✅ Generated {count} overlay images")


def main():
    parser = argparse.ArgumentParser(description="Generate QA report from COCO annotations")
    parser.add_argument("--coco", type=Path, required=True, help="Path to COCO JSON file")
    parser.add_argument("--images-dir", type=Path, required=True, help="Directory with source images")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory for report")
    parser.add_argument("--max-overlays", type=int, default=5, help="Max number of overlay images to generate")
    args = parser.parse_args()

    print(f"📖 Loading COCO: {args.coco}")
    coco_data = load_coco(args.coco)

    print("📊 Generating CSV summary...")
    csv_path = args.output_dir / "summary.csv"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    generate_csv_summary(coco_data, csv_path)

    print(f"🖼️  Generating overlay images (max {args.max_overlays})...")
    draw_overlays(coco_data, args.images_dir, args.output_dir, max_count=args.max_overlays, color_by_class=True)

    print(f"\n✅ QA report complete! Check: {args.output_dir}")


if __name__ == "__main__":
    main()
