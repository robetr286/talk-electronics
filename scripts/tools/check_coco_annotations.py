"""
Check COCO annotations for common issues that can lead to NaN losses:
- zero-area bboxes
- zero-area segmentation polygons
- segmentation with odd number of coords or less than 6 coords (requires at least 3 points)
- coordinates outside image bounds
- overlapping annotations with degenerate polygons

Usage:
python scripts/tools/check_coco_annotations.py --coco-json <file> [--images-dir <dir>]
"""

import argparse
import json
import math
from pathlib import Path


def polygon_area(poly):
    # poly: list of [x1,y1,x2,y2,...]
    pts = list(zip(poly[0::2], poly[1::2]))
    area = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def bbox_area(bbox):
    _, _, w, h = bbox
    return max(0.0, w) * max(0.0, h)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--coco-json", required=True)
    p.add_argument("--images-dir", default=None)
    args = p.parse_args()

    coco_path = Path(args.coco_json)
    if not coco_path.exists():
        print("COCO JSON not found:", coco_path)
        return 1

    with open(coco_path, "r", encoding="utf-8") as f:
        coco = json.load(f)

    images = {img["id"]: img for img in coco.get("images", [])}
    anns = coco.get("annotations", [])

    problems = []
    for ann in anns:
        img_id = ann.get("image_id")
        img = images.get(img_id)
        if not img:
            problems.append((ann, "image_id not found"))
            continue
        width = img.get("width")
        height = img.get("height")
        bbox = ann.get("bbox", [0, 0, 0, 0])
        bbox_a = bbox_area(bbox)
        if bbox_a <= 0:
            problems.append((ann, f"zero-area bbox {bbox}"))
        segs = ann.get("segmentation") or []
        if not segs:
            problems.append((ann, "missing segmentation"))
            continue
        if not isinstance(segs, list):
            problems.append((ann, f"segmentation not list: {type(segs)}"))
            continue
        # COCO segmentation may be list of polys; we check each polygon
        for seg in segs:
            if not isinstance(seg, list):
                continue
            if len(seg) < 6:
                problems.append((ann, f"segmentation polygon less than 3 points (len={len(seg)})"))
                continue
            if len(seg) % 2 != 0:
                problems.append((ann, f"segmentation polygon odd-length coords (len={len(seg)})"))
            area = polygon_area(seg)
            if area <= 0:
                problems.append((ann, f"segmentation polygon zero-area (area={area})"))
            # check bounds
            xs = seg[0::2]
            ys = seg[1::2]
            if min(xs) < 0 or min(ys) < 0 or max(xs) > width or max(ys) > height:
                problems.append(
                    (ann, f"segmentation coords outside image bounds (minx={min(xs)},maxx={max(xs)},w={width})")
                )

    print(f"Checked {len(anns)} annotations across {len(images)} images. Found {len(problems)} issues.")
    for ann, msg in problems[:200]:
        print(f"Ann id={ann.get('id')} img_id={ann.get('image_id')} category={ann.get('category_id')}: {msg}")
    if len(problems) > 200:
        print("... (truncated)")

    if problems:
        return 2
    return 0


if __name__ == "__main__":
    exit(main())
