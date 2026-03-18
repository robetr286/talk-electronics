#!/usr/bin/env python3
"""Per-class threshold tuner: compute PR curves from preds and GT and suggest thresholds.

Produces:
- runs/benchmarks/thresholds/thresholds_yolo.json (per-class suggested thresholds)
- runs/benchmarks/thresholds/per_class_pr_<class_id>.png
- runs/benchmarks/thresholds/thresholds_yolo.csv
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--preds", type=Path, required=True)
    p.add_argument("--coco", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("runs/benchmarks/thresholds"))
    p.add_argument("--max-samples", type=int, default=200)
    p.add_argument("--iou", type=float, default=0.5)
    p.add_argument("--min-recall", type=float, default=0.5, help="minimum recall floor for precision-based threshold")
    return p.parse_args()


def bbox_iou(boxA, boxB):
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


def load_coco(coco_json):
    with open(coco_json, "r", encoding="utf-8") as f:
        coco = json.load(f)
    images = coco["images"]
    anns_by_image = defaultdict(list)
    for ann in coco.get("annotations", []):
        anns_by_image[ann["image_id"]].append(ann)
    categories = [c["id"] for c in coco.get("categories", [])]
    return images, anns_by_image, categories


def prepare_preds(preds_json: Dict, images_list: List[Dict]):
    ids = {img["id"] for img in images_list}
    preds = {}
    for k, v in preds_json.items():
        try:
            kid = int(k)
        except Exception:
            continue
        if kid in ids:
            preds[kid] = v
    return preds


def compute_pr_for_class(cls_id, preds, gts, images_list, iou_thresh=0.5, thresholds=None):
    if thresholds is None:
        thresholds = np.linspace(0.0, 1.0, 101)
    npos = 0
    for img_info in images_list:
        img_id = img_info["id"]
        g = [a for a in gts.get(img_id, []) if a["category_id"] == cls_id]
        npos += len(g)

    precisions = []
    recalls = []
    f1s = []
    for thr in thresholds:
        tp = 0
        fp = 0
        for img_info in images_list:
            img_id = img_info["id"]
            g = [a for a in gts.get(img_id, []) if a["category_id"] == cls_id]
            preds_here = [
                p
                for p in preds.get(img_id, [])
                if int(p.get("category_id", 1)) == cls_id and p.get("score", 0.0) >= thr
            ]
            assigned = [False] * len(g)
            for p in sorted(preds_here, key=lambda x: x.get("score", 0.0), reverse=True):
                best_iou = 0.0
                best_idx = -1
                for i, ann in enumerate(g):
                    if assigned[i]:
                        continue
                    iou = bbox_iou(p.get("bbox", []), ann.get("bbox", []))
                    if iou > best_iou:
                        best_iou = iou
                        best_idx = i
                if best_idx >= 0 and best_iou >= iou_thresh:
                    tp += 1
                    assigned[best_idx] = True
                else:
                    fp += 1
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / npos if npos > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)
    return thresholds, np.array(precisions), np.array(recalls), np.array(f1s)


def main():
    args = parse_args()
    images, anns_by_image, categories = load_coco(args.coco)
    images_list = images[: args.max_samples]
    with open(args.preds, "r", encoding="utf-8") as f:
        preds_json = json.load(f)
    preds = prepare_preds(preds_json, images_list)
    args.out.mkdir(parents=True, exist_ok=True)

    results = {}
    import csv

    csv_out = args.out / "thresholds_yolo.csv"
    with open(csv_out, "w", newline="", encoding="utf-8") as csvf:
        w = csv.writer(csvf)
        w.writerow(["class_id", "best_thr_f1", "f1", "thr_prec_at_minrec", "prec_at_minrec", "rec_at_minrec"])
        for cls in categories:
            thr, prec, rec, f1 = compute_pr_for_class(cls, preds, anns_by_image, images_list, iou_thresh=args.iou)
            best_idx = int(np.argmax(f1))
            best_thr = float(thr[best_idx])
            best_f1 = float(f1[best_idx])
            cand_idxs = np.where(rec >= args.min_recall)[0]
            if len(cand_idxs) > 0:
                best_idx2 = cand_idxs[np.argmax(prec[cand_idxs])]
                thr_prec = float(thr[best_idx2])
                prec_at = float(prec[best_idx2])
                rec_at = float(rec[best_idx2])
            else:
                thr_prec = best_thr
                prec_at = float(prec[best_idx])
                rec_at = float(rec[best_idx])
            results[cls] = {
                "best_thr_f1": best_thr,
                "best_f1": best_f1,
                "thr_prec_at_minrec": thr_prec,
                "prec_at_minrec": prec_at,
                "rec_at_minrec": rec_at,
            }
            plt.figure(figsize=(5, 4))
            plt.plot(rec, prec, label=f"class {cls}")
            plt.xlabel("Recall")
            plt.ylabel("Precision")
            plt.title(f"PR curve class {cls}")
            plt.grid(True)
            plt.scatter([rec[best_idx]], [prec[best_idx]], color="red", label=f"F1@{best_thr:.2f}")
            plt.legend()
            plt.tight_layout()
            plt.savefig(args.out / f"per_class_pr_{cls}.png", dpi=150)
            plt.close()
            w.writerow([cls, best_thr, best_f1, thr_prec, prec_at, rec_at])

    with open(args.out / "thresholds_yolo.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("Saved thresholds and PR plots to", args.out)


if __name__ == "__main__":
    main()
