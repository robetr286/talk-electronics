#!/usr/bin/env python
"""
Konwerter metadata JSON → COCO Instance Segmentation format.

Konwertuje metadata z mock generatora schematów (bbox + typ komponentu)
do formatu COCO używanego przez YOLOv8 i Label Studio.

Usage:
    python scripts/synthetic/emit_annotations.py --input-dir data/synthetic/annotations
    --output data/synthetic/coco_annotations.json
"""

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Mapowanie typów komponentów na kategorie COCO wraz z domyślnymi rozmiarami.
COMPONENT_CATEGORIES: Dict[str, Dict] = {
    "R": {"id": 1, "name": "resistor", "supercategory": "passive", "default_size": (140, 40)},
    "C": {"id": 2, "name": "capacitor", "supercategory": "passive", "default_size": (100, 40)},
    "L": {"id": 3, "name": "inductor", "supercategory": "passive", "default_size": (160, 50)},
    "D": {"id": 4, "name": "diode", "supercategory": "semiconductor", "default_size": (120, 40)},
    "A": {"id": 5, "name": "op_amp", "supercategory": "integrated", "default_size": (180, 120)},
}

COMPONENT_TYPE_TO_CLASS = {key: value["name"] for key, value in COMPONENT_CATEGORIES.items()}


class COCOAnnotationBuilder:
    """Utility for constructing COCO-compatible annotation dictionaries."""

    def __init__(self, *, info: Optional[Dict] = None, licenses: Optional[List[Dict]] = None):
        self.images: List[Dict] = []
        self.annotations: List[Dict] = []
        self.info = info or {
            "description": "Synthetic Electronic Schematics Dataset",
            "version": "1.0",
            "year": datetime.now().year,
            "contributor": "Talk_electronic",
            "date_created": datetime.now().isoformat(),
        }
        self.licenses = licenses or [{"id": 1, "name": "MIT", "url": "https://opensource.org/licenses/MIT"}]
        self.categories = [deepcopy(cat) for cat in COMPONENT_CATEGORIES.values()]
        self._annotation_id = 1
        self._image_ids = set()

    def add_image(self, image_id: int, file_name: str, width: int, height: int) -> None:
        self.images.append(
            {
                "id": image_id,
                "width": width,
                "height": height,
                "file_name": file_name,
                "license": 1,
                "date_captured": datetime.now().isoformat(),
            }
        )
        self._image_ids.add(image_id)

    def add_annotation(
        self,
        image_id: int,
        category_id: int,
        bbox: List[float],
        *,
        segmentation: Optional[List[List[float]]] = None,
        area: Optional[float] = None,
        attributes: Optional[Dict] = None,
    ) -> int:
        width = float(bbox[2])
        height = float(bbox[3])
        computed_area = area if area is not None else abs(width * height)
        if segmentation is None:
            x, y, w, h = bbox
            segmentation = [[x, y, x + w, y, x + w, y + h, x, y + h]]

        annotation = {
            "id": self._annotation_id,
            "image_id": image_id,
            "category_id": category_id,
            "bbox": [float(v) for v in bbox],
            "area": float(computed_area),
            "segmentation": segmentation,
            "iscrowd": 0,
            "attributes": attributes or {},
        }
        self.annotations.append(annotation)
        self._annotation_id += 1
        return annotation["id"]

    def category_id_for_type(self, component_type: str) -> Optional[int]:
        cat = COMPONENT_CATEGORIES.get(component_type)
        return cat["id"] if cat else None

    def to_dict(self) -> Dict:
        return {
            "info": self.info,
            "licenses": self.licenses,
            "images": self.images,
            "annotations": self.annotations,
            "categories": self.categories,
        }

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=False)


def estimate_component_bbox(component: Dict) -> List[float]:
    """Estimate a bounding box for generator metadata when explicit size is missing."""

    comp_type = (component.get("type") or "").upper()
    defaults = COMPONENT_CATEGORIES.get(comp_type, {"default_size": (80, 50)})
    default_width, default_height = defaults.get("default_size", (80, 50))

    width = float(component.get("width", default_width))
    height = float(component.get("height", default_height))
    rotation = int(component.get("rotation", 0)) % 180

    if rotation in {90, 270}:
        width, height = height, width

    position = component.get("position", [0.0, 0.0])
    if isinstance(position, dict):
        cx = float(position.get("x", 0.0))
        cy = float(position.get("y", 0.0))
    else:
        cx = float(position[0]) if len(position) >= 1 else 0.0
        cy = float(position[1]) if len(position) >= 2 else 0.0

    top_left_x = cx - width / 2.0
    top_left_y = cy - height / 2.0

    return [top_left_x, top_left_y, width, height]


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Convert synthetic schematic metadata to COCO format")
    parser.add_argument(
        "--input-dir", type=str, required=True, help="Directory with metadata JSON files from generate_schematic.py"
    )
    parser.add_argument("--output", type=str, required=True, help="Output COCO JSON file path")
    parser.add_argument(
        "--images-dir",
        type=str,
        default="data/synthetic/images_raw",
        help="Directory with generated PNG images (for relative paths in COCO)",
    )

    return parser.parse_args()


def bbox_to_segmentation(x: float, y: float, width: float, height: float, rotation: float = 0) -> List[float]:
    """
    Convert bounding box to segmentation polygon (4 corner points).

    Args:
        x: Center X coordinate of the component
        y: Center Y coordinate of the component
        width: Width of bbox
        height: Height of bbox
        rotation: Rotation angle in degrees (0-360)

    Returns:
        List of [x1, y1, x2, y2, x3, y3, x4, y4] coordinates

    Note:
        generate_schematic.py stores position as the CENTER of the component,
        not the top-left corner. Fixed 2026-03-05 (previously x,y were
        incorrectly treated as top-left, causing a (width/2, height/2) offset).
    """
    # x, y are already the center of the component
    cx = x
    cy = y

    # Convert rotation to radians
    angle_rad = math.radians(rotation)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # Four corners (relative to center)
    corners = [
        (-width / 2, -height / 2),  # Top-left
        (width / 2, -height / 2),  # Top-right
        (width / 2, height / 2),  # Bottom-right
        (-width / 2, height / 2),  # Bottom-left
    ]

    # Rotate and translate corners
    segmentation = []
    for dx, dy in corners:
        # Rotate around center
        rotated_x = dx * cos_a - dy * sin_a
        rotated_y = dx * sin_a + dy * cos_a

        # Translate to absolute position
        abs_x = cx + rotated_x
        abs_y = cy + rotated_y

        segmentation.extend([abs_x, abs_y])

    return segmentation


def compute_bbox_from_segmentation(segmentation: List[float]) -> List[float]:
    """
    Compute COCO bbox [x, y, width, height] from segmentation polygon.

    Args:
        segmentation: List of [x1, y1, x2, y2, ...] coordinates

    Returns:
        [x, y, width, height] in COCO format
    """
    xs = segmentation[0::2]
    ys = segmentation[1::2]

    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)

    return [x_min, y_min, x_max - x_min, y_max - y_min]


def compute_area(segmentation: List[float]) -> float:
    """
    Compute area of polygon using Shoelace formula.

    Args:
        segmentation: List of [x1, y1, x2, y2, ...] coordinates

    Returns:
        Area in square pixels
    """
    xs = segmentation[0::2]
    ys = segmentation[1::2]

    area = 0.0
    n = len(xs)

    for i in range(n):
        j = (i + 1) % n
        area += xs[i] * ys[j]
        area -= xs[j] * ys[i]

    return abs(area) / 2.0


def convert_metadata_to_coco(metadata_files: List[Path], images_dir: Path) -> Dict:
    """Convert metadata JSON files to COCO format using ``COCOAnnotationBuilder``."""

    builder = COCOAnnotationBuilder()

    # Process each metadata file
    for image_id, metadata_path in enumerate(metadata_files, start=1):
        # Load metadata
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # Get corresponding image path
        image_filename = metadata_path.stem + ".png"
        image_path = images_dir / image_filename

        if not image_path.exists():
            print(f"[!] Pominięto: brak obrazu {image_path}")
            continue

        # Add image to builder
        canvas_width, canvas_height = metadata["config"]["canvas_size"]
        builder.add_image(image_id=image_id, file_name=image_filename, width=canvas_width, height=canvas_height)

        # Process components as annotations
        for component in metadata["components"]:
            comp_type = component["type"]

            # Skip if component type not mapped
            category_id = builder.category_id_for_type(comp_type)
            if category_id is None:
                print(f"[!] Pominięto nieznany typ: {comp_type}")
                continue

            # Convert bbox to segmentation
            x, y = component["position"]
            width = component["width"]
            height = component["height"]
            rotation = component.get("rotation", 0)

            segmentation = bbox_to_segmentation(x, y, width, height, rotation)
            bbox = compute_bbox_from_segmentation(segmentation)
            area = compute_area(segmentation)

            # Add annotation
            builder.add_annotation(
                image_id=image_id,
                category_id=category_id,
                bbox=bbox,
                segmentation=[segmentation],
                area=area,
                attributes={"designator": component["id"], "rotation": rotation},
            )

    return builder.to_dict()


def main():
    """Main conversion function."""
    args = parse_args()

    input_dir = Path(args.input_dir)
    output_path = Path(args.output)
    images_dir = Path(args.images_dir)

    # Find all metadata JSON files (exclude batch_metadata.json)
    metadata_files = sorted([f for f in input_dir.glob("*.json") if f.name != "batch_metadata.json"])

    if not metadata_files:
        print(f"[X] Nie znaleziono plików metadata w {input_dir}")
        return

    print("[>] Konwersja metadata -> COCO")
    print("=" * 60)
    print(f"Katalog wejściowy: {input_dir}")
    print(f"Katalog obrazów: {images_dir}")
    print(f"Plik wyjściowy: {output_path}")
    print(f"Liczba plików: {len(metadata_files)}")
    print("=" * 60)
    print()

    # Convert to COCO
    coco = convert_metadata_to_coco(metadata_files, images_dir)

    # Save COCO JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(coco, f, indent=2, ensure_ascii=False)

    # Print summary
    print()
    print("=" * 60)
    print("[OK] Ukończono konwersję")
    print(f"  Obrazy: {len(coco['images'])}")
    print(f"  Anotacje: {len(coco['annotations'])}")
    print(f"  Kategorie: {len(coco['categories'])}")
    print("=" * 60)
    print()
    print(f"[*] Plik COCO: {output_path}")
    print()
    print("[*] Kategorie:")
    for cat in coco["categories"]:
        count = sum(1 for ann in coco["annotations"] if ann["category_id"] == cat["id"])
        print(f"  - {cat['name']}: {count} instancji")
    print()
    print("[>] Następny krok:")
    print(f"  python scripts/synthetic/augment_dataset.py --input-dir {images_dir} --annotations {output_path}")


if __name__ == "__main__":
    main()
