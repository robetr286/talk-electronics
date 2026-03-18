#!/usr/bin/env python3
"""Run inference benchmark for a YOLOv8 run and save summary.

Saves `inference_benchmark.json` and a sample overlay `val_batch0_pred_yolo.jpg` into the run dir
and appends a short summary to `qa_log.md`.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


def nvidia_snapshot():
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
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


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--weights", type=str, default="best.pt")
    p.add_argument("--images-dir", type=Path, default=Path("data/yolo_dataset/mix_small/images"))
    p.add_argument("--coco-json", type=Path, default=Path("data/yolo_dataset/mix_small/coco_annotations.json"))
    p.add_argument("--device", type=str, default=None)
    p.add_argument("--img-size", type=int, default=256)
    p.add_argument("--max-samples", type=int, default=200)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--iterations", type=int, default=50)
    return p.parse_args()


class SimpleCocoDataset:
    def __init__(self, coco_json, images_dir):
        import json

        with open(coco_json, "r", encoding="utf-8") as f:
            coco = json.load(f)
        self.images = coco["images"]
        self.images_dir = images_dir

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        img_info = self.images[idx]
        img_path = self.images_dir / img_info["file_name"]
        img = Image.open(img_path).convert("RGB")
        return img, np.array(img)


def overlay_predictions(img: Image.Image, detections, save_path: Path):
    draw = ImageDraw.Draw(img, "RGBA")
    # detections: list of dicts with box and optional segmentation polygon list
    for det in detections[:20]:
        box = det.get("box")
        seg = det.get("segmentation")
        score = det.get("score", 0.0)
        if seg:
            # segmentation is list of [x,y] pairs
            try:
                polygon = [tuple(p) for p in seg]
                overlay = Image.new("RGBA", img.size, (255, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay, "RGBA")
                overlay_draw.polygon(polygon, fill=(255, 0, 0, 80))
                img = Image.alpha_composite(img.convert("RGBA"), overlay)
            except Exception:
                pass
        if box:
            x, y, w, h = box
            x2 = x + w
            y2 = y + h
            draw.rectangle([x, y, x2, y2], outline=(0, 255, 0, 255), width=2)
            draw.text((x + 2, y + 2), f"{score:.2f}", fill=(255, 255, 255, 255))
    img.convert("RGB").save(save_path)


def main():
    args = parse_args()
    run_dir = args.run_dir
    candidate = run_dir / "weights" / args.weights
    if candidate.exists():
        weights = candidate
    else:
        weights = None
        print(f"Weight file {candidate} not found; resolving using detector fallback candidates (env / weights/).")

    dataset = SimpleCocoDataset(args.coco_json, args.images_dir)

    # prepare detector (import lazily to avoid module-level import after code)
    from talk_electronic.services.symbol_detection.yolov8 import YoloV8SegDetector

    detector = YoloV8SegDetector(weights_path=str(weights) if weights else None, imgsz=args.img_size)

    # warmup
    print("Warming up detector for", args.warmup, "iterations")
    for i in range(min(args.warmup, len(dataset))):
        img, img_arr = dataset[i]
        detector.detect(img_arr, return_summary=False)

    times = []
    preds_info = []
    gpu_before = nvidia_snapshot()
    for i in range(min(len(dataset), args.max_samples)):
        img, img_arr = dataset[i]
        # synchronize if torch.cuda is available
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.synchronize()
        except Exception:
            pass
        t0 = time.time()
        res = detector.detect(img_arr, return_summary=False)
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.synchronize()
        except Exception:
            pass
        t1 = time.time()
        dt_ms = (t1 - t0) * 1000.0
        times.append(dt_ms)
        if i < 20:
            preds_info.append({"idx": i, "lat_ms": dt_ms, "n_detections": len(res.detections)})
        if len(times) >= args.iterations:
            break
    gpu_after = nvidia_snapshot()

    times = np.array(times)
    summary = {
        "run_dir": str(run_dir),
        "weights": str(weights),
        "device": detector._device,
        "samples": int(len(times)),
        "mean_latency_ms": float(np.mean(times)) if len(times) else None,
        "median_latency_ms": float(np.median(times)) if len(times) else None,
        "std_latency_ms": float(np.std(times)) if len(times) else None,
        "fps": float(1000.0 / np.mean(times)) if len(times) else None,
        "gpu_before": gpu_before,
        "gpu_after": gpu_after,
        "preds_examples": preds_info,
    }

    out_path = run_dir / "inference_benchmark.json"
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("Saved inference benchmark to", out_path)

    # save visualization for first sample
    try:
        img0, img0_arr = dataset[0]
        det0 = detector.detect(img0_arr, return_summary=False)
        # build simple serializable detections for overlay
        serial = []
        for d in det0.detections:
            md = d.metadata or {}
            seg = md.get("segmentation")
            box = [d.box.x, d.box.y, d.box.width, d.box.height]
            serial.append({"box": box, "segmentation": seg, "score": d.score})
        overlay_predictions(img0.copy(), serial, run_dir / "val_batch0_pred_yolo.jpg")
        print("Saved sample overlay to", run_dir / "val_batch0_pred_yolo.jpg")
    except Exception as e:
        print("Failed to save sample overlay:", e)

    # append summary to qa_log.md
    qa = Path("qa_log.md")
    text = [f"### Inference benchmark (YOLO): {run_dir.name}", ""]
    text.append(
        f"Mean latency (ms): {summary['mean_latency_ms']:.2f}" if summary["mean_latency_ms"] else "Mean latency: N/A"
    )
    text.append(f"FPS (est.): {summary['fps']:.2f}" if summary["fps"] else "FPS: N/A")
    text.append(f"Samples measured: {summary['samples']}")
    text = "\n".join(text) + "\n"
    try:
        qa_text = qa.read_text(encoding="utf-8")
        qa_text = qa_text.rstrip() + "\n\n" + text
        qa.write_text(qa_text, encoding="utf-8")
        print("Appended inference summary to qa_log.md")
    except Exception as e:
        print("Failed to append to qa_log.md:", e)


if __name__ == "__main__":
    main()
