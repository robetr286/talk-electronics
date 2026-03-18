#!/usr/bin/env python3
"""Minimal Mask R-CNN PoC training script using torchvision.

Train a small Mask R-CNN on COCO-style JSON produced by scripts/export_yolo_to_coco.py.

Usage example:
  python scripts/experiments/run_maskrcnn_poc.py \
    --coco-json data/yolo_dataset/mix_small/coco_annotations.json \
    --images-dir data/yolo_dataset/mix_small/images --output runs/segment/exp_maskrcnn_poc --epochs 10 --batch 1
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List

import numpy as np
import torch
import torchvision
from PIL import Image, ImageDraw
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms as T


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--coco-json", required=True, type=Path)
    p.add_argument("--images-dir", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--device", type=str, default=None, choices=["cpu", "cuda"], help="Device to use (cpu or cuda)")
    p.add_argument("--img-size", type=int, default=640, help="Resize image short side (pixels) to limit memory usage")
    p.add_argument("--lr", type=float, default=0.005, help="Learning rate")
    p.add_argument(
        "--collect-report",
        action="store_true",
        help="After training completes, automatically run report collection and inference benchmark",
    )
    return p.parse_args()


def polygon_to_mask(segmentation: List[float], width: int, height: int):
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    # segmentation is a flat list [x1,y1,x2,y2...]
    draw.polygon(segmentation, outline=1, fill=1)
    return np.array(mask, dtype=np.uint8)


class CocoLikeDataset(Dataset):
    def __init__(self, coco_json: Path, images_dir: Path, transforms=None):
        with open(coco_json, "r", encoding="utf-8") as f:
            coco = json.load(f)

        self.images = coco["images"]
        self.anns = coco["annotations"]
        # Build index: image_id -> list of annotations
        self.anns_by_image = {}
        for ann in self.anns:
            self.anns_by_image.setdefault(ann["image_id"], []).append(ann)

        self.images_dir = images_dir
        self.transforms = transforms
        # detect Resize transform size from transforms if provided
        self.resize_size = None
        if transforms is not None and hasattr(transforms, "transforms"):
            for t in transforms.transforms:
                try:
                    if isinstance(t, T.Resize):
                        size = t.size
                        if isinstance(size, int):
                            self.resize_size = size
                        elif isinstance(size, (tuple, list)):
                            # pick smaller dimension
                            self.resize_size = min(size)
                except Exception:
                    pass

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        img_info = self.images[idx]
        img_id = img_info["id"]
        img_path = self.images_dir / img_info["file_name"]
        img = Image.open(img_path).convert("RGB")
        w, h = img.size

        ann_list = self.anns_by_image.get(img_id, [])
        boxes = []
        labels = []
        masks = []
        areas = []

        for ann in ann_list:
            seg = ann["segmentation"][0]
            # seg contains pixel coords
            bbox = ann["bbox"]
            x1, y1, w_box, h_box = bbox
            x2 = x1 + w_box
            y2 = y1 + h_box
            boxes.append([x1, y1, x2, y2])
            labels.append(int(ann["category_id"]))
            mask = polygon_to_mask(seg, w, h)
            masks.append(mask)
            areas.append(float(ann.get("area", w_box * h_box)))

        boxes = torch.as_tensor(boxes, dtype=torch.float32) if boxes else torch.zeros((0, 4), dtype=torch.float32)
        labels = torch.as_tensor(labels, dtype=torch.int64) if labels else torch.zeros((0,), dtype=torch.int64)
        # If resize is set, scale mask to the resized image size
        if self.resize_size and masks:
            # compute new dims preserving aspect similar to torchvision.Resize
            if w < h:
                new_w = self.resize_size
                new_h = int(h * new_w / w)
            else:
                new_h = self.resize_size
                new_w = int(w * new_h / h)
            from PIL import Image as PILImage

            scaled_masks = []
            for m in masks:
                pil = PILImage.fromarray(m)
                pil2 = pil.resize((new_w, new_h), resample=PILImage.NEAREST)
                scaled_masks.append(np.array(pil2, dtype=np.uint8))
            if scaled_masks:
                scaled_masks = np.array(scaled_masks, dtype=np.uint8)  # szybciej niż konwersja z listy tablic
                masks = torch.as_tensor(scaled_masks, dtype=torch.uint8)
            else:
                masks = torch.zeros((0, new_h, new_w), dtype=torch.uint8)

            # Scale boxes to match resized image dimensions
            # boxes are [x1, y1, x2, y2] in original image coords
            if boxes.numel():
                scale_x = new_w / float(w)
                scale_y = new_h / float(h)
                boxes = boxes.clone()
                boxes[:, 0] = boxes[:, 0] * scale_x
                boxes[:, 2] = boxes[:, 2] * scale_x
                boxes[:, 1] = boxes[:, 1] * scale_y
                boxes[:, 3] = boxes[:, 3] * scale_y
        else:
            masks = torch.as_tensor(masks, dtype=torch.uint8) if masks else torch.zeros((0, h, w), dtype=torch.uint8)
        image_id = torch.tensor([img_id])

        target = {
            "boxes": boxes,
            "labels": labels,
            "masks": masks,
            "image_id": image_id,
            "area": torch.as_tensor(areas, dtype=torch.float32) if areas else torch.tensor([]),
            "iscrowd": torch.zeros((len(areas),), dtype=torch.int64) if areas else torch.tensor([]),
        }

        if self.transforms:
            img = self.transforms(img)
        else:
            img = T.ToTensor()(img)

        return img, target


def collate_fn(batch):
    return tuple(zip(*batch))


def get_model(num_classes):
    # load an instance segmentation model pre-trained on COCO
    model = torchvision.models.detection.maskrcnn_resnet50_fpn(pretrained=True)
    # replace the classifier with a new one, that has num_classes which is user-defined
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = torchvision.models.detection.faster_rcnn.FastRCNNPredictor(in_features, num_classes)
    # now get the number of input features for the mask classifier
    in_features_mask = model.roi_heads.mask_predictor.conv5_mask.in_channels
    hidden_layer = 256
    model.roi_heads.mask_predictor = torchvision.models.detection.mask_rcnn.MaskRCNNPredictor(
        in_features_mask, hidden_layer, num_classes
    )
    return model


def evaluate_iou(model, dataloader, device):
    model.eval()
    ious = []
    with torch.no_grad():
        for imgs, targets in dataloader:
            imgs = [img.to(device) for img in imgs]
            outputs = model(imgs)
            # take first image / target
            out = outputs[0]
            tgt = targets[0]
            gt_masks = (
                tgt["masks"].to(device).bool()
                if tgt["masks"].numel()
                else torch.zeros((0, imgs[0].shape[1], imgs[0].shape[2]), dtype=torch.bool, device=device)
            )
            pred_masks = out.get("masks", torch.zeros((0, imgs[0].shape[1], imgs[0].shape[2]), device=device)).bool()

            # If no preds or no gts, skip
            if gt_masks.numel() == 0 or pred_masks.numel() == 0:
                continue

            # compute IoU per gt sequentially to avoid large intermediate tensors (memory-safe)
            for gi in range(gt_masks.shape[0]):
                gt_vec = gt_masks[gi].reshape(-1).float()
                max_iou = 0.0
                for pj in range(pred_masks.shape[0]):
                    pr_vec = pred_masks[pj].reshape(-1).float()
                    inter = (gt_vec * pr_vec).sum()
                    union = (gt_vec + pr_vec - gt_vec * pr_vec).sum()
                    if union.item() == 0:
                        continue
                    iou = inter / (union + 1e-6)
                    if iou > max_iou:
                        max_iou = iou.item()
                ious.append(float(max_iou))
            # replaced dense matrix IoU with sequential per-gt checks to be memory-safe

    if not ious:
        return 0.0
    return float(np.mean(ious))


def train_loop(model, train_loader, optimizer, device, epoch):
    model.train()
    running_loss = 0.0
    for batch_idx, (imgs, targets) in enumerate(train_loader):
        imgs = [img.to(device) for img in imgs]
        # move tensors in targets to device
        targets = [{k: (v.to(device) if isinstance(v, torch.Tensor) else v) for k, v in t.items()} for t in targets]
        loss_dict = model(imgs, targets)
        losses = sum(loss for loss in loss_dict.values())

        # debug: check for NaN/inf in losses
        if not torch.isfinite(losses):
            print(f"Warning: Non-finite loss at epoch {epoch} batch {batch_idx}: loss={losses}")
            print("Loss dict:")
            for k, v in loss_dict.items():
                try:
                    print(f"  {k}: {float(v)}")
                except Exception:
                    print(f"  {k}: (could not convert)")
            # print some target statistics
            try:
                t = targets[0]
                img_id_val = int(t.get("image_id")[0].item()) if "image_id" in t else None
                if img_id_val is not None:
                    print(f" target image_id: {img_id_val}")
                # print boxes shape and min/max separately so lines stay under 120 chars
                print(f" target boxes shape: {t['boxes'].shape}")
                try:
                    print(f" target boxes min/max: {t['boxes'].min().item()}/{t['boxes'].max().item()}")
                except Exception:
                    print(" target boxes min/max: (could not compute)")
                if t["masks"].numel():
                    print(f" target masks sum: {t['masks'].sum().item()}")
                if t.get("labels") is not None and getattr(t.get("labels"), "numel", None):
                    try:
                        print(
                            f" target labels min/max: {int(t['labels'].min().item())}/{int(t['labels'].max().item())}"
                        )
                    except Exception:
                        print(" target labels: (could not compute min/max)")
            except Exception:
                pass
            # skip this batch to avoid breaking
            continue

        optimizer.zero_grad()
        try:
            losses.backward()
            # gradient clipping to prevent explosion
            try:
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            except Exception:
                pass
        except Exception as e:
            print(f"Backward failed at epoch {epoch} batch {batch_idx}: {e}")
            continue
        optimizer.step()
        running_loss += losses.item()

    avg_loss = running_loss / len(train_loader)
    print(f"Epoch {epoch} training loss: {avg_loss:.4f}")
    return avg_loss


def main():
    args = parse_args()
    if args.device:
        device = torch.device(args.device)
    else:
        device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "weights").mkdir(parents=True, exist_ok=True)

    # Load coco
    with open(args.coco_json, "r", encoding="utf-8") as f:
        coco = json.load(f)
    num_classes = len({c["id"] for c in coco.get("categories", [])}) + 1

    # resize + to tensor (shorter side resized to img_size, keep aspect)
    transforms = T.Compose([T.Resize(args.img_size), T.ToTensor()])
    dataset = CocoLikeDataset(args.coco_json, args.images_dir, transforms=transforms)
    train_loader = DataLoader(
        dataset, batch_size=args.batch, shuffle=True, num_workers=args.workers, collate_fn=collate_fn
    )

    print(f"Dataset length: {len(dataset)} images, batch size: {args.batch}, workers: {args.workers}, device: {device}")

    model = get_model(num_classes)
    model.to(device)

    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(params, lr=args.lr, momentum=0.9, weight_decay=0.0005)

    best_loss = float("inf")
    for epoch in range(1, args.epochs + 1):
        try:
            train_loss = train_loop(model, train_loader, optimizer, device, epoch)
        except Exception as e:
            print(f"Training failed at epoch {epoch}: {e}")
            break

        # save checkpoint
        ckpt_path = out_dir / "weights" / f"epoch{epoch}.pth"
        try:
            torch.save(model.state_dict(), ckpt_path)
            torch.save(model.state_dict(), out_dir / "weights" / "last.pth")
        except Exception as e:
            print("Error saving weights", e)
            break
        if train_loss < best_loss:
            best_loss = train_loss
            torch.save(model.state_dict(), out_dir / "weights" / "best.pth")

        # quick eval
        iou = evaluate_iou(model, train_loader, device)
        print(f"Epoch {epoch} quick IoU mean: {iou:.4f}")

    print("Training complete. Artifacts saved to:", out_dir)

    # write a marker file to indicate run finished (helpful for external watchers)
    try:
        (out_dir / "run_complete").write_text("done", encoding="utf-8")
    except Exception as e:
        print("Warning: failed to write run_complete marker:", e)

    # optionally collect reports + inference benchmark
    if args.collect_report:
        import subprocess

        print("Collecting Mask R-CNN report and running inference benchmark...")
        subprocess.run([sys.executable, "scripts/tools/gather_maskrcnn_report.py", "--run-dir", str(out_dir)])
        subprocess.run([sys.executable, "scripts/tools/inference_benchmark_maskrcnn.py", "--run-dir", str(out_dir)])


if __name__ == "__main__":
    main()
