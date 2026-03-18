"""Sweep runner with visible progress, ETA and parallelism.

This script runs per-image graph-repair experiments and shows clear
progress (completed/total, percent, ETA). It writes intermediate results
to a JSON file after each task so runs can safely be interrupted and
resumed.

Usage: python scripts/run_graph_repair_sweep_progress.py
Options are configured inside `main()` for safety; adjust as needed.
"""

from __future__ import annotations

import concurrent.futures
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

PY = sys.executable
SCRIPT = Path(__file__).resolve().parents[0] / "export_junction_patches.py"


def find_images(dirs: Iterable[Path]) -> List[Path]:
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
    images = []
    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.suffix.lower() in exts:
                images.append(p)
    return images


def run_single(params: Tuple[Path, float, float, int, Path, int]) -> Dict:
    image, angle, overlap, max_joins, out_dir, timeout = params
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [PY, str(SCRIPT), str(image), "--debug-dir", str(out_dir), "--enable-graph-repair"]
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
            "elapsed_s": round(elapsed, 3),
            "stdout_lines": (proc.stdout or "").splitlines()[-6:],
            "stderr_lines": (proc.stderr or "").splitlines()[-6:],
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


def print_progress(done: int, total: int, start_ts: float) -> None:
    pct = (done / total) * 100.0 if total else 100.0
    elapsed = time.perf_counter() - start_ts
    rate = done / elapsed if elapsed > 0 else 0.0
    remain = max(0.0, total - done)
    eta = (remain / rate) if rate > 0 else float("inf")
    eta_fmt = f"{int(eta//60)}m{int(eta%60)}s" if math.isfinite(eta) else "?"
    print(f"Progress: {done}/{total} ({pct:.1f}%) — elapsed {int(elapsed)}s — ETA {eta_fmt}")


def tasks_for_grid(
    images: List[Path], angles: List[float], overlaps: List[float], max_joins: List[int], base_debug: Path
) -> List[Tuple[Path, float, float, int, Path, int]]:
    tasks = []
    for a in angles:
        for o in overlaps:
            for m in max_joins:
                folder = base_debug / f"a{int(a)}_o{int(o*100)}_m{m}"
                for img in images:
                    outdir = folder / img.stem
                    tasks.append((img, a, o, m, outdir, 35))
    return tasks


def main():
    repo = Path(__file__).resolve().parents[1]
    small = repo / "data" / "junction_inputs" / "small"
    medium = repo / "data" / "junction_inputs" / "medium"

    images = find_images([small, medium])
    # optional: limit images via env var SWEEP_LIMIT (useful for quick tests)
    from os import environ

    limit = int(environ.get("SWEEP_LIMIT", "0") or "0")
    if limit and len(images) > limit:
        print(f"Limiting images to first {limit} for quick run (SWEEP_LIMIT env var)")
        images = images[:limit]
    if not images:
        print("No images found in small/medium — aborting")
        return

    # conservative grid
    angles = [15.0, 30.0]
    overlaps = [0.4, 0.6]
    max_joins = [10, 50]

    total_tasks = len(images) * len(angles) * len(overlaps) * len(max_joins)
    print(
        f"Running sweep; images={len(images)}, angles={len(angles)}, overlaps={len(overlaps)}, joins={len(max_joins)}"
    )
    print(f"Total tasks: {total_tasks}")

    base_debug = repo / "debug" / "graph_repair_sweep_progress"
    out_json = base_debug / "sweep_progress_summary.json"
    base_debug.mkdir(parents=True, exist_ok=True)

    # read optional timeout override (seconds) from env var SWEEP_TIMEOUT
    from os import environ

    timeout_sec = int(environ.get("SWEEP_TIMEOUT", "35") or "35")
    tasks = tasks_for_grid(images, angles, overlaps, max_joins, base_debug)
    # replace timeout values in tasks
    tasks = [(img, a, o, m, outdir, timeout_sec) for (img, a, o, m, outdir, _) in tasks]

    # If summary exists already, load to skip completed
    completed_map: Dict[str, Dict] = {}
    if out_json.exists():
        try:
            existing = json.loads(out_json.read_text(encoding="utf-8"))
            for item in existing:
                key = f"{item.get('image')}|{item.get('angle')}|{item.get('overlap')}|{item.get('max_joins')}"
                completed_map[key] = item
        except Exception:
            # ignore corrupt
            completed_map = {}

    filtered_tasks = [t for t in tasks if f"{t[0]}|{t[1]}|{t[2]}|{t[3]}" not in completed_map]
    total = len(tasks)
    done_initial = len(completed_map)
    print(f"Already completed: {done_initial} — will process {len(filtered_tasks)} remaining tasks")

    start_ts = time.perf_counter()
    results = list(completed_map.values())

    # choose parallelism conservatively; allow override via env SWEEP_WORKERS
    from os import environ

    workers_env = int(environ.get("SWEEP_WORKERS", "0") or "0")
    if workers_env > 0:
        workers = workers_env
    else:
        workers = min(4, max(1, (len(filtered_tasks) and 2)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(run_single, params): params for params in filtered_tasks}
        done = done_initial
        print_progress(done, total, start_ts)
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
            except Exception as exc:
                res = {"error": str(exc)}
            results.append(res)
            done += 1
            # write intermediate results to disk to allow resume
            out_json.write_text(json.dumps(results, indent=2), encoding="utf-8")
            print_progress(done, total, start_ts)

    print(f"Sweep finished — final summary: {out_json}")


if __name__ == "__main__":
    main()
