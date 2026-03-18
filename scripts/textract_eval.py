import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoRegionError
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

import talk_electronic.routes.textract as tx


def bbox_to_px(bbox: dict, w: int, h: int) -> Tuple[int, int, int, int]:
    left = bbox.get("Left", 0) * w
    top = bbox.get("Top", 0) * h
    width = bbox.get("Width", 0) * w
    height = bbox.get("Height", 0) * h
    return int(left), int(top), int(left + width), int(top + height)


def textract_client(region: str | None):
    load_dotenv()  # załaduj zmienne z .env (AWS_* jeśli tam są)
    session = boto3.session.Session(region_name=region)
    return session.client("textract")


def analyze_image(client, img_path: Path, feature_types: List[str]) -> dict:
    payload = img_path.read_bytes()
    return client.analyze_document(Document={"Bytes": payload}, FeatureTypes=feature_types)


def draw_overlay(img_path: Path, blocks: Iterable[dict], out_path: Path) -> None:
    im = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(im)
    font = ImageFont.load_default()
    w, h = im.size

    for block in blocks:
        if block.get("BlockType") not in {"WORD", "LINE"}:
            continue
        bbox = block.get("Geometry", {}).get("BoundingBox")
        if not bbox:
            continue
        x0, y0, x1, y1 = bbox_to_px(bbox, w, h)
        draw.rectangle([x0, y0, x1, y1], outline=(0, 255, 0), width=2)
        text = block.get("Text")
        if text:
            draw.text((x0, max(0, y0 - 10)), text, fill=(0, 255, 0), font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_path)


def draw_post_overlay(img_path: Path, tokens: List[Dict], pairs: List[Dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tx._draw_overlay(img_path, tokens, pairs, out_path)


def save_json(data: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_lines_tsv(blocks: Iterable[dict], out_path: Path) -> None:
    lines = []
    for b in blocks:
        if b.get("BlockType") == "LINE" and b.get("Text"):
            lines.append(b["Text"].replace("\t", " "))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def iter_images(img_dir: Path) -> List[Path]:
    return sorted([p for p in img_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"}])


def load_gt_counts(path: Path) -> Dict[str, Dict[str, int]]:
    if not path.exists():
        return {}
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        if line.strip().startswith("|-"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cols)
    if not rows:
        return {}
    header, *data = rows
    result: Dict[str, Dict[str, int]] = {}
    for row in data:
        if len(row) != len(header):
            continue
        rec = {header[i]: row[i] for i in range(len(header))}
        fname = rec.get("file")
        if not fname:
            continue
        parsed = {}
        for k, v in rec.items():
            if k == "file":
                continue
            try:
                parsed[k] = int(v)
            except ValueError:
                continue
        result[fname] = parsed
    return result


def combine_overlays(model_overlay: Path, gt_overlay: Path, out_path: Path) -> None:
    if not (model_overlay.exists() and gt_overlay.exists()):
        return
    im_left = Image.open(model_overlay).convert("RGB")
    im_right = Image.open(gt_overlay).convert("RGB")
    h = max(im_left.height, im_right.height)
    w_left, w_right = im_left.width, im_right.width
    canvas = Image.new("RGB", (w_left + w_right + 10, h), (255, 255, 255))
    canvas.paste(im_left, (0, 0))
    canvas.paste(im_right, (w_left + 10, 0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


def main():
    ap = argparse.ArgumentParser(description="Batch Textract eval on schematic images")
    ap.add_argument("--images", type=Path, default=Path("textract_test/images"))
    ap.add_argument("--out", type=Path, default=Path("reports/textract"))
    ap.add_argument("--max-files", type=int, default=0, help="Limit number of files (0 = all)")
    ap.add_argument("--only", type=str, default="", help="Comma list of filename stems to process (filters list)")
    ap.add_argument("--region", type=str, default=None, help="AWS region override")
    ap.add_argument("--feature-types", type=str, default="FORMS,TABLES", help="Comma list of Textract features")
    ap.add_argument("--dry-run", action="store_true", help="List files without calling Textract")
    ap.add_argument("--min-conf", type=float, default=40.0, help="Minimalna pewność tokenu")
    ap.add_argument("--gt-counts", type=Path, default=Path("reports/textract/counts_template.csv"))
    ap.add_argument("--gt-overlays", type=Path, default=Path("textract_test/overlays_gt"))
    args = ap.parse_args()

    files = iter_images(args.images)
    if args.only:
        allow = {s.strip() for s in args.only.split(",") if s.strip()}
        files = [f for f in files if f.stem in allow or any(a in f.stem for a in allow)]
    if args.max_files:
        files = files[: args.max_files]

    if args.dry_run:
        for f in files:
            print(f)
        return

    metrics_rows = []

    feature_types = [f.strip() for f in args.feature_types.split(",") if f.strip()]
    try:
        client = textract_client(args.region)
    except NoRegionError:
        print("Brak regionu AWS. Ustaw AWS_DEFAULT_REGION lub użyj --region.")
        return

    for idx, img_path in enumerate(files, 1):
        stem = img_path.stem
        print(f"[{idx}/{len(files)}] {img_path.name}")
        try:
            result = analyze_image(client, img_path, feature_types)
        except (ClientError, BotoCoreError) as e:
            print(f"  Textract error: {e}")
            continue

        blocks = result.get("Blocks", [])
        save_json(result, args.out / "json" / f"{stem}.json")
        save_lines_tsv(blocks, args.out / "tsv" / f"{stem}.txt")
        overlay_blocks = args.out / "overlays_model" / f"{stem}_overlay.png"
        draw_overlay(img_path, blocks, overlay_blocks)

        try:
            im = Image.open(img_path)
            w, h = im.size
        except Exception:
            w = h = 0

        tokens = tx._filter_tokens(blocks, w, h, min_conf=args.min_conf) if (w and h) else []
        tokens = tx._merge_vertical_fragments(tokens)  # P4: merge vertical chars
        tokens = tx._extend_truncated_designators(tokens)  # P25c: C41 → C411
        tokens = tx._fix_semicon_fragments(tokens)  # P25b: 2S+C1740 → 2SC1740
        tokens = tx._fix_ic_ocr_confusion(tokens)  # P25e: IC40B → IC408

        # P4+: Rescue vertical text from uncovered strips
        if tokens and w and h:
            try:
                rescued = tx._rescue_vertical_text(img_path, tokens, client, w, h)
                if rescued:
                    tokens.extend(rescued)
                    print(f"  vertical_rescue: +{len(rescued)} tokenów")
            except Exception as exc:
                print(f"  vertical_rescue failed: {exc}")

        # P9e: General substring deduplication
        tokens = tx._dedup_substring_tokens(tokens)

        pairs = tx._pair_components_to_values(tokens) if tokens else []
        tokens, pairs = tx._fix_truncated_ic(tokens, pairs)  # P3: C408 → IC408

        post_payload = {
            "file": img_path.name,
            "tokens": tokens,
            "pairs": pairs,
        }
        save_json(post_payload, args.out / "post" / f"{stem}_post.json")

        overlay_post = args.out / "overlays_post" / f"{stem}_post.png"
        if tokens:
            draw_post_overlay(img_path, tokens, pairs, overlay_post)

        gt_overlay = args.gt_overlays / f"{img_path.name}"
        compare_out = args.out / "overlays_compare" / f"{stem}_model_vs_gt.png"
        if overlay_post.exists() and gt_overlay.exists():
            combine_overlays(overlay_post, gt_overlay, compare_out)

        metrics_row = {
            "file": img_path.name,
            "tokens": len(tokens),
            "components": sum(1 for t in tokens if t.get("category") == "component"),
            "values": sum(1 for t in tokens if t.get("category") == "value"),
            "net_labels": sum(1 for t in tokens if t.get("category") == "net_label"),
            "pairs": len(pairs),
        }
        metrics_rows.append(metrics_row)

    gt_counts = load_gt_counts(args.gt_counts)
    with (args.out / "eval_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "file",
            "tokens",
            "components",
            "values",
            "net_labels",
            "pairs",
            "gt_symbole_total",
            "gt_net_label",
            "tp_symbole_approx",
            "fp_symbole_approx",
            "fn_symbole_approx",
            "tp_net_label",
            "fp_net_label",
            "fn_net_label",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in metrics_rows:
            gt = gt_counts.get(row["file"], {})
            gt_sym = gt.get("symbole_total")
            gt_net = gt.get("net_label")
            pred_comp = row["components"]
            pred_net = row["net_labels"]
            tp_sym = min(pred_comp, gt_sym) if gt_sym is not None else None
            fp_sym = max(pred_comp - gt_sym, 0) if gt_sym is not None else None
            fn_sym = max(gt_sym - pred_comp, 0) if gt_sym is not None else None
            tp_net = min(pred_net, gt_net) if gt_net is not None else None
            fp_net = max(pred_net - gt_net, 0) if gt_net is not None else None
            fn_net = max(gt_net - pred_net, 0) if gt_net is not None else None
            writer.writerow(
                {
                    **row,
                    "gt_symbole_total": gt_sym,
                    "gt_net_label": gt_net,
                    "tp_symbole_approx": tp_sym,
                    "fp_symbole_approx": fp_sym,
                    "fn_symbole_approx": fn_sym,
                    "tp_net_label": tp_net,
                    "fp_net_label": fp_net,
                    "fn_net_label": fn_net,
                }
            )

    print("Done.")


if __name__ == "__main__":
    main()
