#!/usr/bin/env python3
"""Gather a short report for a Mask R-CNN PoC run and append to qa_log.md.

Loads best checkpoint and computes mean IoU on provided COCO JSON dataset (default same as YOLO mix_small tool).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torchvision
from PIL import Image
from torchvision import transforms as T


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--coco-json", type=Path, default=Path("data/yolo_dataset/mix_small/coco_annotations.json"))
    p.add_argument("--images-dir", type=Path, default=Path("data/yolo_dataset/mix_small/images"))
    p.add_argument("--weights", type=str, default="best.pth")
    p.add_argument("--img-size", type=int, default=512)
    return p.parse_args()


def polygon_to_mask(segmentation, width, height):
    from PIL import ImageDraw

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon(segmentation, outline=1, fill=1)
    return np.array(mask, dtype=np.uint8)


class FastCocoDataset:
    def __init__(self, coco_json, images_dir, transforms=None):
        with open(coco_json, "r", encoding="utf-8") as f:
            coco = json.load(f)
        self.images = coco["images"]
        self.anns = coco["annotations"]
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
        masks = []
        for ann in ann_list:
            seg = ann["segmentation"][0]
            bbox = ann["bbox"]
            x1, y1, w_box, h_box = bbox
            x2 = x1 + w_box
            y2 = y1 + h_box
            boxes.append([x1, y1, x2, y2])
            masks.append(polygon_to_mask(seg, w, h))

        if self.transforms:
            img = self.transforms(img)
        else:
            from torchvision import transforms as T

            img = T.ToTensor()(img)

        # If resize was set, scale masks similarly to the resize transform to match model outputs
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
            masks = scaled_masks

        target = {"boxes": boxes, "masks": masks}
        return img, target


def evaluate_iou(model, dataset, device):
    model.eval()
    ious = []
    import torch

    with torch.no_grad():
        for i in range(len(dataset)):
            img, target = dataset[i]
            imgs = [img.to(device)]
            outputs = model(imgs)
            out = outputs[0]
            out_masks = out.get("masks")
            if out_masks is None or out_masks.numel() == 0 or not target["masks"]:
                continue
            # Move to CPU and compute per-gt IoU sequentially to avoid large memory usage
            gt = torch.tensor(target["masks"], dtype=torch.uint8, device="cpu").bool()
            pr = (out_masks > 0.5).squeeze(1).to("cpu").bool()
            if pr.numel() == 0 or gt.numel() == 0:
                continue
            for gi in range(gt.shape[0]):
                gt_vec = gt[gi].reshape(-1).float()
                max_iou = 0.0
                for pj in range(pr.shape[0]):
                    pr_vec = pr[pj].reshape(-1).float()
                    inter = (gt_vec * pr_vec).sum()
                    union = (gt_vec + pr_vec - gt_vec * pr_vec).sum()
                    if union.item() == 0:
                        continue
                    iou = inter / (union + 1e-6)
                    if iou > max_iou:
                        max_iou = iou.item()
                ious.append(float(max_iou))
    if not ious:
        return 0.0
    return float(np.mean(ious))


def main():
    args = parse_args()
    run_dir = args.run_dir
    weights_dir = run_dir / "weights"
    wpath = weights_dir / args.weights
    if not wpath.exists():
        print("Weights not found:", wpath)
        return 1

    # prepare dataset
    transforms = T.Compose([T.Resize(args.img_size), T.ToTensor()])
    dataset = FastCocoDataset(args.coco_json, args.images_dir, transforms=transforms)

    # load model
    with open(args.coco_json, "r", encoding="utf-8") as f:
        coco = json.load(f)
    num_classes = len({c["id"] for c in coco.get("categories", [])}) + 1
    model = torchvision.models.detection.maskrcnn_resnet50_fpn(pretrained=False)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = torchvision.models.detection.faster_rcnn.FastRCNNPredictor(in_features, num_classes)
    in_features_mask = model.roi_heads.mask_predictor.conv5_mask.in_channels
    model.roi_heads.mask_predictor = torchvision.models.detection.mask_rcnn.MaskRCNNPredictor(
        in_features_mask, 256, num_classes
    )
    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    sd = torch.load(wpath, map_location=device)
    model.load_state_dict(sd)
    model.to(device)

    iou = evaluate_iou(model, dataset, device)

    # create summary
    epochs = len(list(weights_dir.glob("epoch*.pth")))
    summary = [
        f"### Report: {run_dir.name}",
        "",
        f"Epochs checkpoints: {epochs}",
        f"Weights: {wpath.as_posix()}",
        f"Mean IoU (masks) on dataset: {iou:.4f}",
    ]
    text = "\n".join(summary) + "\n"
    print(text)

    qa = Path("qa_log.md")
    qa_text = qa.read_text(encoding="utf-8")
    qa_text = qa_text.rstrip() + "\n\n" + text
    qa.write_text(qa_text, encoding="utf-8")
    print("Appended Mask R-CNN report to qa_log.md")


if __name__ == "__main__":
    sys.exit(main())
