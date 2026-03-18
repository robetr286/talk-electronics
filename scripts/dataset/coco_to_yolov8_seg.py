#!/usr/bin/env python3
"""Convert COCO segmentation to YOLOv8 segmentation format.

Usage:
  python scripts/dataset/coco_to_yolov8_seg.py \
    --coco data/annotations/coco_seg/labelstudio_export_20251209_batch1_coco.json \
    --images-dir png_dla_label-studio \
    --output-dir data/yolo_dataset/real_batch1
"""
import argparse
import json
import shutil
from pathlib import Path


def coco_to_yolo_seg(coco_path: Path, images_dir: Path, output_dir: Path):
    """Convert COCO instance segmentation to YOLOv8 format."""
    # Load COCO
    with open(coco_path, "r", encoding="utf-8") as f:
        coco_data = json.load(f)

    images = {img["id"]: img for img in coco_data["images"]}
    categories = {cat["id"]: cat for cat in coco_data["categories"]}

    # Create YOLOv8 directory structure
    output_dir = Path(output_dir)
    images_out = output_dir / "images"
    labels_out = output_dir / "labels"
    images_out.mkdir(parents=True, exist_ok=True)
    labels_out.mkdir(parents=True, exist_ok=True)

    # Group annotations by image
    anns_by_image = {}
    for ann in coco_data["annotations"]:
        img_id = ann["image_id"]
        anns_by_image.setdefault(img_id, []).append(ann)

    # Convert each image
    for img_id, img_info in images.items():
        img_filename = img_info["file_name"]
        img_path = images_dir / img_filename

        if not img_path.exists():
            print(f"⚠️  Image not found: {img_path}")
            continue

        # Copy image
        shutil.copy(img_path, images_out / img_filename)

        # Convert annotations to YOLO format
        img_w = img_info["width"]
        img_h = img_info["height"]
        anns = anns_by_image.get(img_id, [])

        label_lines = []
        for ann in anns:
            # Skip annotations without segmentation or if it's ignore_region
            cat_name = categories[ann["category_id"]]["name"]
            if cat_name == "ignore_region":
                continue

            if "segmentation" not in ann or not ann["segmentation"]:
                continue

            # YOLO format: <class_id> <x1> <y1> <x2> <y2> ... (normalized)
            # Category ID in YOLO is 0-indexed
            class_id = ann["category_id"] - 1  # Adjust if needed

            for seg in ann["segmentation"]:
                # Normalize coordinates
                normalized_pts = []
                for i in range(0, len(seg), 2):
                    x_norm = seg[i] / img_w
                    y_norm = seg[i + 1] / img_h
                    normalized_pts.extend([x_norm, y_norm])

                # Format: class_id x1 y1 x2 y2 ...
                line = f"{class_id} " + " ".join([f"{pt:.6f}" for pt in normalized_pts])
                label_lines.append(line)

        # Save label file
        label_filename = Path(img_filename).stem + ".txt"
        label_path = labels_out / label_filename
        with open(label_path, "w") as f:
            f.write("\n".join(label_lines))

    print(f"✅ Converted {len(images)} images to YOLOv8 format")
    print(f"   Images: {images_out}")
    print(f"   Labels: {labels_out}")

    # Generate dataset.yaml
    yaml_content = f"""# YOLOv8 segmentation dataset config
path: {output_dir.absolute()}
train: images
val: images
test: images

# Classes
names:
"""
    # Add class names (sorted by ID)
    sorted_cats = sorted(categories.values(), key=lambda x: x["id"])
    for cat in sorted_cats:
        if cat["name"] != "ignore_region":  # Skip ignore regions
            yaml_content += f"  {cat['id'] - 1}: {cat['name']}\n"

    yaml_path = output_dir / "dataset.yaml"
    with open(yaml_path, "w") as f:
        f.write(yaml_content)

    print(f"✅ Generated dataset config: {yaml_path}")


def main():
    parser = argparse.ArgumentParser(description="Convert COCO to YOLOv8 segmentation format")
    parser.add_argument("--coco", type=Path, required=True, help="Path to COCO JSON file")
    parser.add_argument("--images-dir", type=Path, required=True, help="Directory with source images")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory for YOLO dataset")
    args = parser.parse_args()

    print("📖 Converting COCO to YOLOv8 segmentation format...")
    coco_to_yolo_seg(args.coco, args.images_dir, args.output_dir)
    print("\n✅ Conversion complete!")


if __name__ == "__main__":
    main()
