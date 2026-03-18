#!/usr/bin/env python3
"""Map Label Studio export image references to actual files in image directories.

Usage:
    python scripts/dataset/map_labelstudio_filenames.py -i input.json \
        -o output_mapped.json -I png_dla_label-studio data/real/images

The script tries these heuristics (in order) to find a match for the referenced filename:
 - exact filename match in any images dir
 - strip a leading uuid-like prefix (text up to first '-') and try match
 - fallback: find files whose name endswith the referenced suffix (unique match required)

The mapped JSON will contain the same structure but with task['data']['image'] replaced by the matched base filename where possible.
"""
# flake8: noqa
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional


def find_candidate_in_dirs(candidate: str, image_dirs: List[Path]) -> Optional[Path]:
    base = os.path.basename(candidate)
    # exact
    for d in image_dirs:
        p = d / base
        if p.exists():
            return p

    # try strip leading prefix up to first '-'
    if "-" in base:
        _, suffix = base.split("-", 1)
        for d in image_dirs:
            p = d / suffix
            if p.exists():
                return p

    # try endswith unique match
    matches = []
    for d in image_dirs:
        for f in d.rglob("*"):
            if not f.is_file():
                continue
            if f.name.endswith(base) or (("-" in base) and f.name.endswith(suffix)):
                matches.append(f)

    # unique match only
    if len(matches) == 1:
        return matches[0]

    return None


def map_export(input_json: Path, image_dirs: List[Path], output_json: Path):
    data = json.loads(input_json.read_text(encoding="utf-8"))
    mapped = []
    found = {}
    not_found = {}

    for task in data:
        d = task.get("data")
        if isinstance(d, dict):
            img = d.get("image") or d.get("url") or d.get("file")
        elif isinstance(d, str):
            img = d
        else:
            img = None

        if not img:
            mapped.append(task)
            continue

        base = os.path.basename(img)
        p = find_candidate_in_dirs(base, image_dirs)
        if p:
            # normalize to base filename
            newname = p.name
            # update the task data in-place
            if isinstance(d, dict):
                if "image" in d:
                    d["image"] = newname
                elif "url" in d:
                    d["url"] = newname
                elif "file" in d:
                    d["file"] = newname
            else:
                task["data"] = newname

            mapped.append(task)
            found[base] = str(p)
        else:
            mapped.append(task)
            not_found[base] = True

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(mapped, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Mapped export saved to: {output_json}")
    print(f"Matches found: {len(found)}")
    if found:
        for k, v in found.items():
            print(f"  {k} -> {v}")

    if not_found:
        print(f"Could not match {len(not_found)} referenced filenames:")
        for k in not_found.keys():
            print(f"  - {k}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True, type=Path)
    parser.add_argument("--output", "-o", required=True, type=Path)
    parser.add_argument("--images", "-I", required=True, nargs="+", type=Path)
    args = parser.parse_args()

    image_dirs = [p for p in args.images if p.exists()]
    if not image_dirs:
        print("No image directories available")
        raise SystemExit(2)

    map_export(args.input, image_dirs, args.output)


if __name__ == "__main__":
    main()
