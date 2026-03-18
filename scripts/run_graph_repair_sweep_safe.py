"""Robust sweep runner for graph-repair experiments.

Runs the CLI `scripts/export_junction_patches.py` per-image with a per-image
timeout and collects a JSON/CSV summary to avoid long hangs when processing
large datasets.

Usage: python scripts/run_graph_repair_sweep_safe.py
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import List

PY = sys.executable
SCRIPT = Path(__file__).resolve().parents[0] / "export_junction_patches.py"


def find_images(dirs: List[Path]) -> List[Path]:
    images = []
    extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.suffix.lower() in extensions:
                images.append(p)
    return images


def run_one(image: Path, debug_dir: Path, angle: float, overlap: float, max_joins: int, timeout: int = 30):
    debug_dir.mkdir(parents=True, exist_ok=True)
    cmd = [PY, str(SCRIPT), str(image), "--debug-dir", str(debug_dir), "--enable-graph-repair"]
    cmd += [
        "--graph-repair-angle-threshold",
        str(angle),
        "--graph-repair-overlap",
        str(overlap),
        "--graph-repair-max-joins",
        str(max_joins),
    ]
    start = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, text=True)
        elapsed = time.perf_counter() - start
        return {
            "image": str(image),
            "angle": angle,
            "overlap": overlap,
            "max_joins": max_joins,
            "timeout": False,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "elapsed_s": round(elapsed, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "image": str(image),
            "angle": angle,
            "overlap": overlap,
            "max_joins": max_joins,
            "timeout": True,
            "elapsed_s": round(time.perf_counter() - start, 3),
            "error": str(exc),
        }


def main():
    repo = Path(__file__).resolve().parents[1]
    small = repo / "data" / "junction_inputs" / "small"
    medium = repo / "data" / "junction_inputs" / "medium"

    images = find_images([small, medium])
    print(f"Found {len(images)} images to process (small+medium)")

    # conservative grid; can extend later
    angles = [15.0, 30.0]
    overlaps = [0.4, 0.6]
    max_joins = [10, 50]

    base_debug = repo / "debug" / "graph_repair_sweep_extended"
    summary = []

    for angle in angles:
        for overlap in overlaps:
            for m in max_joins:
                grp_dir = base_debug / f"a{int(angle)}_o{int(overlap*100)}_m{m}"
                for img in images:
                    folder = grp_dir / img.stem
                    print(f"Processing {img} -> {folder} (angle={angle}, overlap={overlap}, max_joins={m})")
                    result = run_one(img, folder, angle, overlap, m, timeout=35)
                    summary.append(result)

    out_json = base_debug / "sweep_extended_summary.json"
    out_csv = base_debug / "sweep_extended_summary.csv"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        if summary:
            keys = sorted(list(summary[0].keys()))
            writer = csv.DictWriter(fh, fieldnames=keys)
            writer.writeheader()
            for row in summary:
                writer.writerow({k: row.get(k, "") for k in keys})

    print(f"Saved sweep summary: {out_json} & {out_csv}")


if __name__ == "__main__":
    main()
