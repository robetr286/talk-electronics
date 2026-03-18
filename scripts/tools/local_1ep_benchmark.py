#!/usr/bin/env python3
"""Run a 1-epoch benchmark for YOLOv8 and Mask R-CNN locally and collect timing/usage.

The script runs a single epoch for YOLOv8 (via ultralytics API) and Mask R-CNN PoC
(`scripts/experiments/run_maskrcnn_poc.py`) and writes a small JSON report with timings
and optional GPU memory snapshots (via nvidia-smi if available).

Usage example:
  python scripts/tools/local_1ep_benchmark.py \
    --yolo-data data/yolo_dataset/mix_small/dataset.yaml \
    --coco-json data/yolo_dataset/mix_small/coco_annotations_small.json \
    --images-dir data/yolo_dataset/mix_small/images \
    --device cuda --workers 0

"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def nvidia_snapshot():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL,
        )
        rows = out.decode("utf8").strip().splitlines()
        res = []
        for r in rows:
            used, total, util = [int(x.strip()) for x in r.split(",")]
            res.append({"memory_used_mb": used, "memory_total_mb": total, "utilization_pct": util})
        return res
    except Exception:
        return None


def run_yolo(yolo_data, device, epochs, imgsz, batch, workers, output_dir):
    start = time.monotonic()
    gpu_before = nvidia_snapshot()
    try:
        from ultralytics import YOLO

        # allow choosing different pretrained YOLO weights (e.g., yolov8s-seg.pt)
        model = YOLO(run_yolo.yolo_model)
        results = model.train(
            data=str(yolo_data),
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=device if device in ("cpu", "cuda") else device,
            workers=workers,
            save_period=1,
            plots=False,
            val=True,
        )
        success = True
        save_dir = str(results.save_dir)
    except Exception as e:
        print("YOLO training failed:", e)
        success = False
        save_dir = None
    end = time.monotonic()
    gpu_after = nvidia_snapshot()
    return {
        "model": run_yolo.yolo_model,
        "success": success,
        "save_dir": save_dir,
        "time_sec": end - start,
        "gpu_before": gpu_before,
        "gpu_after": gpu_after,
    }


def run_maskrcnn(coco_json, images_dir, device, epochs, img_size, batch, workers, output_dir):
    start = time.monotonic()
    gpu_before = nvidia_snapshot()
    cmd = [
        sys.executable,
        str(Path(__file__).parents[1].resolve() / "experiments" / "run_maskrcnn_poc.py"),
        "--coco-json",
        str(coco_json),
        "--images-dir",
        str(images_dir),
        "--output",
        str(output_dir / "exp_maskrcnn_bench"),
        "--epochs",
        str(epochs),
        "--batch",
        str(batch),
        "--img-size",
        str(img_size),
        "--workers",
        str(workers),
    ]
    if device:
        cmd += ["--device", device]
    try:
        subprocess.check_call(cmd)
        success = True
    except subprocess.CalledProcessError as e:
        print("Mask R-CNN training failed:", e)
        success = False
    end = time.monotonic()
    gpu_after = nvidia_snapshot()
    return {
        "model": "maskrcnn_resnet50_fpn",
        "success": success,
        "save_dir": str(output_dir / "exp_maskrcnn_bench"),
        "time_sec": end - start,
        "gpu_before": gpu_before,
        "gpu_after": gpu_after,
    }


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--yolo-data", type=Path, default=Path("data/yolo_dataset/mix_small/dataset.yaml"))
    p.add_argument("--coco-json", type=Path, default=Path("data/yolo_dataset/mix_small/coco_annotations_small.json"))
    p.add_argument("--images-dir", type=Path, default=Path("data/yolo_dataset/mix_small/images"))
    p.add_argument("--device", type=str, default=None, help="cuda or cpu or device index for YOLO")
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--imgsz", type=int, default=256)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--output-dir", type=Path, default=Path("runs/benchmarks"))
    p.add_argument(
        "--yolo-model",
        type=str,
        default="yolov8n-seg.pt",
        help="pretrained YOLO model weights to use (file or model name)",
    )
    p.add_argument("--models", nargs="+", choices=["yolo", "maskrcnn"], default=["yolo", "maskrcnn"])
    return p.parse_args()


def main():
    args = parse_args()
    # attach chosen yolo model to run_yolo function for simple access
    run_yolo.yolo_model = args.yolo_model
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": timestamp,
        "device": args.device,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "workers": args.workers,
        "results": [],
    }
    if "yolo" in args.models:
        print("Running YOLOv8 1-epoch benchmark...")
        res = run_yolo(
            args.yolo_data,
            args.device,
            epochs=1,
            imgsz=args.imgsz,
            batch=args.batch,
            workers=args.workers,
            output_dir=args.output_dir,
        )
        report["results"].append(res)

    if "maskrcnn" in args.models:
        print("Running Mask R-CNN 1-epoch benchmark...")
        res = run_maskrcnn(
            args.coco_json,
            args.images_dir,
            args.device if args.device else "cuda",
            epochs=1,
            img_size=args.imgsz,
            batch=args.batch,
            workers=args.workers,
            output_dir=args.output_dir,
        )
        report["results"].append(res)

    out = args.output_dir / f"benchmark_{timestamp}.json"
    with open(out, "w", encoding="utf8") as f:
        json.dump(report, f, indent=2)
    print("Benchmark complete. Report saved to:", out)


if __name__ == "__main__":
    main()
