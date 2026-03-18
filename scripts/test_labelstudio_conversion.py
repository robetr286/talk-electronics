#!/usr/bin/env python3
"""
Test script to verify Label Studio export and conversion pipeline.

Creates a sample Label Studio export with rotated rectangles and polygons,
then tests the conversion to COCO format.
"""

import json
import subprocess
import sys
from pathlib import Path

# Sample Label Studio export with mixed annotations
SAMPLE_EXPORT = [
    {
        "id": 1,
        "data": {"image": "test_image_001.png", "width": 1000, "height": 800},
        "annotations": [
            {
                "result": [
                    # Rotated rectangle (resistor at 45°)
                    {
                        "type": "rectanglelabels",
                        "value": {
                            "x": 20,
                            "y": 30,
                            "width": 15,
                            "height": 5,
                            "rotation": 45,
                            "rectanglelabels": ["resistor"],
                        },
                    },
                    # Non-rotated rectangle (capacitor at 0°)
                    {
                        "type": "rectanglelabels",
                        "value": {
                            "x": 50,
                            "y": 50,
                            "width": 10,
                            "height": 20,
                            "rotation": 0,
                            "rectanglelabels": ["capacitor"],
                        },
                    },
                    # Polygon (complex shape - diode)
                    {
                        "type": "polygonlabels",
                        "value": {
                            "points": [[70, 40], [75, 35], [80, 40], [80, 50], [75, 55], [70, 50]],
                            "polygonlabels": ["diode"],
                        },
                    },
                    # Quality metadata (these are skipped by converter)
                    {"type": "choices", "value": {"choices": ["clean"]}},
                ]
            }
        ],
    },
    {
        "id": 2,
        "data": {"image": "test_image_002.png", "width": 1200, "height": 900},
        "annotations": [
            {
                "result": [
                    # Rectangle with 90° rotation
                    {
                        "type": "rectanglelabels",
                        "value": {
                            "x": 10,
                            "y": 10,
                            "width": 5,
                            "height": 15,
                            "rotation": 90,
                            "rectanglelabels": ["transistor"],
                        },
                    }
                ]
            }
        ],
    },
]


def create_test_export():
    """Create a test Label Studio export file."""
    output_path = Path("data/annotations/labelstudio_exports/test_export.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_EXPORT, f, indent=2)

    print(f"✅ Created test export: {output_path}")
    print("   Contains: 2 images, 4 annotations (3 rectangles, 1 polygon)")
    return output_path


def verify_coco_output(coco_path: Path):
    """Verify the converted COCO output."""
    if not coco_path.exists():
        print(f"❌ COCO output not found: {coco_path}")
        return False

    with open(coco_path, "r", encoding="utf-8") as f:
        coco = json.load(f)

    print(f"\n✅ COCO output created: {coco_path}")
    print("📊 Contents:")
    print(f"   Images:      {len(coco['images'])}")
    print(f"   Annotations: {len(coco['annotations'])}")
    print(f"   Categories:  {len(coco['categories'])}")

    # Verify annotations
    print("\n🔍 Annotation details:")
    for ann in coco["annotations"]:
        cat_name = next(c["name"] for c in coco["categories"] if c["id"] == ann["category_id"])
        method = ann["attributes"].get("annotation_method", "unknown")
        rotation = ann["attributes"].get("rotation", "N/A")
        seg_points = len(ann["segmentation"][0]) // 2
        method_display = str(method)
        rotation_display = str(rotation)

        print(
            f"   ID {ann['id']}: {cat_name:12s} | Method: {method_display:20s} | "
            f"Rotation: {rotation_display:>5s} | Segmentation points: {seg_points}"
        )

    # Verify expected results
    expected = {"images": 2, "annotations": 4, "categories": 14}

    success = True
    for key, expected_value in expected.items():
        actual_value = len(coco[key])
        if actual_value != expected_value:
            print(f"❌ Expected {expected_value} {key}, got {actual_value}")
            success = False

    if success:
        print("\n✅ All checks passed!")

    return success


def main():
    print("=" * 60)
    print("Testing Label Studio → COCO conversion pipeline")
    print("=" * 60)

    # Step 1: Create test export
    print("\n📝 Step 1: Creating test Label Studio export...")
    test_export_path = create_test_export()

    # Step 2: Run conversion
    print("\n🔄 Step 2: Run conversion script...")
    print("Execute:")
    print("  python scripts/export_labelstudio_to_coco_seg.py \\")
    print(f"      --input {test_export_path} \\")
    print("      --output data/annotations/coco_seg/test_output.json \\")
    print("      --images-dir data/images")
    print()

    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_labelstudio_to_coco_seg.py",
            "--input",
            str(test_export_path),
            "--output",
            "data/annotations/coco_seg/test_output.json",
            "--images-dir",
            "data/images",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    print(result.stdout)
    if result.stderr:
        print("Stderr:", result.stderr)

    # Step 3: Verify output
    print("\n🔍 Step 3: Verifying COCO output...")
    success = verify_coco_output(Path("data/annotations/coco_seg/test_output.json"))

    print("\n" + "=" * 60)
    if success:
        print("✅ TEST PASSED - Pipeline is working correctly!")
    else:
        print("❌ TEST FAILED - Check errors above")
    print("=" * 60)


if __name__ == "__main__":
    main()
