"""Runner for larger graph-repair diagnostics sweep.

Generates synthetic cases (broken/dotted lines) across angles and scales,
runs detection with graph_repair enabled/disabled and writes CSV/JSON
results plus a small sample of debug images.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

from talk_electronic.services.line_detection import LineDetectionConfig

# load the harness module by path so running this file directly works
project_root = Path(__file__).resolve().parents[1]
# ensure project root is visible for imports inside the harness module
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

spec = importlib.util.spec_from_file_location(
    "graph_repair_harness", str(Path(__file__).resolve().parent / "graph_repair_harness.py")
)
grh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grh)  # type: ignore
run_scale_sweep = grh.run_scale_sweep
synthetic_broken_line_at_angle = grh.synthetic_broken_line_at_angle
collect_baseline_metrics = grh.collect_baseline_metrics


def config_builder(enable: bool, *, debug_dir: Path | None = None) -> LineDetectionConfig:
    cfg = LineDetectionConfig(dotted_line_graph_repair_enable=enable)
    # enable text masking as part of safety defaults
    cfg.enable_text_masking = True
    if debug_dir is not None:
        cfg.debug_dir = debug_dir
    return cfg


def run_sweep(
    angles: List[float],
    scales: List[float],
    cases_per_combo: int = 10,
    out_root: Path | str = "runs/graph_repair_sweep",
) -> Dict[Tuple[float, float], Dict[str, List[Dict[str, int]]]]:
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_root / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    writer_csv_path = out_dir / "sweep_results.csv"
    json_path = out_dir / "sweep_summary.json"

    rows = []
    summary: Dict[Tuple[float, float], Dict[str, List[Dict[str, int]]]] = {}

    # For speed and reproducibility keep a fixed seed here — we'll still vary small
    rng = random.Random(42)

    total_cases = max(1, len(angles) * len(scales) * cases_per_combo)
    processed = 0
    print(f"Sweep start: {len(angles)} angles × {len(scales)} scales × {cases_per_combo} cases")
    print(f"Total cases: {total_cases}")
    print("Progress updates and intermediate CSV files will be saved periodically")
    flush_every = max(1, total_cases // 20)

    try:
        for angle in angles:
            for scale in scales:
                key = (angle, scale)
                summary[key] = {"no_repair": [], "with_repair": []}
                print(f"Starting combo angle={angle:g}, scale={scale:g} — {cases_per_combo} cases")
                for case_idx in range(cases_per_combo):
                    # vary parameters a bit
                    gap = rng.randint(8, 16)
                    dot_spacing = rng.randint(4, 10)
                    size = 240
                    img = synthetic_broken_line_at_angle(
                        size=size, angle_deg=float(angle), gap=gap, dot_spacing=dot_spacing
                    )
                    if not (abs(scale - 1.0) < 1e-6):
                        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                        img_scaled = cv2.resize(img, dsize=(0, 0), fx=scale, fy=scale, interpolation=interp)
                    else:
                        img_scaled = img

                    # run both configurations
                    cfg_no = config_builder(False)
                    cfg_yes = config_builder(True)

                    # baseline metrics
                    m_no = collect_baseline_metrics(img_scaled, cfg_no)
                    m_yes = collect_baseline_metrics(img_scaled, cfg_yes)

                    # compute ground-truth skeleton and repaired masks for IoU and pixel-delta
                    # use harness helpers imported via importlib
                    gt_img = grh.synthetic_continuous_line_at_angle(size=img_scaled.shape[0], angle_deg=float(angle))
                    gt_skel = grh._fast_skeletonize((gt_img > 0).astype(np.uint8) * 255)
                    gt_skel = (gt_skel > 0).astype(np.uint8)

                    no_bin, no_skel, no_repaired = grh._compute_masks_for_config(img_scaled, cfg_no)
                    yes_bin, yes_skel, yes_repaired = grh._compute_masks_for_config(img_scaled, cfg_yes)

                    # add IoU and skeleton pixel deltas
                    m_no["skeleton_iou_vs_gt"] = grh._iou(no_skel, gt_skel)
                    m_yes["skeleton_iou_vs_gt"] = grh._iou(yes_repaired, gt_skel)

                    m_no["skeleton_pixel_delta_vs_gt"] = int(abs(int(no_skel.sum()) - int(gt_skel.sum())))
                    m_yes["skeleton_pixel_delta_vs_gt"] = int(abs(int(yes_repaired.sum()) - int(gt_skel.sum())))

                    summary[key]["no_repair"].append(m_no)
                    summary[key]["with_repair"].append(m_yes)

                    # Save the synthetic images for traceability for the first case of each combo
                    if case_idx == 0:
                        img_path = out_dir / f"img_angle_{angle:g}_scale_{scale:g}.png"
                        cv2.imwrite(str(img_path), img_scaled)

                    rows.append(
                        {
                            "angle": float(angle),
                            "scale": float(scale),
                            "case_idx": int(case_idx),
                            "no_repair_binary_pixels": int(m_no.get("binary_pixels", 0)),
                            "no_repair_skeleton_pixels": int(m_no.get("skeleton_pixels", 0)),
                            "no_repair_lines_count": int(m_no.get("lines_count", 0)),
                            "no_repair_endpoints": int(m_no.get("endpoints", 0)),
                            "no_repair_components": int(m_no.get("components", 0)),
                            "no_repair_skeleton_iou_vs_gt": float(m_no.get("skeleton_iou_vs_gt", 0.0)),
                            "no_repair_skeleton_pixel_delta_vs_gt": int(m_no.get("skeleton_pixel_delta_vs_gt", 0)),
                            "with_repair_binary_pixels": int(m_yes.get("binary_pixels", 0)),
                            "with_repair_skeleton_pixels": int(m_yes.get("skeleton_pixels", 0)),
                            "with_repair_lines_count": int(m_yes.get("lines_count", 0)),
                            "with_repair_endpoints": int(m_yes.get("endpoints", 0)),
                            "with_repair_components": int(m_yes.get("components", 0)),
                            "with_repair_skeleton_iou_vs_gt": float(m_yes.get("skeleton_iou_vs_gt", 0.0)),
                            "with_repair_skeleton_pixel_delta_vs_gt": int(m_yes.get("skeleton_pixel_delta_vs_gt", 0)),
                        }
                    )

                    processed += 1
                    if processed % flush_every == 0 or processed >= total_cases:
                        # save intermediate CSV so a long run shows progress and leaves artifacts
                        with open(writer_csv_path, "w", newline="", encoding="utf-8") as fh:
                            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
                            if rows:
                                writer.writeheader()
                                writer.writerows(rows)
                        print(f"Progress: processed {processed}/{total_cases} cases (flushed intermediate CSV)")
    except KeyboardInterrupt:
        print("\nSweep interrupted by user (KeyboardInterrupt). Saving partial results...")

    # save CSV
    # Final write (safe even if we did intermediate writes)
    with open(writer_csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)

    # save summary JSON (convert keys)
    json_serializable = {f"{angle}_{scale}": summary[(angle, scale)] for angle, scale in list(summary.keys())}
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(json_serializable, fh, indent=2)

    print(f"Saved CSV: {writer_csv_path}")
    print(f"Saved JSON summary: {json_path}")
    print(f"Outputs are in: {out_dir}")

    return summary


if __name__ == "__main__":
    angles = [float(x) for x in range(0, 180, 15)]
    scales = [0.5, 0.75, 1.0, 1.5, 2.0]
    print("Running sweep with angles:", angles)
    print("Scales:", scales)
    run_sweep(angles, scales, cases_per_combo=10)
