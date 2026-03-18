#!/usr/bin/env python3
"""Sanity checks for real dataset images and Label Studio exports.

Usage:
  python scripts/dataset/validate_real.py --images data/real/images --exports data/annotations/labelstudio_exports

Checks performed:
 - lists image files and basic stats (count, sizes)
 - detects duplicates by SHA1
 - verifies that export JSONs reference existing image filenames
 - prints short summary and non-zero exit code when issues found
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        while True:
            b = fh.read(8192)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def find_images(images_dir: Path) -> List[Path]:
    exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
    result = [p for p in images_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts]
    return sorted(result)


def find_labelstudio_exports(exports_dir: Path) -> List[Path]:
    return sorted([p for p in exports_dir.glob("*.json") if p.is_file()])


def scan_images(images: List[Path]) -> Dict[str, List[str]]:
    hashes: Dict[str, List[str]] = {}
    for p in images:
        h = sha1(p)
        hashes.setdefault(h, []).append(str(p))
    return hashes


def scan_exports(exports: List[Path]) -> Dict[str, List[str]]:
    refs: Dict[str, List[str]] = {}
    for p in exports:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            refs[str(p)] = [f"!ERROR json load: {e}"]
            continue

        # label-studio exports vary in shape — collect referenced filenames
        # (data->image, or annotations->result->value->image)
        found = set()
        if isinstance(data, list):
            for task in data:
                if isinstance(task, dict):
                    d = task.get("data") or task.get("image") or {}
                    if isinstance(d, dict):
                        img = d.get("image") or d.get("url") or d.get("file")
                        if isinstance(img, str):
                            found.add(os.path.basename(img))
                    elif isinstance(d, str):
                        found.add(os.path.basename(d))
        refs[str(p)] = sorted(found)

    return refs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--images", default="data/real/images", help="images dir")
    p.add_argument("--exports", default="data/annotations/labelstudio_exports", help="labelstudio exports dir")
    args = p.parse_args()

    images_dir = Path(args.images)
    exports_dir = Path(args.exports)

    if not images_dir.exists():
        print(f"Images dir not found: {images_dir}")
        raise SystemExit(2)
    if not exports_dir.exists():
        print(f"Exports dir not found: {exports_dir}")
        raise SystemExit(2)

    images = find_images(images_dir)
    exports = find_labelstudio_exports(exports_dir)

    print(f"Found {len(images)} images under {images_dir}")
    sizes = [p.stat().st_size for p in images]
    if sizes:
        print(f"Sizes (bytes) — min {min(sizes)} / max {max(sizes)} / total {sum(sizes)}")

    duplicates = scan_images(images)
    dupe_groups = [v for v in duplicates.values() if len(v) > 1]
    print(f"Duplicate groups: {len(dupe_groups)}")
    if dupe_groups:
        for g in dupe_groups:
            print(" DUPES:")
            for f in g:
                print("  ", f)

    print(f"Found {len(exports)} export json(s) in {exports_dir}")
    if exports:
        refs = scan_exports(exports)
        missing_refs = []
        for jp, files in refs.items():
            if not files:
                print(f" {jp} references ZERO images")
                continue
            for fn in files:
                expected = images_dir / fn
                if not expected.exists():
                    missing_refs.append((jp, fn))

        if missing_refs:
            print("Missing image files referenced in exports:")
            for jp, fn in missing_refs:
                print(f" - {jp} references missing file: {fn}")

    ok = (len(dupe_groups) == 0) and (len(exports) > 0 and not missing_refs)
    if ok:
        print(
            "Sanity check looks OK (no obvious problems)."
            " Next: convert Label Studio export to COCO and run quick prototyping train."
        )
        return 0

    print("Sanity check produced warnings / issues. Please review output and correct missing files / duplicates.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
