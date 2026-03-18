#!/usr/bin/env python3
"""Run budgeted benchmarks on a GPU instance (H100) for YOLOv8 and Mask R-CNN.

This script runs both models for a specified GPU-time budget (minutes). It runs
repeated single-epoch trainings and stops when the budget elapses. Output is
written as JSON with per-epoch metrics and timing.

Usage example:
  python scripts/tools/h100_benchmark.py --yolo-data data/yolo_dataset/mix_small/dataset.yaml \
    --coco-json data/synthetic/coco_v2_450.json --yolo-budget 60 --mask-budget 90 --device cuda:0
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def run_cmd(cmd, env=None):
    print("Running:", " ".join(cmd))
    proc = subprocess.Popen(cmd, env=env)
    rc = proc.wait()
    return rc


def nvidia_snapshot():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"]
        )
        rows = out.decode("utf8").strip().splitlines()
        res = []
        for r in rows:
            used, total, util = [int(x.strip()) for x in r.split(",")]
            res.append({"memory_used_mb": used, "memory_total_mb": total, "utilization_pct": util})
        return res
    except Exception:
        return None


def run_yolo_epoch(yolo_data, device, imgsz, batch, workers, output_dir):
    from ultralytics import YOLO

    model = YOLO("yolov8n-seg.pt")
    start = time.monotonic()
    results = model.train(
        data=str(yolo_data),
        epochs=1,
        imgsz=imgsz,
        batch=batch,
        device=device,
        workers=workers,
        save_period=1,
        plots=False,
        val=True,
    )
    end = time.monotonic()
    return {"time_sec": end - start, "save_dir": str(results.save_dir)}


def run_maskrcnn_epoch(coco_json, images_dir, device, img_size, batch, workers, output_dir):
    cmd = [
        sys.executable,
        str(Path(__file__).parents[1].resolve() / "experiments" / "run_maskrcnn_poc.py"),
        "--coco-json",
        str(coco_json),
        "--images-dir",
        str(images_dir),
        "--output",
        str(output_dir),
        "--epochs",
        "1",
        "--batch",
        str(batch),
        "--img-size",
        str(img_size),
        "--workers",
        str(workers),
    ]
    if device:
        cmd += ["--device", device]
    start = time.monotonic()
    rc = run_cmd(cmd)
    end = time.monotonic()
    return {"time_sec": end - start, "rc": rc}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--yolo-data", type=Path, default=Path("data/yolo_dataset/mix_small/dataset.yaml"))
    p.add_argument("--coco-json", type=Path, default=Path("data/synthetic/coco_v2_450.json"))
    p.add_argument("--images-dir", type=Path, default=Path("data/synthetic/images"))
    p.add_argument("--yolo-budget", type=int, default=60)
    p.add_argument("--mask-budget", type=int, default=90)
    p.add_argument("--device", type=str, default="cuda")
    p.add_argument("--imgsz", type=int, default=256)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--mask-batch", type=int, default=1)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--output-dir", type=Path, default=Path("runs/benchmarks/h100"))
    return p.parse_args()


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": timestamp,
        "device": args.device,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "mask_batch": args.mask_batch,
        "workers": args.workers,
        "yolo_budget_min": args.yolo_budget,
        "mask_budget_min": args.mask_budget,
        "results": [],
    }

    # YOLO budgeted run
    print("Starting YOLO budgeted run for", args.yolo_budget, "minutes")
    yolo_start = time.monotonic()
    elapsed_min = 0
    yolo_info = []
    try:
        while elapsed_min < args.yolo_budget:
            snap = nvidia_snapshot()
            res = run_yolo_epoch(args.yolo_data, args.device, args.imgsz, args.batch, args.workers, args.output_dir)
            res["gpu_snapshot"] = snap
            res["timestamp"] = datetime.utcnow().isoformat()
            yolo_info.append(res)
            elapsed_min = (time.monotonic() - yolo_start) / 60.0
            print("Elapsed (min):", elapsed_min)
    except KeyboardInterrupt:
        print("YOLO budget run interrupted")
    report["results"].append({"model": "yolov8n-seg", "epochs_ran": len(yolo_info), "epochs": yolo_info})

    # Mask R-CNN budgeted run
    print("Starting Mask R-CNN budgeted run for", args.mask_budget, "minutes")
    mask_start = time.monotonic()
    elapsed_min = 0
    mask_info = []
    try:
        while elapsed_min < args.mask_budget:
            snap = nvidia_snapshot()
            res = run_maskrcnn_epoch(
                args.coco_json, args.images_dir, args.device, args.imgsz, args.mask_batch, args.workers, args.output_dir
            )
            res["gpu_snapshot"] = snap
            res["timestamp"] = datetime.utcnow().isoformat()
            mask_info.append(res)
            elapsed_min = (time.monotonic() - mask_start) / 60.0
            print("Elapsed (min):", elapsed_min)
    except KeyboardInterrupt:
        print("Mask R-CNN budget run interrupted")
    report["results"].append({"model": "maskrcnn_resnet50_fpn", "epochs_ran": len(mask_info), "epochs": mask_info})

    out = args.output_dir / f"h100_benchmark_{timestamp}.json"
    with open(out, "w", encoding="utf8") as f:
        json.dump(report, f, indent=2)
    print("H100 benchmark complete. Report saved to:", out)


if __name__ == "__main__":
    main()
