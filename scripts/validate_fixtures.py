#!/usr/bin/env python3
"""
Prosty validator fixtures dla tests/fixtures/p1_line_examples.
Sprawdza:
 - obecność katalogów raw/ i annotations/
 - dozwolone rozszerzenia (png, jpg, jpeg, bmp, tiff, pdf)
 - czy dla każdego obrazu jest plik anotacji .json (opcjonalne, ale zgłaszane)
 - rozmiar plików (domyślnie <= 5 MiB)
 - duplikaty plików (sha256)
 - prostą strukturę pliku anotacji (image, annotations -> list)

Użycie:
 python scripts/validate_fixtures.py --path tests/fixtures/p1_line_examples --max-size-mb 5

Zwraca kod 0 jeśli ok, 1 jeśli znaleziono błędy krytyczne, 2 jeśli są tylko ostrzeżenia.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Tuple

ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".pdf"}


def hash_file(path: Path, chunk_size: int = 8192) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def find_files(directory: Path) -> List[Path]:
    return [p for p in directory.iterdir() if p.is_file()]


def validate_annotations_file(path: Path) -> Tuple[bool, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # keep simple
        return False, f"invalid json: {e}"

    if not isinstance(raw, dict):
        return False, "annotation file root is not an object"

    if "image" not in raw or "annotations" not in raw:
        return False, "missing required keys (image, annotations)"

    if not isinstance(raw["annotations"], list):
        return False, "annotations is not a list"

    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="tests/fixtures/p1_line_examples", help="Path to fixtures root")
    parser.add_argument("--max-size-mb", default=5, type=float, help="Maximum allowed file size in MiB")
    args = parser.parse_args()

    root = Path(args.path)
    raw_dir = root / "raw"
    ann_dir = root / "annotations"

    if not root.exists():
        print(f"ERROR: fixtures root not found: {root}")
        return 1

    if not raw_dir.exists():
        print(f"ERROR: raw directory not found: {raw_dir}")
        return 1

    if not ann_dir.exists():
        print(f"WARNING: annotations directory not found: {ann_dir} (annotations are optional but recommended)")

    max_bytes = int(args.max_size_mb * 1024 * 1024)

    raw_files = find_files(raw_dir)
    if not raw_files:
        print("WARNING: no raw files found in fixtures/raw/")

    errors = []
    warnings = []

    # duplicates check
    hashes: Dict[str, List[Path]] = {}

    for f in raw_files:
        ext = f.suffix.lower()
        if ext not in ALLOWED_EXTS:
            warnings.append(f"{f.name}: unexpected extension '{ext}'")

        size = f.stat().st_size
        if size > max_bytes:
            warnings.append(f"{f.name}: size {size} bytes > {max_bytes} bytes ({args.max_size_mb} MiB)")

        h = hash_file(f)
        hashes.setdefault(h, []).append(f)

        # check for corresponding annotation
        ann = ann_dir / (f.stem + ".json")
        if ann_dir.exists():
            if not ann.exists():
                warnings.append(f"{f.name}: missing annotation file {ann.name}")
            else:
                ok, msg = validate_annotations_file(ann)
                if not ok:
                    errors.append(f"{ann.name}: {msg}")

    # duplicates
    for h, files in hashes.items():
        if len(files) > 1:
            warnings.append("duplicate files detected: " + ", ".join([p.name for p in files]))

    # report
    print("\nVALIDATION SUMMARY")
    print("-------------------")
    if errors:
        print("ERRORS:")
        for e in errors:
            print(" - ", e)
    else:
        print("No critical errors found.")

    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(" - ", w)
    else:
        print("No warnings.")

    if errors:
        return 1
    if warnings:
        # exit code 2 for warnings only
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
