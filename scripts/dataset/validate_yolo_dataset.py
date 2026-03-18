#!/usr/bin/env python3
"""Quick validation of YOLOv8 dataset structure without training.

Usage:
  python scripts/dataset/validate_yolo_dataset.py --dataset data/yolo_dataset/real_batch1
"""
import argparse
from pathlib import Path


def validate_yolo_dataset(dataset_dir: Path):
    """Validate YOLOv8 dataset structure."""
    dataset_dir = Path(dataset_dir)

    # Check required files
    yaml_path = dataset_dir / "dataset.yaml"
    images_dir = dataset_dir / "images"
    labels_dir = dataset_dir / "labels"

    checks = {
        "dataset.yaml exists": yaml_path.exists(),
        "images/ directory exists": images_dir.exists(),
        "labels/ directory exists": labels_dir.exists(),
    }

    print("🔍 Validating YOLOv8 dataset structure...")
    print(f"   Dataset: {dataset_dir}")
    print()

    for check, result in checks.items():
        status = "✅" if result else "❌"
        print(f"   {status} {check}")

    if not all(checks.values()):
        print("\n❌ Dataset validation failed!")
        return False

    # Count images and labels
    images = list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpg"))
    labels = list(labels_dir.glob("*.txt"))

    print("\n📊 Dataset statistics:")
    print(f"   Images: {len(images)}")
    print(f"   Labels: {len(labels)}")

    # Check label files
    missing_labels = []
    for img_path in images:
        label_path = labels_dir / (img_path.stem + ".txt")
        if not label_path.exists():
            missing_labels.append(img_path.name)

    if missing_labels:
        print(f"\n⚠️  Missing label files for {len(missing_labels)} images:")
        for img_name in missing_labels[:5]:
            print(f"      {img_name}")
        if len(missing_labels) > 5:
            print(f"      ... and {len(missing_labels) - 5} more")

    # Sample label file content
    if labels:
        sample_label = labels[0]
        print(f"\n📄 Sample label file: {sample_label.name}")
        with open(sample_label, "r") as f:
            lines = f.readlines()
            print(f"   Lines: {len(lines)}")
            if lines:
                print(f"   First line: {lines[0].strip()}")

    # Read and display dataset.yaml
    print("\n📄 dataset.yaml content:")
    with open(yaml_path, "r") as f:
        print(f.read())

    print("\n✅ Dataset validation complete!")
    print(f"   Ready for training: {len(images)} images with {len(labels)} label files")
    print("\n💡 To train (requires ultralytics):")
    print("   pip install ultralytics")
    print(f"   yolo task=segment mode=train model=yolov8n-seg.pt data={yaml_path} epochs=50 imgsz=640")

    return True


def main():
    parser = argparse.ArgumentParser(description="Validate YOLOv8 dataset structure")
    parser.add_argument("--dataset", type=Path, required=True, help="Path to YOLO dataset directory")
    args = parser.parse_args()

    validate_yolo_dataset(args.dataset)


if __name__ == "__main__":
    main()
