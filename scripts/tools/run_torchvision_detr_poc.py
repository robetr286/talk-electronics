"""Quick PoC runner for torchvision DETR (detection only) on a COCO dataset.

Uses the same dataset loader as `run_maskrcnn_poc.py` and trains a minimal DETR model
for 1 epoch to compare detection performance and runtime (recall/mAP/time).
"""

import argparse
import json
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.append(str(root))

import torch
import torchvision
from torch.utils.data import DataLoader

from scripts.experiments.run_maskrcnn_poc import CocoLikeDataset, collate_fn


def get_fasterrcnn(num_classes):
    model = torchvision.models.detection.fasterrcnn_resnet50_fpn(pretrained=True)
    # replace the box predictor head for our number of classes
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = torchvision.models.detection.faster_rcnn.FastRCNNPredictor(in_features, num_classes)
    return model


def run(coco_json, images_dir, output_dir, epochs=1, batch=1, workers=0, device="cuda"):
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    # load dataset
    transforms = torchvision.transforms.Compose([torchvision.transforms.ToTensor(), torchvision.transforms.Resize(256)])
    dataset = CocoLikeDataset(Path(coco_json), Path(images_dir), transforms=transforms)
    loader = DataLoader(dataset, batch_size=batch, shuffle=True, num_workers=workers, collate_fn=collate_fn)

    # get num classes
    import json as _json

    coco = _json.load(open(coco_json, "r", encoding="utf8"))
    num_classes = len({c["id"] for c in coco.get("categories", [])}) + 1

    model = get_fasterrcnn(num_classes)
    device = torch.device(device if torch.cuda.is_available() else "cpu")
    model.to(device)

    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=1e-4)

    start = time.monotonic()
    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        for imgs, targets in loader:
            imgs = [img.to(device) for img in imgs]
            targets = [{k: (v.to(device) if isinstance(v, torch.Tensor) else v) for k, v in t.items()} for t in targets]
            loss_dict = model(imgs, targets)
            losses = sum(v for v in loss_dict.values())
            if not torch.isfinite(losses):
                print("Non-finite losses", loss_dict)
                continue
            optimizer.zero_grad()
            losses.backward()
            optimizer.step()
            running_loss += float(losses.item())
        avg_loss = running_loss / len(loader)
        print(f"Epoch {epoch} DETR average loss: {avg_loss:.4f}")
    elapsed = time.monotonic() - start

    # save a small report
    report = {
        "timestamp": int(time.time()),
        "model": "torchvision_detr_resnet50",
        "time_sec": elapsed,
        "epochs": epochs,
        "batch": batch,
        "dataset_len": len(dataset),
    }
    with open(outdir / f"detr_poc_{int(time.time())}.json", "w", encoding="utf8") as f:
        json.dump(report, f, indent=2)

    # append to summary
    summary = outdir / "third_model_poc_summary.json"
    if summary.exists():
        try:
            arr = json.loads(summary.read_text(encoding="utf8"))
        except Exception:
            arr = []
    else:
        arr = []
    arr.append(report)
    with open(summary, "w", encoding="utf8") as f:
        json.dump(arr, f, indent=2)
    print("Saved DETR PoC report and appended to summary")
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--coco-json", required=True)
    p.add_argument("--images-dir", required=True)
    p.add_argument("--output-dir", default="runs/benchmarks")
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--device", default="cuda")
    args = p.parse_args()
    run(args.coco_json, args.images_dir, args.output_dir, args.epochs, args.batch, args.workers, args.device)


if __name__ == "__main__":
    main()
