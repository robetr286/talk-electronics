#!/usr/bin/env python3
"""
Export Label Studio polygons/rectangles with label(s) 'ignore_region' (or configurable labels)
to per-image JSON files with `ignore_regions` and optional mask PNGs.

Usage:
  python scripts/export_labelstudio_to_ignore.py --input data/annotations/labelstudio_exports/project.json \
        --out tests/fixtures/p1_line_examples/annotations --images-dir data/images --labels ignore_region

The script expects a Label Studio export format (list of tasks). For each task it creates
`<image_base>.json` containing fields:
  {
    "image": "<filename>",
    "ignore_regions": [ {"type":"polygon","points": [[x,y], ...]}, ... ]
  }

Optionally a binary mask PNG can be created next to the JSON when --make-masks is passed
and an images directory is available to read image dimensions.

"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - pillow is optional
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore


def _rotated_rect_to_polygon(value: Dict[str, Any], img_w: int, img_h: int) -> List[List[float]]:
    # Reuse same coords as export_labelstudio_to_coco_seg - rectangle in % -> convert to four points
    import math

    x_pct = value["x"]
    y_pct = value["y"]
    w_pct = value["width"]
    h_pct = value["height"]
    rot = float(value.get("rotation", 0.0))

    x = (x_pct / 100.0) * img_w
    y = (y_pct / 100.0) * img_h
    w = (w_pct / 100.0) * img_w
    h = (h_pct / 100.0) * img_h

    cx = x + w / 2.0
    cy = y + h / 2.0
    angle = math.radians(-rot)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)

    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    pts: List[List[float]] = []
    for dx, dy in corners:
        x_rot = cx + (dx * cos_a - dy * sin_a)
        y_rot = cy + (dx * sin_a + dy * cos_a)
        pts.append([x_rot, y_rot])

    return pts


def _polygon_pct_to_abs(points_pct: List[List[float]], img_w: int, img_h: int) -> List[List[float]]:
    pts: List[List[float]] = []
    for x_pct, y_pct in points_pct:
        pts.append([(x_pct / 100.0) * img_w, (y_pct / 100.0) * img_h])
    return pts


def convert_labelstudio_to_ignore(
    ls_export: List[Dict[str, Any]], out_dir: Path, images_dir: Path | None, labels: List[str], make_masks: bool = False
):
    out_dir.mkdir(parents=True, exist_ok=True)
    masks_dir = out_dir / "masks"
    if make_masks:
        masks_dir.mkdir(parents=True, exist_ok=True)

    for task in ls_export:
        # Try to resolve image filename
        try:
            image_ref = task["data"].get("image") or task["data"].get("url")
            if not image_ref:
                continue
            image_name = Path(str(image_ref)).name

            # default fallback dimensions if not available
            img_w = task["data"].get("width") or None
            img_h = task["data"].get("height") or None

            if img_w is None or img_h is None:
                # try to read from images_dir
                if images_dir:
                    candidate = images_dir / image_name
                    if candidate.exists() and Image is not None:
                        with Image.open(candidate) as img:
                            img_w, img_h = img.size

            img_w = int(img_w) if img_w else 1000
            img_h = int(img_h) if img_h else 1000

        except Exception:
            continue

        ignore_regions: List[Dict[str, Any]] = []

        # Label Studio groups many annotation passes under 'annotations', each having 'result'
        for group in task.get("annotations", []) or task.get("result", []) or []:
            # group might be dict with 'result' or be a top-level result
            results = group.get("result") if isinstance(group, dict) and "result" in group else group
            if not isinstance(results, list):
                continue

            for r in results:
                typ = r.get("type")
                val = r.get("value") or {}
                # check possible label container keys
                label = None
                if typ and "labels" in typ:
                    # not reliable; check known keys
                    label = val.get("polygonlabels") or val.get("rectanglelabels") or val.get("brushlabels")

                # fallback - try to find label name in value
                if not label:
                    for key in ("polygonlabels", "rectanglelabels", "brushlabels", "labels", "choices"):
                        if key in val:
                            label = val.get(key)
                            break

                if isinstance(label, list) and label:
                    label_name = label[0]
                elif isinstance(label, str):
                    label_name = label
                else:
                    label_name = None

                if not label_name or label_name not in labels:
                    # skip non-ignore shapes
                    continue

                # Polygon
                if typ == "polygonlabels" and "points" in val:
                    points_pct = val["points"]
                    pts_abs = _polygon_pct_to_abs(points_pct, img_w, img_h)
                    ignore_regions.append({"type": "polygon", "points": pts_abs, "label": label_name})

                # Rectangle (possibly rotated)
                elif typ == "rectanglelabels" and all(k in val for k in ("x", "y", "width", "height")):
                    pts_abs = _rotated_rect_to_polygon(val, img_w, img_h)
                    ignore_regions.append({"type": "polygon", "points": pts_abs, "label": label_name})

                # Brush/mask - Label Studio can export bitmap as base64 (not handled here robustly)
                elif typ == "brushlabels":
                    # Save a placeholder entry with the raw value so downstream code can inspect it
                    ignore_regions.append({"type": "brush", "value": val})

        # Write per-image ignore json if any found
        if ignore_regions:
            out_path = out_dir / f"{Path(image_name).stem}.json"
            payload = {"image": image_name, "ignore_regions": ignore_regions}
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)

            # Optionally create mask PNG combining polygons
            if make_masks and Image is not None and ignore_regions:
                mask = Image.new("L", (img_w, img_h), 0)
                draw = ImageDraw.Draw(mask)
                for reg in ignore_regions:
                    if reg.get("type") == "polygon":
                        flat = [tuple(pt) for pt in reg["points"]]
                        # ImageDraw expects sequence of tuples
                        draw.polygon(flat, fill=255)
                mask_path = masks_dir / f"{Path(image_name).stem}_ignore_mask.png"
                mask.save(mask_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True, help="Label Studio export JSON")
    parser.add_argument("--out", "-o", required=True, help="Output directory for per-image ignore JSONs")
    parser.add_argument("--images-dir", default=None, help="Local images directory (for mask sizing)")
    parser.add_argument("--labels", default="ignore_region", help="Comma separated labels to treat as ignore regions")
    parser.add_argument(
        "--make-masks", action="store_true", help="Create binary mask PNGs for ignore regions (requires Pillow)"
    )

    args = parser.parse_args()
    ls_path = Path(args.input)
    out_dir = Path(args.out)
    images_dir = Path(args.images_dir) if args.images_dir else None
    labels = [label_str.strip() for label_str in args.labels.split(",") if label_str.strip()]

    with ls_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    # Label Studio exports either a dict with 'tasks' or a top-level list
    tasks = data.get("tasks") if isinstance(data, dict) and "tasks" in data else data

    convert_labelstudio_to_ignore(tasks, out_dir, images_dir, labels, make_masks=args.make_masks)


if __name__ == "__main__":
    main()
