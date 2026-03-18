#!/usr/bin/env python3
"""Wait for a run directory to have results and then gather the report.

Usage:
  python scripts/tools/wait_and_collect.py runs/segment/exp_mix_small_100
"""
import subprocess
import sys
import time
from pathlib import Path


def main():
    if len(sys.argv) > 1:
        run_dir = Path(sys.argv[1])
    else:
        run_dir = Path("runs/segment/exp_mix_small_50")

    print("Waiting for training output in", run_dir)
    while True:
        if run_dir.exists():
            # Trigger collection when either:
            # - the run wrote a 'run_complete' marker (preferred), OR
            # - both results.csv and weights/best.pt exist (legacy behavior)
            if (run_dir / "run_complete").exists() or (
                (run_dir / "results.csv").exists() and (run_dir / "weights" / "best.pt").exists()
            ):
                print("Results found, gathering report...")
                # generic run report
                subprocess.run([sys.executable, "scripts/tools/gather_run_report.py", str(run_dir)])
                # Mask R-CNN specific summary (mIoU) appended to qa_log.md
                subprocess.run(
                    [
                        sys.executable,
                        "scripts/tools/gather_maskrcnn_report.py",
                        "--run-dir",
                        str(run_dir),
                    ]
                )
                # run inference benchmark and append results
                subprocess.run(
                    [
                        sys.executable,
                        "scripts/tools/inference_benchmark_maskrcnn.py",
                        "--run-dir",
                        str(run_dir),
                    ]
                )
                # update aggregated benchmarks CSV/JSON so dashboard stays current
                subprocess.run([sys.executable, "scripts/tools/aggregate_benchmarks.py"])
                break
        time.sleep(30)
    print("Done")


if __name__ == "__main__":
    main()
