#!/usr/bin/env python
"""Gating script for local_patch_repair results.

Runs the worker (optionally) and validates local_results.json against a small
set of acceptance thresholds. Exits non-zero when gating fails.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "debug" / "graph_repair_validation" / "local_results" / "local_results.json"


def run_worker(python=None, max_dist=12, min_line_ratio=0.25, limit=0, watchdog=True, wd_timeout=1800, wd_idle=600):
    cmd = [
        python or sys.executable,
        str(ROOT / "scripts" / "local_patch_repair_worker.py"),
        "--max_dist",
        str(max_dist),
        "--min_line_ratio",
        str(min_line_ratio),
    ]
    if limit:
        cmd += ["--limit", str(limit)]
    # prefer guarded runs to prevent hangs
    if watchdog:
        cmd += ["--watchdog", "--wd-timeout", str(wd_timeout), "--wd-idle", str(wd_idle)]
    print("Running:", " ".join(cmd))
    p = subprocess.run(cmd)
    return p.returncode


def load_results():
    if not RESULTS.exists():
        print("No results file found:", RESULTS)
        return None
    return json.loads(RESULTS.read_text())


def check_gates(results, min_iou=0.7, min_endpoint_reduction_pct=40.0):
    failed = []
    for case, v in results.items():
        orig_eps = v["orig"]["endpoints"]
        conn_eps = v["connected"]["endpoints"]
        iou = v["connected"].get("iou_vs_orig", 0)
        ep_red = 100.0 * (orig_eps - conn_eps) / orig_eps if orig_eps else 0.0
        ok = (iou >= min_iou) or (ep_red >= min_endpoint_reduction_pct)
        if not ok:
            failed.append({"case": case, "iou": iou, "ep_red": ep_red})
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gating runner for local_patch_repair")
    parser.add_argument(
        "--no-worker",
        dest="no_worker",
        action="store_true",
        help="Do not run the worker, only validate existing results",
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Limit for the worker (0=all cases). Only used if worker runs"
    )
    parser.add_argument("--max_dist", type=int, default=12)
    parser.add_argument("--min_line_ratio", type=float, default=0.25)
    parser.add_argument("--wd-timeout", type=int, default=1800)
    parser.add_argument("--wd-idle", type=int, default=600)
    args = parser.parse_args(argv)

    # run worker locally first (optionally limited)
    rc = 0
    if not args.no_worker:
        rc = run_worker(
            max_dist=args.max_dist,
            min_line_ratio=args.min_line_ratio,
            limit=args.limit,
            wd_timeout=args.wd_timeout,
            wd_idle=args.wd_idle,
        )
    if rc != 0:
        print("Worker run failed (exitcode=", rc, ")")
        return rc

    results = load_results()
    if results is None:
        return 2

    failed = check_gates(results)
    if failed:
        print("GATING FAILED for cases:")
        for f in failed:
            print(f)
        return 3

    print("GATING PASSED — all cases satisfy acceptance criteria")
    return 0


if __name__ == "__main__":
    sys.exit(main())
