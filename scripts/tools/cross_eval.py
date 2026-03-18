#!/usr/bin/env python3
"""Cross-evaluate YOLOv8 and Mask R-CNN on the same COCO validation set.

Produces per-model metrics: bbox mAP@0.5, mask mAP@0.5 (approx), mean mask IoU, precision/recall@0.5
and saves a JSON summary to `runs/benchmarks/cross_eval_summary.json`.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--yolo-run-dir", type=Path, required=True)
    p.add_argument("--maskrcnn-run-dir", type=Path, required=True)
    p.add_argument("--coco-json", type=Path, default=Path("data/yolo_dataset/mix_small/coco_annotations.json"))
    p.add_argument("--images-dir", type=Path, default=Path("data/yolo_dataset/mix_small/images"))
    p.add_argument("--max-samples", type=int, default=200)
    p.add_argument("--img-size", type=int, default=256)
    p.add_argument(
        "--use-preds",
        action="store_true",
        help="Load preds from runs/benchmarks/preds_*.json instead of running detectors",
    )
    p.add_argument("--make-overlays", type=int, default=0, help="Generate overlays for N images (0 = none)")
    return p.parse_args()


def bbox_iou(boxA, boxB):
    # boxes are [x,y,w,h]
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
    yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])
    interW = max(0.0, xB - xA)
    interH = max(0.0, yB - yA)
    interArea = interW * interH
    boxAArea = boxA[2] * boxA[3]
    boxBArea = boxB[2] * boxB[3]
    union = boxAArea + boxBArea - interArea
    if union <= 0:
        return 0.0
    return interArea / union


def polygon_to_mask(segmentation, width, height):
    from PIL import ImageDraw

    # segmentation can be:
    # - flat list of floats [x1,y1,x2,y2,...]
    # - list of points [[x1,y1],[x2,y2],...]
    # - list of lists (multiple polygons)
    def _to_points(seg):
        # seg may be flat list
        if not seg:
            return []
        if isinstance(seg[0], (int, float)):
            # flat list
            pts = [(float(seg[i]), float(seg[i + 1])) for i in range(0, len(seg), 2)]
            return pts
        # seg[0] is a list; could be either flat polygon nested in one element [[x1,y1,...]]
        if isinstance(seg[0], (list, tuple)):
            if seg and isinstance(seg[0][0], (int, float)):
                # seg is like [[x1,y1,x2,y2,...]] -> use first element
                flat = seg[0]
                pts = [(float(flat[i]), float(flat[i + 1])) for i in range(0, len(flat), 2)]
                return pts
            # else assume seg is list of [x,y] pairs
            try:
                return [tuple((float(x), float(y))) for x, y in seg]
            except Exception:
                return []
        # unknown format
        return []

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    # handle multiple polygons
    if not segmentation:
        return np.array(mask, dtype=np.uint8)
    if isinstance(segmentation[0], (list, tuple)) and isinstance(segmentation[0][0], (list, tuple)):
        # list of polygons
        for poly in segmentation:
            pts = _to_points(poly)
            if pts:
                draw.polygon(pts, outline=1, fill=1)
    else:
        pts = _to_points(segmentation)
        if pts and len(pts) >= 2:
            draw.polygon(pts, outline=1, fill=1)
    return np.array(mask, dtype=np.uint8)


def mask_iou(gt_mask, pr_mask):
    gt = gt_mask.astype(bool)
    pr = pr_mask.astype(bool)
    inter = np.logical_and(gt, pr).sum()
    union = np.logical_or(gt, pr).sum()
    if union == 0:
        return 0.0
    return float(inter / union)


def ap_from_matches(tp, fp, npos):
    # tp, fp are lists in score-sorted order
    tp_cum = np.cumsum(tp)
    fp_cum = np.cumsum(fp)
    recall = tp_cum / float(npos) if npos > 0 else np.zeros_like(tp_cum)
    precision = tp_cum / np.maximum(tp_cum + fp_cum, 1e-6)
    # compute AP as area under PR curve (numeric)
    # ensure precision envelope
    mpre = np.concatenate(([0.0], precision, [0.0]))
    mrec = np.concatenate(([0.0], recall, [1.0]))
    for i in range(len(mpre) - 1, 0, -1):
        mpre[i - 1] = max(mpre[i - 1], mpre[i])
    idx = np.where(mrec[1:] != mrec[:-1])[0]
    ap = 0.0
    for i in idx:
        ap += (mrec[i + 1] - mrec[i]) * mpre[i + 1]
    return ap, precision, recall


def evaluate_map(predictions, gts, iou_thresh=0.5):
    # predictions: dict image_id -> list of {bbox, score, category_id}
    # gts: dict image_id -> list of {bbox, category_id}

    classes = set()
    for img_id, anns in gts.items():
        for a in anns:
            classes.add(a["category_id"])
    for img_id, preds in predictions.items():
        for p in preds:
            classes.add(p["category_id"])

    ap_per_class = {}
    for cls in sorted(classes):
        preds_list = []
        npos = 0
        gts_by_image = {}
        for img_id, anns in gts.items():
            g = [ann for ann in anns if ann["category_id"] == cls]
            npos += len(g)
            gts_by_image[img_id] = {i: False for i in range(len(g))}
        for img_id, preds in predictions.items():
            for p in preds:
                if p["category_id"] != cls:
                    continue
                preds_list.append((img_id, p["score"], p["bbox"]))
        if not preds_list:
            ap_per_class[cls] = 0.0
            continue
        preds_list.sort(key=lambda x: x[1], reverse=True)
        tp = []
        fp = []
        for img_id, score, bbox in preds_list:
            g = [ann for ann in gts.get(img_id, []) if ann["category_id"] == cls]
            ious = [bbox_iou(bbox, ann["bbox"]) for ann in g]
            assigned = False
            if ious:
                best_i = int(np.argmax(ious))
                if ious[best_i] >= iou_thresh and not gts_by_image[img_id].get(best_i, False):
                    tp.append(1)
                    fp.append(0)
                    gts_by_image[img_id][best_i] = True
                    assigned = True
            if not assigned:
                tp.append(0)
                fp.append(1)
        ap, precision, recall = ap_from_matches(tp, fp, npos)
        ap_per_class[cls] = ap
    if not ap_per_class:
        return 0.0, {}
    mAP = float(np.mean(list(ap_per_class.values())))
    return mAP, ap_per_class


def evaluate_map_across_thresholds(predictions, gts, thresholds=None):
    if thresholds is None:
        thresholds = [round(x, 2) for x in list(np.arange(0.5, 0.96, 0.05))]
    per_thresh = {}
    per_class = defaultdict(lambda: {})
    for t in thresholds:
        mAP, apc = evaluate_map(predictions, gts, iou_thresh=t)
        per_thresh[t] = {"mAP": mAP, "per_class": apc}
        for cls, ap in apc.items():
            per_class[cls][f"ap@{t}"] = ap
    # compute mean AP across thresholds per class and overall
    for cls, dic in per_class.items():
        vals = [v for k, v in dic.items()]
        per_class[cls]["mean_ap_50_95"] = float(np.mean(vals)) if vals else 0.0
    # overall mean across thresholds
    overall_means = [per_thresh[t]["mAP"] for t in thresholds]
    mean_map_50_95 = float(np.mean(overall_means)) if overall_means else 0.0
    return {
        "thresholds": thresholds,
        "per_thresh": per_thresh,
        "per_class": per_class,
        "mean_map_50_95": mean_map_50_95,
    }


def load_coco(coco_json):
    with open(coco_json, "r", encoding="utf-8") as f:
        coco = json.load(f)
    images = coco["images"]
    anns_by_image = defaultdict(list)
    for ann in coco.get("annotations", []):
        anns_by_image[ann["image_id"]].append(ann)
    return images, anns_by_image


def run_detector_on_images(detector, images, images_dir, max_samples):
    preds = {}
    for i, img_info in enumerate(images[:max_samples]):
        img_id = img_info["id"]
        file_name = img_info["file_name"]
        path = images_dir / file_name
        img = Image.open(path).convert("RGB")
        arr = np.array(img)
        res = detector.detect(arr, return_summary=False)
        preds[img_id] = []
        for d in res.detections:
            md = d.metadata or {}
            seg = md.get("segmentation")
            bbox = [d.box.x, d.box.y, d.box.width, d.box.height]
            preds[img_id].append(
                {"bbox": bbox, "score": d.score, "category_id": md.get("class_id", 1), "segmentation": seg}
            )
    return preds


def build_gt_simple(anns_by_image, images, max_samples):
    gt = {}
    for img_info in images[:max_samples]:
        img_id = img_info["id"]
        gt[img_id] = []
        for ann in anns_by_image.get(img_id, []):
            gt[img_id].append(
                {"bbox": ann["bbox"], "category_id": ann["category_id"], "segmentation": ann.get("segmentation")}
            )
    return gt


def compute_mask_mean_iou(preds, gt, images, images_dir, max_samples):
    ious = []
    for img_info in images[:max_samples]:
        img_id = img_info["id"]
        img_w = img_info["width"]
        img_h = img_info["height"]
        gts = gt.get(img_id, [])
        prs = preds.get(img_id, [])
        if not gts or not prs:
            continue
        # For memory reasons, don't materialize all masks at once. Compute per-GT best IoU on the fly.
        for g in gts:
            gseg = g.get("segmentation")
            if not gseg:
                continue
            try:
                gm = polygon_to_mask(gseg, img_w, img_h)
            except Exception:
                continue
            best = 0.0
            for p in prs:
                pseg = p.get("segmentation")
                if not pseg:
                    continue
                try:
                    if (
                        isinstance(pseg, list)
                        and pseg
                        and isinstance(pseg[0], list)
                        and isinstance(pseg[0][0], (int, float))
                        and len(pseg) == img_h
                    ):
                        pm = np.array(pseg, dtype=np.uint8)
                    else:
                        pm = polygon_to_mask(pseg, img_w, img_h)
                except Exception:
                    continue
                i = mask_iou(gm, pm)
                if i > best:
                    best = i
            ious.append(best)
            # free gm
            del gm
    if not ious:
        return 0.0
    return float(np.mean(ious))


def _to_mask_from_seg(seg, width, height):
    # seg can be polygon list or mask list-of-lists
    if seg is None:
        return None
    # mask as list-of-lists (rows)
    if isinstance(seg, list) and seg and isinstance(seg[0], list) and len(seg) == height:
        try:
            arr = np.array(seg, dtype=np.uint8)
            return arr
        except Exception:
            pass
    # polygon(s)
    try:
        m = polygon_to_mask(seg, width, height)
        return m
    except Exception:
        return None


def draw_overlay(image_path, gts, preds_yolo, preds_mask, out_path):
    img = Image.open(image_path).convert("RGBA")
    base = img.copy()
    width, height = base.size
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # draw GT in green
    for g in gts:
        bbox = g.get("bbox")
        if bbox:
            x, y, w, h = bbox
            draw.rectangle([x, y, x + w, y + h], outline=(0, 255, 0, 200), width=2)
        seg = g.get("segmentation")
        mask = _to_mask_from_seg(seg, width, height)
        if mask is not None:
            mimg = Image.fromarray((mask * 128).astype("uint8"))
            color = Image.new("RGBA", base.size, (0, 255, 0, 80))
            overlay = Image.alpha_composite(
                overlay, Image.composite(color, Image.new("RGBA", base.size), mimg.convert("L"))
            )
    # YOLO preds in red
    for p in preds_yolo:
        bbox = p.get("bbox")
        score = p.get("score", 0.0)
        if bbox:
            x, y, w, h = bbox
            draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0, 200), width=2)
            draw.text((x, max(y - 10, 0)), f"Y:{score:.2f}", fill=(255, 0, 0, 220))
        seg = p.get("segmentation")
        mask = _to_mask_from_seg(seg, width, height)
        if mask is not None:
            mimg = Image.fromarray((mask * 255).astype("uint8"))
            color = Image.new("RGBA", base.size, (255, 0, 0, 80))
            overlay = Image.alpha_composite(
                overlay, Image.composite(color, Image.new("RGBA", base.size), mimg.convert("L"))
            )
    # Mask R-CNN preds in blue
    for p in preds_mask:
        bbox = p.get("bbox")
        score = p.get("score", 0.0)
        if bbox:
            x, y, w, h = bbox
            draw.rectangle([x, y, x + w, y + h], outline=(0, 0, 255, 200), width=2)
            draw.text((x, min(y + h + 2, height - 10)), f"M:{score:.2f}", fill=(0, 0, 255, 220))
        seg = p.get("segmentation")
        mask = _to_mask_from_seg(seg, width, height)
        if mask is not None:
            mimg = Image.fromarray((mask * 255).astype("uint8"))
            color = Image.new("RGBA", base.size, (0, 0, 255, 80))
            overlay = Image.alpha_composite(
                overlay, Image.composite(color, Image.new("RGBA", base.size), mimg.convert("L"))
            )
    out = Image.alpha_composite(base, overlay).convert("RGB")
    out.save(out_path, quality=90)


def main():
    args = parse_args()
    images, anns_by_image = load_coco(args.coco_json)
    max_samples = min(args.max_samples, len(images))
    y_run = Path(args.yolo_run_dir)
    # If requested, load existing preds from runs/benchmarks to avoid heavy detector imports
    out_dir = Path("runs/benchmarks")
    preds_yolo = None
    preds_mask = None
    if args.use_preds:
        try:
            with open(out_dir / "preds_yolo.json", "r", encoding="utf-8") as f:
                preds_yolo = json.load(f)
            with open(out_dir / "preds_mask.json", "r", encoding="utf-8") as f:
                preds_mask = json.load(f)
            # convert keys to ints when loaded from json
            preds_yolo = {int(k): v for k, v in preds_yolo.items()}
            preds_mask = {int(k): v for k, v in preds_mask.items()}
            print("Loaded saved predictions from", out_dir)
        except Exception as e:
            print("Failed to load saved preds, will run detectors:", e)

    # prepare detectors lazily only if not using saved preds
    if preds_yolo is None or preds_mask is None:
        # lazy import to avoid heavy deps when not used
        import torch
        import torchvision

        from talk_electronic.services.symbol_detection.yolov8 import YoloV8SegDetector

        # YOLO detector
        yolo_weights = None
        y_run = Path(args.yolo_run_dir)
        cand = y_run / "weights" / "best.pt"
        if cand.exists():
            yolo_weights = str(cand)
        detector_yolo = YoloV8SegDetector(weights_path=yolo_weights, imgsz=args.img_size)

        # Mask R-CNN detector wrapper
        wpath = Path(args.maskrcnn_run_dir) / "weights" / "best.pth"
        if not wpath.exists():
            print("Mask R-CNN weights not found:", wpath)
            return 1
        # build model
        with open(args.coco_json, "r", encoding="utf-8") as f:
            coco = json.load(f)
        num_classes = len({c["id"] for c in coco.get("categories", [])}) + 1
        model = torchvision.models.detection.maskrcnn_resnet50_fpn(pretrained=False)
        in_features = model.roi_heads.box_predictor.cls_score.in_features
        model.roi_heads.box_predictor = torchvision.models.detection.faster_rcnn.FastRCNNPredictor(
            in_features, num_classes
        )
        in_features_mask = model.roi_heads.mask_predictor.conv5_mask.in_channels
        model.roi_heads.mask_predictor = torchvision.models.detection.mask_rcnn.MaskRCNNPredictor(
            in_features_mask, 256, num_classes
        )
        # Use CPU for Mask R-CNN inference to avoid GPU OOM on large images
        device = torch.device("cpu")
        sd = torch.load(wpath, map_location=device)
        model.load_state_dict(sd)
        model.to(device)
        model.eval()

        class MaskRCNNWrapper:
            def __init__(self, model, device):
                self.model = model
                self.device = device

            def detect(self, arr, return_summary=False):
                # arr is numpy RGB
                import torchvision.transforms as T
                from PIL import Image as PILImage

                orig_h, orig_w = arr.shape[0], arr.shape[1]
                # resize to manageable size preserving aspect ratio (min side -> args.img_size)
                target = args.img_size
                if min(orig_h, orig_w) > target:
                    if orig_w < orig_h:
                        new_w = target
                        new_h = int(orig_h * (target / orig_w))
                    else:
                        new_h = target
                        new_w = int(orig_w * (target / orig_h))
                else:
                    new_w, new_h = orig_w, orig_h
                pil_small = PILImage.fromarray(arr).resize((new_w, new_h), resample=PILImage.BILINEAR)
                t = T.ToTensor()(pil_small)
                with torch.no_grad():
                    out = self.model([t.to(self.device)])[0]
                detections = []
                boxes = out.get("boxes")
                scores = out.get("scores")
                masks = out.get("masks")
                labels = out.get("labels")
                n = 0 if boxes is None else len(boxes)
                for i in range(n):
                    b = boxes[i].cpu().numpy()
                    # boxes are in small image coordinates; scale to original
                    x1, y1, x2, y2 = b.tolist()
                    sx = orig_w / float(new_w)
                    sy = orig_h / float(new_h)
                    x1o = float(x1) * sx
                    y1o = float(y1) * sy
                    x2o = float(x2) * sx
                    y2o = float(y2) * sy
                    bbox = [float(x1o), float(y1o), float(x2o - x1o), float(y2o - y1o)]
                    score = float(scores[i].cpu().item()) if scores is not None else 0.0
                    label = int(labels[i].cpu().item()) if labels is not None else 1
                    seg = None
                    if masks is not None and masks.numel() > 0:
                        m = masks[i].squeeze(0).cpu().numpy()
                        # m is mask in small image coords; resize to original size
                        pil = PILImage.fromarray((m * 255).astype("uint8"))
                        pil2 = pil.resize((orig_w, orig_h), resample=PILImage.NEAREST)
                        bin_mask = (np.array(pil2) > 127).astype("uint8")
                        seg = bin_mask.tolist()

                    class Meta:
                        pass

                    class Box:
                        def __init__(self, x, y, w, h):
                            self.x = x
                            self.y = y
                            self.width = w
                            self.height = h

                    from types import SimpleNamespace

                    detections.append(
                        SimpleNamespace(
                            box=Box(bbox[0], bbox[1], bbox[2], bbox[3]),
                            score=score,
                            metadata={"class_id": label, "segmentation": seg},
                        )
                    )
                return SimpleNamespace(detections=detections)

        detector_mask = MaskRCNNWrapper(model, device)

    # run detectors
    images_list = images[:max_samples]
    if preds_yolo is None or preds_mask is None:
        print(f"Running detectors on {len(images_list)} images...")
        preds_yolo = run_detector_on_images(detector_yolo, images_list, args.images_dir, max_samples)
        preds_mask = run_detector_on_images(detector_mask, images_list, args.images_dir, max_samples)
    # detect if YOLO class ids are 0-based; if so, shift by +1 to match COCO (1-based)
    min_cls = None
    for img_id, lst in preds_yolo.items():
        for p in lst:
            cid = p.get("category_id")
            if cid is None:
                continue
            try:
                c = int(cid)
            except Exception:
                continue
            if min_cls is None or c < min_cls:
                min_cls = c
    if min_cls == 0:
        for img_id, lst in preds_yolo.items():
            for p in lst:
                try:
                    p["category_id"] = int(p.get("category_id", 0)) + 1
                except Exception:
                    p["category_id"] = 1

    gt = build_gt_simple(anns_by_image, images_list, max_samples)

    # save preds for inspection (serialize numpy types)
    out_dir = Path("runs/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)

    def _serializable_preds(preds):
        out = {}
        for img_id, lst in preds.items():
            out[img_id] = []
            for p in lst:
                s = {
                    "bbox": [float(x) for x in p.get("bbox", [])],
                    "score": float(p.get("score", 0.0)),
                    "category_id": int(p.get("category_id", 1)),
                }
                seg = p.get("segmentation")
                if seg is None:
                    s["segmentation"] = None
                else:
                    # convert masks/arrays to list-of-lists or keep polygon lists
                    try:
                        if (
                            isinstance(seg, list)
                            and seg
                            and isinstance(seg[0], list)
                            and isinstance(seg[0][0], (int, float))
                        ):
                            s["segmentation"] = seg
                        elif isinstance(seg, list) and seg and isinstance(seg[0], (int, float)):
                            s["segmentation"] = seg
                        else:
                            s["segmentation"] = seg
                    except Exception:
                        s["segmentation"] = None
                out[img_id].append(s)
        return out

    with open(out_dir / "preds_yolo.json", "w", encoding="utf-8") as f:
        json.dump(_serializable_preds(preds_yolo), f)
    with open(out_dir / "preds_mask.json", "w", encoding="utf-8") as f:
        json.dump(_serializable_preds(preds_mask), f)
    # compute per-threshold and per-class APs
    yolo_map_by_thresh = evaluate_map_across_thresholds(preds_yolo, gt)
    mask_map_by_thresh = evaluate_map_across_thresholds(preds_mask, gt)

    # save per-class JSONs
    with open(out_dir / "per_class_yolo.json", "w", encoding="utf-8") as f:
        json.dump(yolo_map_by_thresh, f, indent=2)
    with open(out_dir / "per_class_mask.json", "w", encoding="utf-8") as f:
        json.dump(mask_map_by_thresh, f, indent=2)

    # save per-class CSVs
    def save_per_class_csv(per_class_dict, path):
        # find thresholds from one value
        if not per_class_dict:
            return
        sample_cls = next(iter(per_class_dict))
        keys = list(per_class_dict[sample_cls].keys())
        thresh_keys = sorted([k for k in keys if k.startswith("ap@")], key=lambda x: float(x.split("@")[1]))
        header = ["class_id"] + thresh_keys + ["mean_ap_50_95"]
        with open(path, "w", newline="", encoding="utf-8") as csvf:
            w = csv.writer(csvf)
            w.writerow(header)
            for cls, vals in sorted(per_class_dict.items()):
                row = [cls] + [vals.get(k, 0.0) for k in thresh_keys] + [vals.get("mean_ap_50_95", 0.0)]
                w.writerow(row)

    save_per_class_csv(yolo_map_by_thresh["per_class"], out_dir / "per_class_yolo.csv")
    save_per_class_csv(mask_map_by_thresh["per_class"], out_dir / "per_class_mask.csv")
    # compute bbox mAP@0.5 (read from per-threshold results)
    yolo_map50 = yolo_map_by_thresh["per_thresh"].get(0.5, {}).get("mAP", 0.0)
    mask_map50 = mask_map_by_thresh["per_thresh"].get(0.5, {}).get("mAP", 0.0)

    # compute mean mask IoU
    yolo_miou = compute_mask_mean_iou(preds_yolo, gt, images_list, args.images_dir, max_samples)
    mask_miou = compute_mask_mean_iou(preds_mask, gt, images_list, args.images_dir, max_samples)

    summary = {
        "yolo": {"map50_box": yolo_map50, "mean_mask_iou": yolo_miou, "samples": max_samples},
        "maskrcnn": {"map50_box": mask_map50, "mean_mask_iou": mask_miou, "samples": max_samples},
    }
    # extend with mean mAP@50:95
    summary["yolo"]["mean_map_50_95"] = yolo_map_by_thresh.get(
        "mean_map_50_95", yolo_map_by_thresh.get("mean_map_50_95", 0.0)
    )
    summary["maskrcnn"]["mean_map_50_95"] = mask_map_by_thresh.get(
        "mean_map_50_95", mask_map_by_thresh.get("mean_map_50_95", 0.0)
    )

    out_dir = Path("runs/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cross_eval_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("Saved cross-eval summary to", out_path)

    # append short summary to qa_log.md
    qa = Path("qa_log.md")
    text = [f"### Cross-eval: {y_run.name} vs {Path(args.maskrcnn_run_dir).name}", ""]
    text.append(f"YOLO bbox mAP@0.5: {summary['yolo']['map50_box']:.4f}")
    text.append(f"Mask R-CNN bbox mAP@0.5: {summary['maskrcnn']['map50_box']:.4f}")
    text.append(f"YOLO mean mask IoU: {summary['yolo']['mean_mask_iou']:.4f}")
    text.append(f"Mask R-CNN mean mask IoU: {summary['maskrcnn']['mean_mask_iou']:.4f}")
    text = "\n".join(text) + "\n"
    try:
        qa_text = qa.read_text(encoding="utf-8")
        qa_text = qa_text.rstrip() + "\n\n" + text
        qa.write_text(qa_text, encoding="utf-8")
        print("Appended cross-eval summary to qa_log.md")
    except Exception as e:
        print("Failed to append to qa_log.md:", e)

    # Generate overlays if requested
    if args.make_overlays and args.make_overlays > 0:
        overlays_dir = out_dir / "overlays"
        overlays_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for img_info in images_list[: args.make_overlays]:
            img_id = img_info["id"]
            file_name = img_info.get("file_name")
            image_path = args.images_dir / file_name
            gts_img = gt.get(img_id, [])
            preds_y = preds_yolo.get(img_id, [])
            preds_m = preds_mask.get(img_id, [])
            out_path = overlays_dir / f"{img_id}_overlay.jpg"
            try:
                draw_overlay(image_path, gts_img, preds_y, preds_m, out_path)
                count += 1
            except Exception as e:
                print("Failed to create overlay for", img_id, e)
        print(f"Saved {count} overlays to", overlays_dir)


if __name__ == "__main__":
    main()
