from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - pillow optional
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore


def _create_ignore_mask(ignore_regions: List[Dict], img_w: int, img_h: int):
    if Image is None:
        raise RuntimeError("Pillow required to create masks")

    mask = Image.new("L", (img_w, img_h), 0)
    draw = ImageDraw.Draw(mask)
    for reg in ignore_regions:
        if reg.get("type") == "polygon":
            pts = [tuple(p) for p in reg.get("points", [])]
            if pts:
                draw.polygon(pts, fill=255)
    return mask


def filter_detections_by_polygons(
    detections: List[Dict], ignore_regions: List[Dict], image_shape: Tuple[int, int], iou_threshold: float = 0.3
) -> Tuple[List[Dict], int]:
    """
    Remove detections that overlap ignore regions above the given IoU threshold.

    detections: list of dicts; each dict must contain key 'bbox' = [x,y,w,h] in pixel coordinates.
    ignore_regions: list of {"type":"polygon","points":[[x,y],..]}
    image_shape: (height, width) or (h, w). We'll accept either but treat as (h,w)
    Returns (filtered_detections, removed_count)
    """
    if not ignore_regions or not detections:
        return detections, 0

    # Normalize image shape
    if len(image_shape) != 2:
        raise ValueError("image_shape must be (height, width)")
    img_h, img_w = image_shape

    if Image is None:
        # If pillow is not available, fall back to simple bbox-vs-bbox test using ignore polygon bboxes
        rem = []
        for det in detections:
            x, y, w, h = det.get("bbox", [0, 0, 0, 0])
            keep = True
            for reg in ignore_regions:
                if reg.get("type") == "polygon":
                    xs = [pt[0] for pt in reg.get("points", [])]
                    ys = [pt[1] for pt in reg.get("points", [])]
                    if not xs or not ys:
                        continue
                    rx_min, rx_max = min(xs), max(xs)
                    ry_min, ry_max = min(ys), max(ys)
                    # compute IoU of bboxes
                    ix1 = max(x, rx_min)
                    iy1 = max(y, ry_min)
                    ix2 = min(x + w, rx_max)
                    iy2 = min(y + h, ry_max)
                    inter_w = max(0, ix2 - ix1)
                    inter_h = max(0, iy2 - iy1)
                    inter_area = inter_w * inter_h
                    bbox_area = max(1.0, w * h)
                    iou = inter_area / bbox_area
                    if iou >= iou_threshold:
                        keep = False
                        break
            if keep:
                rem.append(det)
        removed = len(detections) - len(rem)
        return rem, removed

    # Create mask
    mask = _create_ignore_mask(ignore_regions, img_w, img_h)
    # convert mask later into numpy array

    mask_np = np.array(mask, dtype=np.uint8) > 0

    kept = []
    removed_count = 0
    for det in detections:
        x, y, w, h = det.get("bbox", [0, 0, 0, 0])
        x1 = int(max(0, round(x)))
        y1 = int(max(0, round(y)))
        x2 = int(min(img_w, round(x + w)))
        y2 = int(min(img_h, round(y + h)))

        if x2 <= x1 or y2 <= y1:
            kept.append(det)
            continue

        bbox_area = (x2 - x1) * (y2 - y1)
        if bbox_area <= 0:
            kept.append(det)
            continue

        sub = mask_np[y1:y2, x1:x2]
        overlap = int(sub.sum())
        iou = overlap / float(bbox_area)
        if iou >= iou_threshold:
            removed_count += 1
        else:
            kept.append(det)

    return kept, removed_count


def filter_detections_with_mask(
    detections: List[Dict],
    mask_data,
    iou_threshold: float = 0.3,
) -> Tuple[List[Dict], int]:
    """Filter detections using a precomputed mask array (True = ignore pixel)."""

    if mask_data is None or not detections:
        return detections, 0

    mask_array = np.asarray(mask_data)
    if mask_array.ndim == 3:
        mask_array = mask_array[..., 0]
    if mask_array.ndim != 2:
        raise ValueError("mask_data must be 2D")

    mask_bool = mask_array.astype(bool)
    img_h, img_w = mask_bool.shape

    kept: List[Dict] = []
    removed = 0
    for det in detections:
        x, y, w, h = det.get("bbox", [0, 0, 0, 0])
        x1 = int(max(0, round(x)))
        y1 = int(max(0, round(y)))
        x2 = int(min(img_w, round(x + w)))
        y2 = int(min(img_h, round(y + h)))

        if x2 <= x1 or y2 <= y1:
            kept.append(det)
            continue

        bbox_area = (x2 - x1) * (y2 - y1)
        if bbox_area <= 0:
            kept.append(det)
            continue

        overlap = int(mask_bool[y1:y2, x1:x2].sum())
        iou = overlap / float(bbox_area)
        if iou >= iou_threshold:
            removed += 1
        else:
            kept.append(det)

    return kept, removed
