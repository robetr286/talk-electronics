#!/usr/bin/env python3
"""Prepare OCR evaluation dataset from Label Studio exports.

Usage examples:

# From a directory with single-task exports
# python scripts/prepare_ocr_eval.py --single-exports-dir path/to/exports \
#     --images-dir path/to/images --out-dir ocr_eval --ci-count 20

# From a full Label Studio export file
# python scripts/prepare_ocr_eval.py --labelstudio-export tasks.json \
#     --out-dir ocr_eval --ci-count 20

The script produces:
ocr_eval/ci/{id}.png + {id}.json  (first N examples)
ocr_eval/local/{id}.png + {id}.json (rest)

The per-image JSON is a conservative, standardized format that contains a "components" list (label, value, bbox, raw).
"""

import argparse
import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import requests
except Exception:
    requests = None

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def parse_labelstudio_task(task: Dict) -> Tuple[Optional[str], List[Dict]]:
    """Extract image reference and components from a Label Studio task dict.

    Returns (image_ref, components_list)
    components entries: {id, label, value, bbox, raw}
    """
    image_ref = None
    # Try to find image url/path in task['data']
    data = task.get("data") or {}
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str) and v.lower().endswith((".png", ".jpg", ".jpeg")):
                image_ref = v
                break
            if isinstance(v, str) and v.startswith("http") and (".png" in v or ".jpg" in v or ".jpeg" in v):
                image_ref = v
                break

    # Find annotation results (robust across Label Studio export shapes)
    result_list = []
    annotations = task.get("annotations") or task.get("completions") or task.get("predictions") or []
    if isinstance(annotations, list) and annotations:
        # take first non-empty result list we find
        for ann in annotations:
            if isinstance(ann, dict):
                r = ann.get("result") or ann.get("response") or []
                if r:
                    result_list = r
                    break

    # fallback: maybe task itself has 'result'
    if not result_list and isinstance(task.get("result"), list):
        result_list = task.get("result", [])

    components = []
    for idx, res in enumerate(result_list, start=1):
        value = res.get("value", {})
        label_text = None
        value_text = None
        bbox = None

        # rectangle labels (bbox)
        if isinstance(value, dict) and (
            "rectanglelabels" in value or {"x", "y", "width", "height"}.issubset(set(value.keys()))
        ):
            if "rectanglelabels" in value and value.get("rectanglelabels"):
                label_text = value.get("rectanglelabels")[0]
            bbox = (
                [value.get(k) for k in ("x", "y", "width", "height")]
                if {"x", "y", "width", "height"}.issubset(set(value.keys()))
                else None
            )

        # labels/choices
        if not label_text and isinstance(value, dict) and ("labels" in value or "choices" in value):
            if value.get("labels"):
                label_text = value.get("labels")[0]
            elif value.get("choices"):
                # choices may be used for classification
                label_text = value.get("choices")[0]

        # text annotations
        if not value_text and isinstance(value, dict) and "text" in value:
            value_text = value.get("text")

        # sometimes label is in 'from_name' or 'annotation' fields
        if not label_text:
            label_text = res.get("from_name") or res.get("annotationType") or res.get("type")

        # parse meta.text if present (Label Studio often stores key=value tokens in meta.text)
        meta = res.get("meta") or {}
        meta_text = None
        if isinstance(meta, dict):
            mt = meta.get("text")
            if isinstance(mt, list):
                meta_text = " ".join(mt)
            elif isinstance(mt, str):
                meta_text = mt
        if meta_text:
            # tokenize and parse k=v pairs
            attrs = {}
            for tok in meta_text.split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    attrs[k.strip()] = v.strip()
            # prefer designator as label and value as component value
            if attrs.get("designator"):
                label_text = attrs.get("designator")
            if attrs.get("value") and not value_text:
                value_text = attrs.get("value")

        comp = {
            "id": f"c{idx}",
            "label": label_text,
            "value": value_text,
            "bbox": bbox,
            "raw": value,
        }
        components.append(comp)

    return image_ref, components


def download_image(url: str, dest_path: Path) -> bool:
    if requests is None:
        logging.warning("requests not available; cannot download images from URL %s", url)
        return False
    try:
        r = requests.get(url, stream=True, timeout=20)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(1024 * 64):
                f.write(chunk)
        return True
    except Exception as e:
        logging.warning("Failed to download %s: %s", url, e)
        return False


def process_single_json_file(json_path: Path) -> Optional[Dict]:
    try:
        obj = json.loads(json_path.read_text(encoding="utf8"))
    except Exception as e:
        logging.error("Failed to load JSON %s: %s", json_path, e)
        return None

    # Label Studio single-task export may be bare task or a wrapper {"data":..., "annotations":...}
    task = obj
    # if it's a list, take first
    if isinstance(obj, list) and obj:
        task = obj[0]

    image_ref, components = parse_labelstudio_task(task)
    base = json_path.stem
    out = {
        "id": base,
        "source": "label-studio",
        "original": str(json_path.name),
        "image": image_ref,
        "components": components,
    }
    return out


def load_full_export(export_path: Path) -> List[Dict]:
    try:
        obj = json.loads(export_path.read_text(encoding="utf8"))
    except Exception as e:
        logging.error("Failed to load export file %s: %s", export_path, e)
        return []
    tasks = obj if isinstance(obj, list) else obj.get("tasks") or []
    out = []
    for task in tasks:
        image_ref, components = parse_labelstudio_task(task)
        tid = task.get("id") or task.get("task_id") or task.get("data", {}).get("image", None) or str(len(out) + 1)
        out.append(
            {
                "id": str(tid),
                "source": "label-studio",
                "original": None,
                "image": image_ref,
                "components": components,
            }
        )
    return out


def write_example(out_dir: Path, item: Dict, images_dir: Optional[Path] = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = item["id"]
    json_path = out_dir / f"{base}.json"
    # write json in a simple standard format
    std = {
        "id": item["id"],
        "source": item.get("source"),
        "original": item.get("original"),
        "components": item.get("components", []),
    }
    json_path.write_text(json.dumps(std, ensure_ascii=False, indent=2), encoding="utf8")

    image_ref = item.get("image")
    if not image_ref:
        logging.info("No image reference for %s; write json only", base)
        return

    # If image is a URL, attempt download
    if isinstance(image_ref, str) and image_ref.startswith("http"):
        img_dest = out_dir / f"{base}{Path(image_ref).suffix}"
        ok = download_image(image_ref, img_dest)
        if ok:
            logging.info("Downloaded image for %s -> %s", base, img_dest)
        else:
            logging.warning("Image download failed for %s (%s)", base, image_ref)
    else:
        # treat as local file - try images_dir first, then additional fallbacks
        candidate = None
        # try images_dir / basename(image_ref)
        if images_dir:
            p = Path(images_dir) / Path(image_ref).name
            if p.exists():
                candidate = p
        # try images_dir / {base}.png/jpg/jpeg
        if images_dir and not candidate:
            for ext in (".png", ".jpg", ".jpeg"):
                p2 = Path(images_dir) / f"{base}{ext}"
                if p2.exists():
                    candidate = p2
                    break
        # try any file in images_dir with stem == base
        if images_dir and not candidate:
            for p3 in Path(images_dir).iterdir():
                if p3.is_file() and p3.stem == base:
                    candidate = p3
                    break
        # fallback to same folder as json or absolute path
        if not candidate:
            maybe = Path(image_ref)
            if maybe.exists():
                candidate = maybe
        if candidate:
            ext = candidate.suffix or ".png"
            dest = out_dir / f"{base}{ext}"
            shutil.copy(candidate, dest)
            logging.info("Copied image for %s -> %s", base, dest)
        else:
            logging.warning(
                "Could not find local image for %s (%s) in %s",
                base,
                image_ref,
                images_dir,
            )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--single-exports-dir", type=Path, help="Directory with single-task JSON exports from Label Studio")
    p.add_argument("--labelstudio-export", type=Path, help="Full Label Studio export JSON (list of tasks)")
    p.add_argument("--images-dir", type=Path, help="Optional directory where referenced images live (local copies)")
    p.add_argument("--out-dir", type=Path, default=Path("ocr_eval"), help="Output directory")
    p.add_argument("--ci-count", type=int, default=20, help="Number of examples to include in `ci` split")
    p.add_argument(
        "--include-urls", action="store_true", help="Attempt to download images referenced by URL (requires requests)"
    )
    args = p.parse_args()

    items = []
    if args.single_exports_dir:
        for jf in sorted(Path(args.single_exports_dir).glob("*.json")):
            item = process_single_json_file(jf)
            if item:
                # remember original file name for traceability
                item["original"] = jf.name
                items.append(item)
    elif args.labelstudio_export:
        items = load_full_export(args.labelstudio_export)
    else:
        p.print_help()
        return

    if not items:
        logging.error("No items found to process")
        return

    out_dir = args.out_dir
    ci_dir = out_dir / "ci"
    local_dir = out_dir / "local"

    # write first N to ci, rest to local
    for i, item in enumerate(items):
        target = ci_dir if i < args.ci_count else local_dir
        write_example(target, item, images_dir=args.images_dir)

    logging.info(
        "Wrote %d items: %d -> %s, %d -> %s",
        len(items),
        min(len(items), args.ci_count),
        ci_dir,
        max(0, len(items) - args.ci_count),
        local_dir,
    )


if __name__ == "__main__":
    main()
