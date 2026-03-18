#!/usr/bin/env python3
"""Generate example overlays for classes where YOLO underperforms vs Mask R-CNN."""
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path("runs/benchmarks")
COCO = Path("data/yolo_dataset/mix_small/coco_annotations.json")


def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def bbox_to_rect(b):
    x, y, w, h = b
    return [x, y, x + w, y + h]


def draw_example(image_path, gts, y_preds, m_preds, out_path, cls_id):
    img = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    # draw GTs for class
    for g in gts:
        if g["category_id"] != cls_id:
            continue
        draw.rectangle(bbox_to_rect(g["bbox"]), outline=(0, 255, 0), width=3)
    # YOLO preds for class in red
    for p in y_preds:
        if p["category_id"] != cls_id:
            continue
        draw.rectangle(bbox_to_rect(p["bbox"]), outline=(255, 0, 0), width=2)
        draw.text((p["bbox"][0], p["bbox"][1]), f"Y {p.get('score',0):.2f}", fill=(255, 0, 0))
    # Mask preds for class in blue
    for p in m_preds:
        if p["category_id"] != cls_id:
            continue
        draw.rectangle(bbox_to_rect(p["bbox"]), outline=(0, 0, 255), width=2)
        draw.text((p["bbox"][0], p["bbox"][1] + 10), f"M {p.get('score',0):.2f}", fill=(0, 0, 255))
    img.convert("RGB").save(out_path, quality=90)


def main(top_k=3, examples_per_class=5):
    # read csv for ordering
    csvp = ROOT / "per_class_comparison.csv"
    lines = [line.strip() for line in open(csvp, "r", encoding="utf-8").read().splitlines()[1:]]
    class_ids = [int(line.split(",")[0]) for line in lines[:top_k]]

    coco = load_json(COCO)
    anns = coco.get("annotations", [])
    anns_by_img = {}
    for a in anns:
        anns_by_img.setdefault(a["image_id"], []).append(a)
    images = {im["id"]: im for im in coco.get("images", [])}

    preds_y = load_json(ROOT / "preds_yolo.json")
    preds_m = load_json(ROOT / "preds_mask.json")

    outdir = ROOT / "failure_examples"
    outdir.mkdir(parents=True, exist_ok=True)

    for cls in class_ids:
        saved = 0
        for img_id, img_info in images.items():
            if saved >= examples_per_class:
                break
            gts = anns_by_img.get(img_id, [])
            if not any(a["category_id"] == cls for a in gts):
                continue
            yps = preds_y.get(str(img_id), []) if str(img_id) in preds_y else preds_y.get(img_id, [])
            mps = preds_m.get(str(img_id), []) if str(img_id) in preds_m else preds_m.get(img_id, [])
            img_path = Path("data/yolo_dataset/mix_small/images") / img_info["file_name"]
            outp = outdir / f"cls{cls}_img{img_id}.jpg"
            try:
                draw_example(img_path, gts, yps, mps, outp, cls)
                saved += 1
            except Exception as e:
                print("failed", img_id, e)
    print("examples saved to", outdir)


if __name__ == "__main__":
    main()
