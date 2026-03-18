#!/usr/bin/env python3
"""Wait for Mask R-CNN run to complete (weights/last.pth) and run gather_maskrcnn_report.py.

Usage:
    python scripts/tools/wait_for_maskrcnn_and_gather.py \
            runs/segment/exp_maskrcnn_poc \
            --coco-json data/yolo_dataset/mix_small/coco_annotations.json
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("run_dir", type=Path)
    p.add_argument(
        "--wait-seconds", type=int, default=120, help="How long results/stability to wait after last modification"
    )
    p.add_argument("--coco-json", type=Path, default=None)
    return p.parse_args()


def main():
    args = parse_args()
    run_dir = args.run_dir
    if run_dir is None or not run_dir.exists():
        print("Provide an existing run directory")
        sys.exit(1)

    w = run_dir / "weights" / "last.pth"
    print(f"Monitoring {w}")
    last_mtime = None
    while True:
        if w.exists():
            try:
                mtime = w.stat().st_mtime
            except Exception:
                mtime = None
            if last_mtime is None:
                last_mtime = mtime
                print("Detected last.pth, waiting for stability...")
            else:
                if mtime == last_mtime:
                    # time stable -> possibly finished
                    print("last.pth stable; invoking gather script")
                    cmd = [
                        sys.executable,
                        "scripts/tools/gather_maskrcnn_report.py",
                        "--run-dir",
                        str(run_dir),
                    ]
                    if args.coco_json:
                        cmd += ["--coco-json", str(args.coco_json)]
                    subprocess.run(cmd)
                    break
                else:
                    last_mtime = mtime
                    print("last.pth updated; reset stability timer")
        else:
            print("last.pth not found yet; sleeping")
        time.sleep(args.wait_seconds)


if __name__ == "__main__":
    main()
