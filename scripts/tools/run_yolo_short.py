"""Run a short YOLOv8 fine-tune for reproducible local testing.

Usage (PowerShell):

  C:/Users/DELL/miniconda3/envs/talk_flask/python.exe scripts/tools/run_yolo_short.py --data data/yolo_dataset/mix_small/dataset.yaml --epochs 10 --imgsz 256 --batch 1 --device cuda --workers 0

This script trains `yolov8n-seg.pt` for the given number of epochs and writes outputs to `runs/yolo_short`.
"""

import argparse
import time
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("data/yolo_dataset/mix_small/dataset.yaml"))
    p.add_argument(
        "--model", type=str, default="yolov8n-seg.pt", help="YOLO model weights to use (e.g., yolov8s-seg.pt)"
    )
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--imgsz", type=int, default=256)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--device", type=str, default="cuda")
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--output-dir", type=Path, default=Path("runs/yolo_short"))
    args = p.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()

    from ultralytics import YOLO

    model = YOLO(args.model)
    model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        save_period=1,
        plots=False,
        val=True,
    )

    end = time.monotonic()
    with open(args.output_dir / "run_info.txt", "w", encoding="utf8") as f:
        f.write(f"epochs={args.epochs}, imgsz={args.imgsz}, batch={args.batch}, device={args.device}\n")
        f.write(f"time_sec={end-start:.1f}\n")


if __name__ == "__main__":
    main()
