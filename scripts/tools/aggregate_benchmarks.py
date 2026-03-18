#!/usr/bin/env python3
"""Aggregate existing benchmark JSONs into a single CSV/JSON summary.

Searches `runs/benchmarks` and `runs/segment/*/inference_benchmark.json`.
"""
import csv
import json
from pathlib import Path


def find_files(root: Path):
    files = []
    for p in root.rglob("*.json"):
        files.append(p)
    # also look for inference_benchmark.json under runs/segment
    for p in Path("runs/segment").rglob("inference_benchmark.json"):
        files.append(p)
    # dedupe while preserving order
    seen = set()
    out = []
    for p in files:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def extract_from_benchmark(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    # classic benchmark_*.json format
    if isinstance(data, dict) and "results" in data:
        meta = {k: data.get(k) for k in ("timestamp", "device", "imgsz", "batch", "workers")}
        for r in data["results"]:
            rows.append(
                {
                    "source_file": str(path),
                    "run_name": data.get("timestamp") or path.stem,
                    "type": "1-ep-benchmark",
                    "model": r.get("model"),
                    "time_sec": r.get("time_sec"),
                    "device": meta["device"],
                    "imgsz": meta["imgsz"],
                    "batch": meta["batch"],
                    "workers": meta["workers"],
                }
            )
        return rows

    # inference_benchmark.json format
    if isinstance(data, dict) and "mean_latency_ms" in data:
        return [
            {
                "source_file": str(path),
                "run_name": Path(data.get("run_dir", "")).name if data.get("run_dir") else path.parent.name,
                "type": "inference",
                "model": Path(data.get("weights", "")).stem if data.get("weights") else None,
                "mean_latency_ms": data.get("mean_latency_ms"),
                "median_latency_ms": data.get("median_latency_ms"),
                "std_latency_ms": data.get("std_latency_ms"),
                "fps": data.get("fps"),
                "samples": data.get("samples"),
                "device": data.get("device"),
            }
        ]

    # simple PoC summaries (list or dict with time_sec)
    rows = []
    if isinstance(data, list):
        for item in data:
            rows.append(
                {
                    "source_file": str(path),
                    "run_name": path.stem,
                    "type": "poc",
                    "model": item.get("model"),
                    "time_sec": item.get("time_sec"),
                    "epochs": item.get("epochs"),
                    "batch": item.get("batch"),
                }
            )
        return rows

    if isinstance(data, dict) and "time_sec" in data:
        return [
            {
                "source_file": str(path),
                "run_name": path.stem,
                "type": "poc",
                "model": data.get("model"),
                "time_sec": data.get("time_sec"),
                "epochs": data.get("epochs"),
                "batch": data.get("batch"),
            }
        ]

    # fallback: record presence
    return [
        {
            "source_file": str(path),
            "run_name": path.stem,
            "type": "unknown",
        }
    ]


def main():
    root = Path("runs/benchmarks")
    files = find_files(root)
    rows = []
    for p in files:
        try:
            rows.extend(extract_from_benchmark(p))
        except Exception as e:
            rows.append({"source_file": str(p), "run_name": p.stem, "type": "error", "error": str(e)})

    out_json = root / "aggregated_benchmarks.json"
    out_csv = root / "aggregated_benchmarks.csv"
    root.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)

    # determine CSV columns
    cols = set()
    for r in rows:
        cols.update(r.keys())
    cols = [
        "source_file",
        "run_name",
        "type",
        "model",
        "time_sec",
        "mean_latency_ms",
        "fps",
        "median_latency_ms",
        "std_latency_ms",
        "samples",
        "epochs",
        "batch",
        "imgsz",
        "device",
        "workers",
        "error",
    ]

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in cols})

    print("Wrote", out_json, "and", out_csv)
    # append short summary to qa_log.md
    try:
        summary_lines = []
        # fastest 1-ep benchmark (lowest time_sec)
        bench_rows = [r for r in rows if r.get("type") == "1-ep-benchmark" and r.get("time_sec")]
        if bench_rows:
            fastest = min(bench_rows, key=lambda x: float(x.get("time_sec") or 1e9))
            slowest = max(bench_rows, key=lambda x: float(x.get("time_sec") or 0))
            summary_lines.append(
                f"Fastest 1-ep benchmark: {fastest.get('model')} — {float(fastest.get('time_sec')):.1f}s ({Path(fastest['source_file']).name})"
            )
            summary_lines.append(
                f"Slowest 1-ep benchmark: {slowest.get('model')} — {float(slowest.get('time_sec')):.1f}s ({Path(slowest['source_file']).name})"
            )

        # best inference FPS
        inf_rows = [r for r in rows if r.get("type") == "inference" and r.get("fps")]
        if inf_rows:
            best_fps = max(inf_rows, key=lambda x: float(x.get("fps") or 0))
            summary_lines.append(
                f"Best inference FPS: {float(best_fps.get('fps')):.2f} — {best_fps.get('run_name')} ({Path(best_fps['source_file']).name})"
            )

        if summary_lines:
            qa = Path("qa_log.md")
            text = "\n".join(["### Aggregated benchmarks summary", ""] + summary_lines) + "\n"
            qa_text = qa.read_text(encoding="utf-8")
            qa_text = qa_text.rstrip() + "\n\n" + text
            qa.write_text(qa_text, encoding="utf-8")
            print("Appended aggregate summary to qa_log.md")
    except Exception as e:
        print("Failed to append summary to qa_log.md:", e)


if __name__ == "__main__":
    main()
