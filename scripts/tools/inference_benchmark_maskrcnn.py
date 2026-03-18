#!/usr/bin/env python3
"""Run inference benchmark for a Mask R-CNN run and save summary.

Saves `inference_benchmark.json` and a sample overlay `val_batch0_pred.jpg` into the run dir
and appends a short summary to `qa_log.md`.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torchvision
from PIL import Image, ImageDraw
from torchvision import transforms as T


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
    p.add_argument("--weights", type=str, default="best.pth")
    p.add_argument("--coco-json", type=Path, default=Path("data/yolo_dataset/mix_small/coco_annotations.json"))
    p.add_argument("--images-dir", type=Path, default=Path("data/yolo_dataset/mix_small/images"))
    p.add_argument("--device", type=str, default=None)
    p.add_argument("--img-size", type=int, default=256)
    p.add_argument("--max-samples", type=int, default=200)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--iterations", type=int, default=50)
    return p.parse_args()


class SimpleCocoDataset:
    def __init__(self, coco_json, images_dir, transforms=None):
        import json

        with open(coco_json, "r", encoding="utf-8") as f:
            coco = json.load(f)
        self.images = coco["images"]
        self.images_dir = images_dir
        self.transforms = transforms

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        img_info = self.images[idx]
        img_path = self.images_dir / img_info["file_name"]
        img = Image.open(img_path).convert("RGB")
        if self.transforms:
            img_t = self.transforms(img)
        else:
            img_t = T.ToTensor()(img)
        return img, img_t


def overlay_predictions(img: Image.Image, outputs, save_path: Path):
    draw = ImageDraw.Draw(img, "RGBA")
    out = outputs[0]
    masks = out.get("masks")
    boxes = out.get("boxes")
    scores = out.get("scores")
    if masks is not None and masks.numel() > 0:
        masks = (masks > 0.5).squeeze(1).to("cpu").numpy()
        for i, m in enumerate(masks[:5]):
            color = (255, 0, 0, 100)
            pil = Image.fromarray((m * 255).astype("uint8"))
            pil_rgba = Image.new("RGBA", img.size)
            pil_rgba.paste(Image.fromarray(np.zeros((img.size[1], img.size[0], 4), dtype=np.uint8)), (0, 0))
            # draw mask as a semi-transparent overlay
            mask_col = Image.fromarray((m * 255).astype("uint8")).convert("L")
            overlay = Image.new("RGBA", img.size, (255, 0, 0, 0))
            overlay.paste((255, 0, 0, 100), (0, 0), mask_col)
            img = Image.alpha_composite(img.convert("RGBA"), overlay)
    if boxes is not None and boxes.numel() > 0:
        boxes = boxes.to("cpu").numpy()
        for i, b in enumerate(boxes[:10]):
            x1, y1, x2, y2 = b.tolist()
            draw.rectangle([x1, y1, x2, y2], outline=(0, 255, 0, 255), width=2)
    img.convert("RGB").save(save_path)


def main():
    args = parse_args()
    run_dir = args.run_dir
    weights = run_dir / "weights" / args.weights
    if not weights.exists():
        print("Weights not found:", weights)
        return 1

    device = (
        torch.device(args.device)
        if args.device
        else (torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu"))
    )

    # prepare dataset
    transforms = T.Compose([T.Resize(args.img_size), T.ToTensor()])
    dataset = SimpleCocoDataset(args.coco_json, args.images_dir, transforms=transforms)

    # load model
    with open(args.coco_json, "r", encoding="utf-8") as f:
        import json

        coco = json.load(f)
    num_classes = len({c["id"] for c in coco.get("categories", [])}) + 1
    model = torchvision.models.detection.maskrcnn_resnet50_fpn(pretrained=False)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = torchvision.models.detection.faster_rcnn.FastRCNNPredictor(in_features, num_classes)
    in_features_mask = model.roi_heads.mask_predictor.conv5_mask.in_channels
    model.roi_heads.mask_predictor = torchvision.models.detection.mask_rcnn.MaskRCNNPredictor(
        in_features_mask, 256, num_classes
    )
    sd = torch.load(weights, map_location=device)
    model.load_state_dict(sd)
    model.to(device)
    model.eval()

    # warmup
    print("Warming up model for", args.warmup, "iterations")
    with torch.no_grad():
        for i in range(min(args.warmup, len(dataset))):
            img, img_t = dataset[i]
            _ = model([img_t.to(device)])

    times = []
    preds_info = []
    gpu_before = nvidia_snapshot()
    with torch.no_grad():
        for i in range(min(len(dataset), args.max_samples)):
            img, img_t = dataset[i]
            torch.cuda.synchronize() if device.type == "cuda" else None
            t0 = time.time()
            out = model([img_t.to(device)])
            torch.cuda.synchronize() if device.type == "cuda" else None
            t1 = time.time()
            dt_ms = (t1 - t0) * 1000.0
            times.append(dt_ms)
            # store small summary for first N
            if i < 20:
                preds_info.append(
                    {
                        "idx": i,
                        "lat_ms": dt_ms,
                        "n_masks": (
                            int(out[0].get("masks", torch.tensor([])).shape[0])
                            if out[0].get("masks") is not None
                            else 0
                        ),
                    }
                )
            if len(times) >= args.iterations:
                break
    gpu_after = nvidia_snapshot()

    times = np.array(times)
    summary = {
        "run_dir": str(run_dir),
        "weights": str(weights),
        "device": str(device),
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
        img0, img0_t = dataset[0]
        img0_copy = img0.copy()
        with torch.no_grad():
            out0 = model([img0_t.to(device)])
        overlay_predictions(img0_copy, out0, run_dir / "val_batch0_pred.jpg")
        print("Saved sample overlay to", run_dir / "val_batch0_pred.jpg")
    except Exception as e:
        print("Failed to save sample overlay:", e)

    # append summary to qa_log.md
    qa = Path("qa_log.md")
    text = [f"### Inference benchmark: {run_dir.name}", ""]
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
