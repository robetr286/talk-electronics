#!/usr/bin/env python
"""Worker wrapper for local_patch_repair

This script is intended to be used by the pipeline or CI to run the
local_patch_repair experiment as a standalone worker. It calls the
existing script in debug/graph_repair_validation and forwards CLI args.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = ROOT / "debug" / "graph_repair_validation" / "local_patch_repair.py"


def main():
    parser = argparse.ArgumentParser(description="Run local_patch_repair as a worker.")
    parser.add_argument("--max_dist", type=int, default=12)
    parser.add_argument("--min_line_ratio", type=float, default=0.25)
    parser.add_argument("--limit", type=int, default=0, help="0=all cases")
    parser.add_argument("--python", default=sys.executable, help="Python executable to run the worker with")
    args = parser.parse_args()

    if not SCRIPT.exists():
        print(f"ERROR: worker target not found: {SCRIPT}")
        return 2

    cmd = [args.python, str(SCRIPT), "--max_dist", str(args.max_dist), "--min_line_ratio", str(args.min_line_ratio)]
    if args.limit:
        cmd += ["--limit", str(args.limit)]

    print("Running local_patch_repair with:", " ".join(cmd))
    p = subprocess.run(cmd)
    return p.returncode


if __name__ == "__main__":
    raise SystemExit(main())
