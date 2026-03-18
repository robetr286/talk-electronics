#!/usr/bin/env python3
"""
Export Label Studio annotations (rotated rectangles + polygons) to COCO instance segmentation format.

This script handles:
- RectangleLabels with rotation → converted to 4-corner polygons
- PolygonLabels → used directly
- Mixed formats in same export → unified to COCO segmentation

Usage:
    python scripts/export_labelstudio_to_coco_seg.py \
        --input data/annotations/labelstudio_exports/project_2025-11-06.json \
        --output data/annotations/coco_seg/train.json \
        --images-dir data/images
"""

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image


def rotated_rect_to_polygon(
    x_pct: float, y_pct: float, w_pct: float, h_pct: float, rotation_deg: float, img_w: int, img_h: int
) -> List[float]:
    """Convert rotated rectangle to 4-corner polygon coordinates.

    Args:
        x_pct, y_pct, w_pct, h_pct: Rectangle in % (Label Studio format, 0-100)
        rotation_deg: Rotation angle in degrees (clockwise from Label Studio)
        img_w, img_h: Image dimensions in pixels

    Returns:
        List of [x1, y1, x2, y2, x3, y3, x4, y4] in absolute pixels
    """
    # Convert to absolute pixels
    x = (x_pct / 100) * img_w
    y = (y_pct / 100) * img_h
    w = (w_pct / 100) * img_w
    h = (h_pct / 100) * img_h

    # Center coordinates
    cx = x + w / 2
    cy = y + h / 2

    # Rotation in radians (Label Studio uses clockwise, convert to standard counter-clockwise)
    angle = math.radians(-rotation_deg)  # Negate for counter-clockwise
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)

    # Four corners (relative to center, before rotation)
    # Order: top-left, top-right, bottom-right, bottom-left
    corners = [
        (-w / 2, -h / 2),  # Top-left
        (w / 2, -h / 2),  # Top-right
        (w / 2, h / 2),  # Bottom-right
        (-w / 2, h / 2),  # Bottom-left
    ]

    # Rotate and translate corners
    polygon = []
    for dx, dy in corners:
        x_rot = cx + (dx * cos_a - dy * sin_a)
        y_rot = cy + (dx * sin_a + dy * cos_a)
        polygon.extend([x_rot, y_rot])

    return polygon


def polygon_to_segmentation(points_pct: List[List[float]], img_w: int, img_h: int) -> List[float]:
    """Convert Label Studio polygon (%) to COCO segmentation (absolute pixels).

    Args:
        points_pct: List of [x, y] in % (0-100)
        img_w, img_h: Image dimensions

    Returns:
        Flattened list of [x1, y1, x2, y2, ...] in absolute pixels
    """
    segmentation = []
    for point in points_pct:
        x = (point[0] / 100) * img_w
        y = (point[1] / 100) * img_h
        segmentation.extend([x, y])
    return segmentation


def get_image_dimensions(image_path: Path) -> Tuple[int, int]:
    """Get image dimensions (width, height)."""
    try:
        with Image.open(image_path) as img:
            return img.size  # (width, height)
    except Exception as e:
        print(f"Warning: Could not read image {image_path}: {e}")
        return (1000, 1000)  # Fallback


def convert_labelstudio_to_coco_seg(
    labelstudio_json: Path, output_json: Path, images_dir: Path, class_mapping: Dict[str, int]
):
    """
    Convert Label Studio export to COCO instance segmentation format.

    Handles both:
    - RectangleLabels (with rotation) → converted to 4-corner polygons
    - PolygonLabels → used directly

    Args:
        labelstudio_json: Path to Label Studio export JSON
        output_json: Path to save COCO JSON
        images_dir: Directory containing images
        class_mapping: Dict mapping class names to category IDs
    """
    print(f"📖 Reading Label Studio export: {labelstudio_json}")
    with open(labelstudio_json, "r", encoding="utf-8") as f:
        ls_data = json.load(f)

    print(f"📦 Found {len(ls_data)} tasks")

    coco = {
        "images": [],
        "annotations": [],
        "categories": [
            {"id": cat_id, "name": cat_name} for cat_name, cat_id in sorted(class_mapping.items(), key=lambda x: x[1])
        ],
        "info": {
            "description": "Talk Electronics Symbol Detection Dataset",
            "version": "1.0",
            "year": 2025,
            "contributor": "Talk Electronics Team",
            "date_created": "2025-11-06",
        },
    }

    annotation_id = 1
    skipped_tasks = 0
    skipped_annotations = 0

    for task_idx, task in enumerate(ls_data, 1):
        # Extract image info
        try:
            image_filename = Path(task["data"]["image"]).name

            # Try to get dimensions from task data or image file
            if "width" in task["data"] and "height" in task["data"]:
                img_w = task["data"]["width"]
                img_h = task["data"]["height"]
            else:
                # Try to read from actual image
                image_path = images_dir / image_filename
                img_w, img_h = get_image_dimensions(image_path)

            image_id = task.get("id", task_idx)

            coco["images"].append({"id": image_id, "file_name": image_filename, "width": img_w, "height": img_h})

        except (KeyError, TypeError) as e:
            print(f"⚠️  Skipping task {task_idx}: Missing image data ({e})")
            skipped_tasks += 1
            continue

        # Process annotations
        if "annotations" not in task or not task["annotations"]:
            continue

        for annotation_group in task["annotations"]:
            if "result" not in annotation_group:
                continue

            for result in annotation_group["result"]:
                try:
                    value = result["value"]

                    # Handle RectangleLabels (with optional rotation)
                    if result["type"] == "rectanglelabels":
                        label = value.get("rectanglelabels", [None])[0]
                        if label not in class_mapping:
                            print(f"⚠️  Unknown class '{label}', skipping")
                            skipped_annotations += 1
                            continue

                        # If this rectangle result contains 'points', treat as polygon
                        if isinstance(value, dict) and "points" in value:
                            points_pct = value["points"]
                            segmentation = polygon_to_segmentation(points_pct, img_w, img_h)
                            rotation = None
                            annotation_method = "rectangle_as_polygon"
                        else:
                            rotation = value.get("rotation", 0)

                            # Convert rotated rectangle to polygon
                            segmentation = rotated_rect_to_polygon(
                                value["x"], value["y"], value["width"], value["height"], rotation, img_w, img_h
                            )

                            annotation_method = "rotated_rectangle"

                    # Handle PolygonLabels
                    elif result["type"] == "polygonlabels":
                        label = value["polygonlabels"][0]
                        if label not in class_mapping:
                            print(f"⚠️  Unknown class '{label}', skipping")
                            skipped_annotations += 1
                            continue

                        # Extract points from Label Studio format
                        points_pct = value["points"]
                        segmentation = polygon_to_segmentation(points_pct, img_w, img_h)
                        rotation = None
                        annotation_method = "polygon"

                    else:
                        # Skip other annotation types (e.g., TextArea, Choices)
                        continue

                    # Calculate bounding box from segmentation
                    xs = segmentation[0::2]
                    ys = segmentation[1::2]
                    x_min, x_max = min(xs), max(xs)
                    y_min, y_max = min(ys), max(ys)
                    bbox = [x_min, y_min, x_max - x_min, y_max - y_min]
                    area = bbox[2] * bbox[3]

                    # Create COCO annotation
                    coco_annotation = {
                        "id": annotation_id,
                        "image_id": image_id,
                        "category_id": class_mapping[label],
                        "bbox": bbox,
                        "area": area,
                        "segmentation": [segmentation],  # COCO expects list of polygons
                        "iscrowd": 0,
                        "attributes": {
                            "annotation_method": annotation_method,
                        },
                    }

                    # Add rotation if available (for metadata/debugging)
                    if rotation is not None:
                        coco_annotation["attributes"]["rotation"] = rotation

                    coco["annotations"].append(coco_annotation)
                    annotation_id += 1

                except (KeyError, IndexError, TypeError, ValueError) as e:
                    print(f"⚠️  Error processing annotation in task {image_id}: {e}")
                    skipped_annotations += 1
                    continue

    # Save COCO JSON
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(coco, f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("✅ Conversion complete!")
    print("📊 Summary:")
    print(f"   Images:      {len(coco['images'])}")
    print(f"   Annotations: {len(coco['annotations'])}")
    print(f"   Categories:  {len(coco['categories'])}")
    if skipped_tasks > 0:
        print(f"   ⚠️  Skipped tasks: {skipped_tasks}")
    if skipped_annotations > 0:
        print(f"   ⚠️  Skipped annotations: {skipped_annotations}")
    print(f"💾 Saved to: {output_json}")
    print("=" * 60)

    # Print per-class statistics
    print("\n📈 Annotations per class:")
    class_counts = {}
    for ann in coco["annotations"]:
        cat_id = ann["category_id"]
        cat_name = next(c["name"] for c in coco["categories"] if c["id"] == cat_id)
        class_counts[cat_name] = class_counts.get(cat_name, 0) + 1

    for cat_name, count in sorted(class_counts.items(), key=lambda x: -x[1]):
        print(f"   {cat_name:20s}: {count:4d}")


def main():
    parser = argparse.ArgumentParser(description="Convert Label Studio export to COCO instance segmentation format")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Path to Label Studio export JSON")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Path to save COCO JSON output")
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=Path("data/images"),
        help="Directory containing images (for dimension lookup)",
    )
    parser.add_argument(
        "--class-mapping",
        type=Path,
        default=Path("data/annotations/class_mapping.json"),
        help="Path to class mapping JSON (optional)",
    )

    args = parser.parse_args()

    # Load class mapping
    if args.class_mapping.exists():
        print(f"📖 Loading class mapping from: {args.class_mapping}")
        with open(args.class_mapping) as f:
            class_mapping = json.load(f)
    else:
        print("⚠️  No class mapping found, using default")
        class_mapping = {
            "resistor": 1,
            "capacitor": 2,
            "diode": 3,
            "transistor": 4,
            "op_amp": 5,
            "connector": 6,
            "power_rail": 7,
            "ground": 8,
            "ic_pin": 9,
            "net_label": 10,
            "measurement_point": 11,
            "misc_symbol": 12,
            "ic": 13,
            "inductor": 14,
        }

    convert_labelstudio_to_coco_seg(
        labelstudio_json=args.input, output_json=args.output, images_dir=args.images_dir, class_mapping=class_mapping
    )


if __name__ == "__main__":
    main()
