#!/usr/bin/env python3
"""Evaluate OCR candidate models on a folder of samples (ocr_eval/ci-samples).

Outputs a JSON report and CSV summary in `reports/ocr_eval_results.json`.

Simplified pipeline:
- For each image/json pair in --input-dir:
  - load ground-truth components (components[].label, components[].value and bbox in percent)
  - run model -> get detections [{text, bbox_px: (x0,y0,x1,y1)}]
  - spatial-join: for each component check if any detection center lies inside its bbox and text contains label/value
  - compute aggregate metrics per model: label_coverage_pct, value_coverage_pct, avg_detections_per_image

Notes:
- Bbox in Label Studio is percent (x,y,w,h) where x,y are percentage of image width/height. We convert to pixels.
- Models: tesseract, easyocr, paddleocr, doctr, surya. If a model wrapper fails, it will be skipped and reported.

Usage:
  python scripts/evaluate_ocr_candidates.py --input-dir ocr_eval/ci-samples --out-dir reports
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image


def normalize_text(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum() or ch.isspace()) if s else ""


def normalize_token(s: str) -> str:
    """Normalized token without spaces or punctuation for robust matching"""
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


# ----------------------------- detection wrappers -----------------------------


def run_tesseract(img: Image.Image) -> List[Dict[str, Any]]:
    try:
        import pytesseract
        from pytesseract import Output
    except Exception as e:
        raise RuntimeError("pytesseract import failed: %s" % e)
    data = pytesseract.image_to_data(img, output_type=Output.DICT)
    out = []
    n = len(data.get("text", []))
    for i in range(n):
        text = data["text"][i]
        if not text or text.strip() == "":
            continue
        x = int(data["left"][i])
        y = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])
        out.append({"text": text, "bbox": (x, y, x + w, y + h)})
    return out


def run_easyocr(img: Image.Image) -> List[Dict[str, Any]]:
    try:
        import easyocr
    except Exception as e:
        raise RuntimeError("easyocr import failed: %s" % e)
    # create reader once per module invocation
    reader = easyocr.Reader(["en"], gpu=False)
    results = reader.readtext(np.array(img))
    out = []
    for bbox, text, _ in results:
        # bbox is list of 4 points
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        out.append({"text": text, "bbox": (int(x0), int(y0), int(x1), int(y1))})
    return out


def run_paddleocr(img: Image.Image) -> List[Dict[str, Any]]:
    try:
        from paddleocr import PaddleOCR
    except Exception as e:
        raise RuntimeError("paddleocr import failed: %s" % e)
    ocr_engine = PaddleOCR(use_angle_cls=True, lang="en")
    res = ocr_engine.ocr(img, cls=True)
    out = []
    for line in res:
        # each line: [bbox, (text, score)] — score not used
        bbox, (text, _) = line[0], line[1]
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        out.append({"text": text, "bbox": (int(x0), int(y0), int(x1), int(y1))})
    return out


def run_doctr(img: Image.Image) -> List[Dict[str, Any]]:
    try:
        from doctr.models import ocr_predictor
    except Exception as e:
        raise RuntimeError("doctr import failed: %s" % e)
    model = ocr_predictor(pretrained=True)
    arr = np.array(img.convert("RGB"))
    res = model([arr])
    out = []
    # traverse pages->blocks->lines->words
    for page in res.pages:
        for block in page.blocks:
            for line in block.lines:
                for word in line.words:
                    text = word.value
                    bbox = word.geometry.to_dict()  # {x,y,w,h} normalized to 0..1
                    # convert to px
                    w_px, h_px = img.size
                    x = int(bbox["x"] * w_px)
                    y = int(bbox["y"] * h_px)
                    w = int(bbox["w"] * w_px)
                    h = int(bbox["h"] * h_px)
                    out.append({"text": text, "bbox": (x, y, x + w, y + h)})
    return out


def run_surya(img: Image.Image) -> List[Dict[str, Any]]:
    # Surya APIs vary; try common patterns
    try:
        import surya_ocr as surya
    except Exception:
        try:
            import surya
        except Exception as e:
            raise RuntimeError("surya import failed: %s" % e)
    # try surya.simple_ocr or surya.run or surya.ocr
    # we'll attempt to call surya.__call__ or surya.ocr(image)
    # fallback: try a normalized usage where surya.ocr returns list of {text, bbox}
    for fn in (
        getattr(surya, "ocr", None),
        getattr(surya, "predict", None),
        getattr(surya, "read", None),
        getattr(surya, "__call__", None),
    ):
        if fn is None:
            continue
        try:
            res = fn(img)
            # expect res to be list of (text,bbox) or dicts
            out = []
            for item in res:
                if isinstance(item, dict) and "text" in item and "bbox" in item:
                    out.append({"text": item["text"], "bbox": tuple(item["bbox"])})
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    text = item[0]
                    bbox = tuple(item[1])
                    out.append({"text": text, "bbox": bbox})
            if out:
                return out
        except Exception:
            continue
    raise RuntimeError("surya: could not run OCR with detected APIs")


# ----------------------------- helpers ---------------------------------------

# numpy is imported at top-level (valid across runners)


def center_of_bbox(bbox: Tuple[int, int, int, int]) -> Tuple[int, int]:
    x0, y0, x1, y1 = bbox
    return ((x0 + x1) // 2, (y0 + y1) // 2)


def point_in_bbox(px: int, py: int, bbox: Tuple[int, int, int, int]) -> bool:
    x0, y0, x1, y1 = bbox
    return x0 <= px <= x1 and y0 <= py <= y1


def bbox_overlap(b1: Tuple[int, int, int, int], b2: Tuple[int, int, int, int]) -> int:
    x0 = max(b1[0], b2[0])
    y0 = max(b1[1], b2[1])
    x1 = min(b1[2], b2[2])
    y1 = min(b1[3], b2[3])
    if x1 < x0 or y1 < y0:
        return 0
    return (x1 - x0) * (y1 - y0)


def comp_bbox_px(comp: Dict, img_w: int, img_h: int) -> Tuple[int, int, int, int]:
    # comp bbox is [x%, y%, w%, h%]
    b = comp.get("bbox")
    if not b or len(b) != 4:
        return (0, 0, img_w - 1, img_h - 1)
    x_pct, y_pct, w_pct, h_pct = b
    x = int(x_pct / 100.0 * img_w)
    y = int(y_pct / 100.0 * img_h)
    w = int(w_pct / 100.0 * img_w)
    h = int(h_pct / 100.0 * img_h)
    return (x, y, x + max(1, w), y + max(1, h))


# ----------------------------- main evaluation -------------------------------

MODEL_RUNNERS = {
    "tesseract": run_tesseract,
    "easyocr": run_easyocr,
    "paddleocr": run_paddleocr,
    "doctr": run_doctr,
    "surya": run_surya,
}


def evaluate(models: List[str], input_dir: Path, out_dir: Path, max_images: int = None):
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = sorted(Path(input_dir).glob("*.json"))
    if max_images:
        samples = samples[:max_images]

    results = {}
    for model in models:
        print(f"Running model: {model}")
        runner = MODEL_RUNNERS.get(model)
        if not runner:
            print(f"  No runner for {model}, skipping")
            continue
        stats = defaultdict(int)
        total_components = 0
        total_values = 0
        total_detections = 0
        images_processed = 0
        errors = []
        for sj in samples:
            try:
                obj = json.loads(sj.read_text(encoding="utf8"))
            except Exception as e:
                errors.append(f"Failed to read {sj}: {e}")
                continue
            img_candidates = [
                p for p in Path(input_dir).glob(f"{sj.stem}.*") if p.suffix.lower() in [".png", ".jpg", ".jpeg"]
            ]
            if not img_candidates:
                errors.append(f"Image for {sj} not found")
                continue
            img_path = img_candidates[0]
            img = Image.open(img_path).convert("RGB")
            w, h = img.size
            # run model
            try:
                dets = runner(img)
            except Exception as e:
                errors.append(f"Model {model} failed on {sj.name}: {e}")
                dets = []
            total_detections += len(dets)

            # normalize detected texts
            for d in dets:
                d["text_norm"] = normalize_text(d.get("text") or "")

            comps = obj.get("components") or []
            total_components += len(comps)
            # count values
            for comp in comps:
                label = normalize_text(comp.get("label") or "")
                value = normalize_text(comp.get("value") or "")
                cbbox = comp_bbox_px(comp, w, h)
                total_values += 1 if value else 0

                # global detections matching
                found_label_global = False
                found_value_global = False
                for d in dets:
                    cx, cy = center_of_bbox(d["bbox"])
                    overlap = bbox_overlap(d["bbox"], cbbox)
                    if point_in_bbox(cx, cy, cbbox) or overlap > 0:
                        dtoken = normalize_token(d.get("text_norm") or "")
                        if normalize_token(label) and normalize_token(label) in dtoken:
                            found_label_global = True
                        if normalize_token(value) and normalize_token(value) in dtoken:
                            found_value_global = True

                # localized crop OCR if needed
                found_label_local = False
                found_value_local = False
                if (not found_label_global and label) or (not found_value_global and value):
                    pad_w = int((cbbox[2] - cbbox[0]) * 0.8)
                    pad_h = int((cbbox[3] - cbbox[1]) * 0.8)
                    cx0 = max(0, cbbox[0] - pad_w)
                    cy0 = max(0, cbbox[1] - pad_h)
                    cx1 = min(w, cbbox[2] + pad_w)
                    cy1 = min(h, cbbox[3] + pad_h)
                    crop = img.crop((cx0, cy0, cx1, cy1))
                    try:
                        crop_dets = runner(crop)
                        for cd in crop_dets:
                            cd_text = normalize_token(normalize_text(cd.get("text") or ""))
                            if (
                                (not found_label_global)
                                and normalize_token(label)
                                and normalize_token(label) in cd_text
                            ):
                                found_label_local = True
                            if (
                                (not found_value_global)
                                and normalize_token(value)
                                and normalize_token(value) in cd_text
                            ):
                                found_value_local = True
                    except Exception as e:
                        errors.append(f"Local OCR failed for {sj.name} comp {comp.get('id')}: {e}")

                found_label = found_label_global or found_label_local
                found_value = found_value_global or found_value_local
                if found_label:
                    stats["label_hits"] += 1
                if found_value:
                    stats["value_hits"] += 1
            images_processed += 1
            # small progress
        # compute metrics
        label_cov = (stats["label_hits"] / total_components * 100.0) if total_components else 0.0
        value_cov = (stats["value_hits"] / total_values * 100.0) if total_values else 0.0
        avg_dets = (total_detections / images_processed) if images_processed else 0.0
        results[model] = {
            "images": images_processed,
            "total_components": total_components,
            "label_hits": int(stats["label_hits"]),
            "value_hits": int(stats["value_hits"]),
            "label_coverage_pct": round(label_cov, 2),
            "value_coverage_pct": round(value_cov, 2),
            "avg_detections_per_image": round(avg_dets, 2),
            "errors": errors,
        }
        print(
            f"  done {model}: label_cov={label_cov:.1f}%",
            f"value_cov={value_cov:.1f}% avg_dets={avg_dets:.1f}",
        )

    # write report
    report_path = out_dir / "ocr_eval_results.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf8")
    print(f"Wrote report to {report_path}")
    # also produce simple CSV
    csv_path = out_dir / "ocr_eval_results.csv"
    with open(csv_path, "w", encoding="utf8") as f:
        f.write(
            (
                "model,images,total_components,label_hits,value_hits,"
                "label_coverage_pct,value_coverage_pct,avg_detections_per_image\n"
            )
        )
        for m, r in results.items():
            f.write(
                (
                    f"{m},{r['images']},{r['total_components']},{r['label_hits']},"
                    f"{r['value_hits']},{r['label_coverage_pct']},{r['value_coverage_pct']},"
                    f"{r['avg_detections_per_image']}\n"
                )
            )
    print(f"Wrote CSV to {csv_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--models", type=str, default="tesseract,easyocr,paddleocr,doctr,surya")
    p.add_argument("--input-dir", type=Path, default=Path("ocr_eval/ci-samples"))
    p.add_argument("--out-dir", type=Path, default=Path("reports"))
    p.add_argument("--max-images", type=int, default=None)
    args = p.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    evaluate(models, args.input_dir, args.out_dir, max_images=args.max_images)
