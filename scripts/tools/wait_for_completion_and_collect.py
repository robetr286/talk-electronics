#!/usr/bin/env python3
"""Wait for a run to reach expected epochs and gather a final report.

Usage:
  python scripts/tools/wait_for_completion_and_collect.py runs/segment/exp_mix_small_100
"""
import sys
import time
import subprocess
from pathlib import Path
import yaml
import csv
import glob


def detect_training_finished(run_dir: Path) -> bool:
    """Detect whether training finished early by scanning debug logs or presence of last checkpoint.

    Heuristics used:
    - look for 'Training finished' or 'EarlyStopping' in any debug log matching run name
    - or if `weights/last.pt` exists and `results.csv` hasn't changed for >120s
    """
    # check debug logs
    pattern = str(Path("debug") / f"*{run_dir.name}*.log")
    for p in glob.glob(pattern):
        try:
            text = Path(p).read_text(encoding="utf-8", errors="ignore")
            if "Training finished" in text or "EarlyStopping" in text:
                return True
        except Exception:
            pass
    # fallback: last.pt exists and results.csv hasn't changed for a while
    last_pt = run_dir / "weights" / "last.pt"
    results = run_dir / "results.csv"
    if last_pt.exists() and results.exists():
        try:
            mtime = results.stat().st_mtime
            if (time.time() - mtime) > 120:
                return True
        except Exception:
            pass
    return False


def get_expected_epochs(run_dir: Path) -> int:
    args = run_dir / "args.yaml"
    if not args.exists():
        return -1
    try:
        d = yaml.safe_load(args.read_text(encoding="utf-8"))
        return int(d.get("epochs", -1))
    except Exception:
        return -1


def last_epoch_in_results(results: Path) -> int:
    if not results.exists():
        return -1
    try:
        lines = results.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        if len(lines) <= 1:
            return -1
        reader = csv.DictReader(lines)
        rows = list(reader)
        if not rows:
            return -1
        last = rows[-1]
        return int(last.get("epoch", -1))
    except Exception:
        return -1


def main():
    if len(sys.argv) > 1:
        run_dir = Path(sys.argv[1])
    else:
        run_dir = Path("runs/segment/exp_mix_small_50")

    print(f"Monitoring completion for {run_dir}")
    expected = get_expected_epochs(run_dir)
    print(f"Expected epochs from args.yaml: {expected}")
    results = run_dir / "results.csv"
    while True:
        curr = last_epoch_in_results(results)
        print(f"Current epoch: {curr} / {expected}")
        if expected > 0 and curr >= expected:
            print("Target epoch reached. Gathering final report...")
            subprocess.run([sys.executable, "scripts/tools/gather_run_report.py", str(run_dir)])
            print("Done")
            break
        # also consider last.pt presence as completion fallback
        if detect_training_finished(run_dir):
            print("Detected training finished (early stop or last.pt); collecting report...")
            subprocess.run([sys.executable, "scripts/tools/gather_run_report.py", str(run_dir)])
            break
        time.sleep(60)


if __name__ == "__main__":
    main()
