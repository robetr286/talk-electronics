#!/usr/bin/env python3
"""
Convert COCO segmentation format to YOLO format (for YOLOv8 training).

YOLO format for segmentation:
- Each image has a corresponding .txt file
- Each line: <class_id> <x1> <y1> <x2> <y2> ... <xn> <yn>
- Coordinates are normalized (0-1)
- Polygon points are space-separated

Usage:
    python scripts/export_coco_to_yolo.py \
        --input data/annotations/coco_seg/train.json \
        --output data/annotations/yolo/train \
        --images-dir data/images
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List


def coco_to_yolo_segmentation(coco_json: Path, output_dir: Path, images_dir: Path):
    """
    Convert COCO segmentation format to YOLO format.

    Args:
        coco_json: Path to COCO JSON file
        output_dir: Directory to save YOLO .txt files
        images_dir: Directory containing images (for reference)
    """
    print(f"📖 Reading COCO file: {coco_json}")
    with open(coco_json, "r", encoding="utf-8") as f:
        coco_data = json.load(f)

    # Create output directory structure
    labels_dir = output_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)

    # Build image index: image_id -> image info
    images = {img["id"]: img for img in coco_data["images"]}

    # Build category index: cat_id -> class_index (0-based for YOLO)
    categories = sorted(coco_data["categories"], key=lambda x: x["id"])
    category_to_index = {cat["id"]: idx for idx, cat in enumerate(categories)}

    # Group annotations by image_id
    annotations_by_image: Dict[int, List] = {}
    for ann in coco_data["annotations"]:
        image_id = ann["image_id"]
        if image_id not in annotations_by_image:
            annotations_by_image[image_id] = []
        annotations_by_image[image_id].append(ann)

    print(f"📦 Found {len(images)} images, {len(coco_data['annotations'])} annotations")

    # Process each image
    converted_images = 0
    converted_annotations = 0

    for image_id, image_info in images.items():
        filename = Path(image_info["file_name"]).stem  # Without extension
        img_w = image_info["width"]
        img_h = image_info["height"]

        # Get annotations for this image
        annotations = annotations_by_image.get(image_id, [])
        if not annotations:
            continue

        # Create YOLO label file
        label_file = labels_dir / f"{filename}.txt"

        with open(label_file, "w") as f:
            for ann in annotations:
                # Get class index (0-based)
                category_id = ann["category_id"]
                class_idx = category_to_index[category_id]

                # Get segmentation polygon
                segmentation = ann["segmentation"][0]  # First polygon

                # Normalize coordinates (0-1)
                normalized_coords = []
                for i in range(0, len(segmentation), 2):
                    x = segmentation[i] / img_w
                    y = segmentation[i + 1] / img_h
                    # Clamp to [0, 1]
                    x = max(0.0, min(1.0, x))
                    y = max(0.0, min(1.0, y))
                    normalized_coords.extend([x, y])

                # Write to file: class_id x1 y1 x2 y2 ... xn yn
                coords_str = " ".join(f"{c:.6f}" for c in normalized_coords)
                f.write(f"{class_idx} {coords_str}\n")

                converted_annotations += 1

        converted_images += 1

    # Create dataset.yaml for YOLO
    yaml_path = output_dir / "dataset.yaml"
    class_names = [cat["name"] for cat in categories]

    yaml_content = f"""# YOLO dataset configuration
# Generated from COCO: {coco_json.name}

path: {output_dir.absolute()}  # Dataset root
train: images  # Train images relative to path
val: images    # Val images relative to path

# Classes
names:
"""
    for idx, name in enumerate(class_names):
        yaml_content += f"  {idx}: {name}\n"

    with open(yaml_path, "w") as f:
        f.write(yaml_content)

    # Print summary
    print("\n" + "=" * 60)
    print("✅ Conversion complete!")
    print("📊 Summary:")
    print(f"   Images with labels: {converted_images}")
    print(f"   Total annotations:  {converted_annotations}")
    print(f"   Classes:            {len(class_names)}")
    print(f"💾 Labels saved to:    {labels_dir}")
    print(f"💾 Config saved to:    {yaml_path}")
    print("=" * 60)

    print("\n📋 Class names (YOLO indices):")
    for idx, name in enumerate(class_names):
        print(f"   {idx}: {name}")

    print("💡 Next steps:")
    print(f"   1. Copy/link images to: {output_dir / 'images'}")
    print(f"   2. Train with: yolo segment train data={yaml_path} model=yolov8n-seg.pt")


def main():
    parser = argparse.ArgumentParser(description="Convert COCO segmentation format to YOLO format")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Path to COCO JSON file")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output directory for YOLO format")
    parser.add_argument(
        "--images-dir", type=Path, default=Path("data/images"), help="Directory containing images (for reference)"
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"❌ Error: Input file not found: {args.input}")
        return 1

    coco_to_yolo_segmentation(coco_json=args.input, output_dir=args.output, images_dir=args.images_dir)

    return 0


if __name__ == "__main__":
    exit(main())
