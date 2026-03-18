"""Comparative sweep runner for graph-repair experiments.

Runs `scripts/export_junction_patches.py` for two predefined parameter sets:
  - conservative: angle=15.0, overlap=0.4, max_joins=10
  - aggressive:    angle=30.0, overlap=0.6, max_joins=50

This runner uses a longer per-image timeout (default 120s) intended for full
small+medium sweeps. It writes a per-run summary JSON/CSV to
debug/graph_repair_sweep_comparative/.

Usage: python scripts/run_graph_repair_sweep_comparative.py
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


def run_one(image: Path, debug_dir: Path, angle: float, overlap: float, max_joins: int, timeout: int = 120):
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


def run_mode(
    images: List[Path],
    base_debug: Path,
    mode_name: str,
    angle: float,
    overlap: float,
    max_joins: int,
    timeout: int = 120,
):
    summary = []
    grp_dir = base_debug / mode_name
    for img in images:
        folder = grp_dir / img.stem
        print(f"Processing [{mode_name}] {img} -> {folder} (angle={angle}, overlap={overlap}, max_joins={max_joins})")
        result = run_one(img, folder, angle, overlap, max_joins, timeout=timeout)
        summary.append(result)

    out_json = grp_dir / "summary.json"
    out_csv = grp_dir / "summary.csv"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        if summary:
            keys = sorted(list(summary[0].keys()))
            writer = csv.DictWriter(fh, fieldnames=keys)
            writer.writeheader()
            for row in summary:
                writer.writerow({k: row.get(k, "") for k in keys})

    print(f"Saved {mode_name} summary: {out_json} & {out_csv}")
    return summary


def main():
    repo = Path(__file__).resolve().parents[1]
    small = repo / "data" / "junction_inputs" / "small"
    medium = repo / "data" / "junction_inputs" / "medium"

    images = find_images([small, medium])
    print(f"Found {len(images)} images to process (small+medium)")

    base_debug = repo / "debug" / "graph_repair_sweep_comparative"

    # conservative vs aggressive pair
    conservative = dict(mode_name="conservative", angle=15.0, overlap=0.4, max_joins=10)
    aggressive = dict(mode_name="aggressive", angle=30.0, overlap=0.6, max_joins=50)

    # run conservative first (faster) then aggressive
    csummary = run_mode(images, base_debug, **conservative, timeout=120)
    asummary = run_mode(images, base_debug, **aggressive, timeout=120)

    # write top-level comparative report
    top = {
        "total_images": len(images),
        "conservative_count": len(csummary),
        "aggressive_count": len(asummary),
    }
    top_json = base_debug / "comparative_report.json"
    top_json.write_text(json.dumps(top, indent=2), encoding="utf-8")
    print(f"Comparative sweep finished — report: {top_json}")


if __name__ == "__main__":
    main()
