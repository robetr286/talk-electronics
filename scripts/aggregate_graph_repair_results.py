"""Aggregate outputs from graph-repair sweeps.

Parses the JSON summary produced by the progress runner and computes per-task
metrics including elapsed time, timeout/failure counts, and pixel differences
between skeleton and skeleton_repaired images where available.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


def load_summary(json_path: Path):
    if not json_path.exists():
        raise FileNotFoundError(json_path)
    return json.loads(json_path.read_text(encoding="utf-8"))


def compute_pixel_delta(folder: Path) -> int | None:
    """Return (repaired_pixels - original_pixels) if both images exist, else None."""
    import cv2

    # find by glob
    skel_files = list(folder.glob("*skeleton.png"))
    repaired_files = list(folder.glob("*skeleton_repaired.png"))
    if not skel_files or not repaired_files:
        return None
    try:
        sk = cv2.imread(str(skel_files[0]), cv2.IMREAD_UNCHANGED)
        rp = cv2.imread(str(repaired_files[0]), cv2.IMREAD_UNCHANGED)
        if sk is None or rp is None:
            return None
        skn = (sk > 0).astype("uint8")
        rpn = (rp > 0).astype("uint8")
        return int(rpn.sum()) - int(skn.sum())
    except Exception:
        return None


def aggregate(json_path: Path):
    summary = load_summary(json_path)
    stats = {
        "total": 0,
        "timeouts": 0,
        "nonzero_return": 0,
        "elapsed_total": 0.0,
        "pixel_deltas_counted": 0,
        "pixel_delta_sum": 0,
    }
    results: List[Dict] = []
    base = json_path.parent
    for item in summary:
        stats["total"] += 1
        if item.get("timeout"):
            stats["timeouts"] += 1
        rc = item.get("returncode")
        if rc not in (None, 0):
            stats["nonzero_return"] += 1
        elapsed = float(item.get("elapsed_s") or 0.0)
        stats["elapsed_total"] += elapsed

        # compute pixel delta if debug folder exists
        img = Path(item.get("image"))
        # reconstruct expected outdir structure
        # debug path: debug/graph_repair_sweep_progress/a{angle}_o{overlap}_m{max}/<stem>
        angle = item.get("angle")
        overlap = item.get("overlap")
        maxj = item.get("max_joins")
        outdir = base / f"a{int(angle)}_o{int(float(overlap)*100)}_m{int(maxj)}" / img.stem
        delta = compute_pixel_delta(outdir)
        if delta is not None:
            stats["pixel_deltas_counted"] += 1
            stats["pixel_delta_sum"] += delta

        results.append(
            {
                "image": item.get("image"),
                "angle": angle,
                "overlap": overlap,
                "max_joins": maxj,
                "timeout": item.get("timeout", False),
                "elapsed_s": elapsed,
                "pixel_delta": delta,
            }
        )

    # summary
    avg_elapsed = stats["elapsed_total"] / stats["total"] if stats["total"] else 0
    avg_delta = stats["pixel_delta_sum"] / stats["pixel_deltas_counted"] if stats["pixel_deltas_counted"] else 0
    stats_report = {
        "total_tasks": stats["total"],
        "timeouts": stats["timeouts"],
        "nonzero_return_codes": stats["nonzero_return"],
        "avg_elapsed_s": round(avg_elapsed, 3),
        "pixel_delta_counted": stats["pixel_deltas_counted"],
        "avg_pixel_delta": round(avg_delta, 3),
    }

    out = {
        "summary": stats_report,
        "items": results,
    }
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "summary_json",
        type=Path,
        nargs="?",
        default=Path("debug/graph_repair_sweep_progress/sweep_progress_summary.json"),
    )
    args = parser.parse_args()
    out = aggregate(args.summary_json)
    print(json.dumps(out["summary"], indent=2))
    out_file = args.summary_json.parent / "sweep_progress_aggregated.json"
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("Wrote aggregated results:", out_file)
