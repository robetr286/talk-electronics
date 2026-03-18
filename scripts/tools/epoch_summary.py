#!/usr/bin/env python3
"""Monitor `results.csv` in a run directory and print short summary every N epochs.

Usage:
  python scripts/tools/epoch_summary.py runs/segment/exp_mix_small_100 --interval 30 --period 10
"""
import argparse
import csv
import time
from pathlib import Path


def parse_results(path: Path):
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    if len(lines) <= 1:
        return []
    reader = csv.DictReader(lines)
    rows = list(reader)
    return rows


def short_summary(row):
    # pick useful fields if present
    ep = row.get("epoch") or row.get("epoch", "?")
    time_s = row.get("time", "?")
    mAP_box = row.get("metrics/mAP50(B)", "?")
    mAP_box_5095 = row.get("metrics/mAP50-95(B)", "?")
    mAP_mask = row.get("metrics/mAP50(M)", "?")
    return f"Epoch {ep}: time={time_s}s mAP50(box)={mAP_box} mAP50-95(box)={mAP_box_5095} mAP50(mask)={mAP_mask}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run_dir", help="run directory")
    p.add_argument("--interval", type=int, default=30, help="seconds between checks")
    p.add_argument("--period", type=int, default=10, help="report every N epochs")
    args = p.parse_args()

    run_dir = Path(args.run_dir)
    results = run_dir / "results.csv"
    log = Path("debug") / f"epoch_summary_{run_dir.name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    seen = set()
    print(f"Monitoring {results} (interval={args.interval}s, period={args.period} epochs)")
    try:
        with log.open("a", encoding="utf-8") as lf:
            lf.write(f"--- epoch_summary started for {run_dir} at {time.ctime()}\n")
    except Exception as e:
        print(f"Warning: cannot write to log {log}: {e}")
    while True:
        rows = parse_results(results)
        for row in rows:
            try:
                ep = int(row.get("epoch", -1))
            except Exception:
                continue
            if ep in seen:
                continue
            seen.add(ep)
            if ep % args.period == 0:
                s = short_summary(row)
                t = time.ctime()
                out = f"[{t}] {s}"
                print(out)
                try:
                    with log.open("a", encoding="utf-8") as lf:
                        lf.write(out + "\n")
                except Exception:
                    # ignore logging failures, continue printing to console
                    pass
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
