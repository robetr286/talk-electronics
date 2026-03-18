#!/usr/bin/env python3
"""
Fix duplicate filenames in coco_complete_200.json by renaming files and updating JSON.
"""

import json
import shutil
from pathlib import Path


def main():
    # Load data
    input_json = Path("data/synthetic/coco_complete_200.json")
    data = json.load(open(input_json))

    print(f"Input: {input_json}")
    print(f"Images in JSON: {len(data['images'])}")

    # Strategy:
    # IDs 1-50:   schematic_001-050 from images_augmented -> keep names
    # IDs 51-100: schematic_001-050 from images_raw (duplicates) -> rename to schematic_201-250
    # IDs 101-200: schematic_051-150 from images_raw -> keep names

    dest_dir = Path("data/synthetic/images")
    dest_dir.mkdir(exist_ok=True)

    # Remove old images directory if exists
    if dest_dir.exists():
        for f in dest_dir.glob("*.png"):
            f.unlink()

    # Copy images_augmented (001-050)
    print("\n[1/3] Copying images_augmented (001-050)...")
    copied_aug = 0
    for i in range(1, 51):
        src = Path(f"data/synthetic/images_augmented/schematic_{i:03d}.png")
        dst = dest_dir / f"schematic_{i:03d}.png"
        if src.exists():
            shutil.copy2(src, dst)
            copied_aug += 1
    print(f"  Copied: {copied_aug} files")

    # Copy raw 001-050 as 201-250
    print("\n[2/3] Copying images_raw (001-050) with new names (201-250)...")
    copied_renamed = 0
    for i in range(1, 51):
        src = Path(f"data/synthetic/images_raw/schematic_{i:03d}.png")
        dst = dest_dir / f"schematic_{i+200:03d}.png"
        if src.exists():
            shutil.copy2(src, dst)
            copied_renamed += 1
    print(f"  Copied: {copied_renamed} files")

    # Copy raw 051-150 as-is
    print("\n[3/3] Copying images_raw (051-150)...")
    copied_raw = 0
    for i in range(51, 151):
        src = Path(f"data/synthetic/images_raw/schematic_{i:03d}.png")
        dst = dest_dir / f"schematic_{i:03d}.png"
        if src.exists():
            shutil.copy2(src, dst)
            copied_raw += 1
    print(f"  Copied: {copied_raw} files")

    total_copied = copied_aug + copied_renamed + copied_raw
    print(f"\nTotal images copied: {total_copied} (expected 200)")

    # Update JSON filenames for IDs 51-100
    print("\n[4/4] Updating JSON filenames for IDs 51-100...")
    updated_count = 0
    for img in data["images"]:
        if 51 <= img["id"] <= 100:
            # These had schematic_001-050, rename to 201-250
            old_name = img["file_name"]
            num = int(old_name.split("_")[1].split(".")[0])
            new_name = f"schematic_{num+200:03d}.png"
            img["file_name"] = new_name
            updated_count += 1

    print(f"  Updated: {updated_count} entries")

    # Verify no duplicates
    filenames = [img["file_name"] for img in data["images"]]
    unique_filenames = set(filenames)
    print("\nVerification:")
    print(f"  Total images: {len(filenames)}")
    print(f"  Unique filenames: {len(unique_filenames)}")
    print(f"  Duplicates: {len(filenames) - len(unique_filenames)}")

    # Save fixed JSON
    output_path = Path("data/synthetic/coco_fixed_200.json")
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print("\nSuccess!")
    print(f"  Fixed JSON: {output_path}")
    print(f"  Images directory: {dest_dir} ({total_copied} files)")


if __name__ == "__main__":
    main()
