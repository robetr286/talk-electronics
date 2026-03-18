import json
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent.parent / "textract_test"
IMG_DIR = BASE / "images"
OUT_DIR = BASE / "overlays_gt"
COCO_PATH = BASE / "coco_ls_14_01_2026.json"
LS_EXPORT_PATH = OUT_DIR / "project-2-at-2026-02-06-19-03-390c7b7a.json"
SKIP_LABELS = {"ignore_region"}
LINE_WIDTH = 4  # pogrubione ramki dla lepszej widoczności

# Kolory przypisane do kategorii GT (dopasowane do liczenia w counts_template.csv).
# Uwaga: dla "ic" używamy fioletu, aby ramka była widoczna na białym tle.
CATEGORY_COLORS: Dict[str, tuple] = {
    "net_label": (0, 0, 255),  # niebieski
    "resistor": (255, 140, 0),  # pomarańczowy
    "capacitor": (0, 128, 128),  # teal
    "diode": (220, 20, 60),  # crimson
    "inductor": (0, 128, 0),  # zielony
    "op_amp": (72, 61, 139),  # ciemny fiolet/granat
    "transistor": (139, 0, 0),  # ciemna czerwień
    "ic": (138, 43, 226),  # fiolet (widoczny na białym)
    "ic_pin": (186, 85, 211),  # jasny fiolet
    "connector": (0, 191, 255),  # jasny niebieski
    "ground": (85, 107, 47),  # oliwkowy (unikalny, odróżnialny od transistor)
    "edge_connector": (255, 215, 0),  # złoty
    "broken_line": (255, 0, 255),  # magenta
    "measurement_point": (255, 105, 180),  # róż
    "misc_symbol": (128, 128, 128),  # szary
}
COLOR_DEFAULT = (255, 0, 0)


def load_coco(path: Path) -> Dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_ls_export(path: Path) -> Dict[str, List[Dict]]:
    """Parsuje export Label Studio (pełny JSON z listą tasków).

    Zwraca mapę: nazwa_pliku -> lista adnotacji {bbox: [x, y, w, h], label: str} w pikselach.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    by_file: Dict[str, List[Dict]] = {}

    for task in data:
        fname = Path(task.get("file_upload") or Path(task.get("data", {}).get("image", "")).name).name
        if not fname:
            continue

        annotations = task.get("annotations", [])
        for ann in annotations:
            for res in ann.get("result", []):
                rtype = res.get("type")
                val = res.get("value", {})
                ow = res.get("original_width") or task.get("data", {}).get("width")
                oh = res.get("original_height") or task.get("data", {}).get("height")
                if not ow or not oh:
                    continue

                if rtype == "rectanglelabels":
                    label = (val.get("rectanglelabels") or [""])[0]
                    x = val.get("x")
                    y = val.get("y")
                    w = val.get("width")
                    h = val.get("height")
                    if None in (x, y, w, h):
                        continue
                    bbox = [x / 100.0 * ow, y / 100.0 * oh, w / 100.0 * ow, h / 100.0 * oh]
                    points = None
                    kind = "rect"
                elif rtype == "polygonlabels":
                    pts = val.get("points") or []
                    label = (val.get("polygonlabels") or [""])[0]
                    if not pts:
                        continue
                    xs = [p[0] / 100.0 * ow for p in pts]
                    ys = [p[1] / 100.0 * oh for p in pts]
                    bbox = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
                    points = list(zip(xs, ys))
                    kind = "polygon"
                else:
                    continue

                if label.lower() in SKIP_LABELS:
                    continue

                by_file.setdefault(fname, []).append({"bbox": bbox, "label": label, "points": points, "kind": kind})

    return by_file


def group_annotations(annotations: List[Dict]) -> Dict[int, List[Dict]]:
    grouped: Dict[int, List[Dict]] = {}
    for ann in annotations:
        grouped.setdefault(ann["image_id"], []).append(ann)
    return grouped


def draw_overlays(data: Dict) -> List[Dict]:
    images = {img["id"]: img for img in data.get("images", [])}
    categories = {c["id"]: c.get("name", str(c["id"])) for c in data.get("categories", [])}
    anns_by_img = group_annotations(data.get("annotations", []))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    color = (255, 0, 0)  # fallback dla COCO (nieużywany przy LS, zostaje dla zgodności)
    summary: List[Dict] = []
    missing: List[str] = []

    for img_id, meta in images.items():
        fname = meta["file_name"]
        path = IMG_DIR / fname
        if not path.exists():
            missing.append(fname)
            continue

        im = Image.open(path).convert("RGB")
        draw = ImageDraw.Draw(im)
        anns = anns_by_img.get(img_id, [])

        for ann in anns:
            x, y, w, h = ann["bbox"]
            label = categories.get(ann["category_id"], str(ann["category_id"]))
            draw.rectangle([x, y, x + w, y + h], outline=color, width=LINE_WIDTH)
            draw.text((x, max(0, y - 10)), label, fill=color, font=font)

        out_path = OUT_DIR / fname
        im.save(out_path)
        summary.append({"file": fname, "annotations": len(anns)})

    summary_path = OUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if missing:
        print("Missing images:", ", ".join(missing))
    print(f"Generated {len(summary)} overlays. Summary -> {summary_path}")
    return summary


def draw_overlays_ls(by_file: Dict[str, List[Dict]]) -> List[Dict]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    color = COLOR_DEFAULT
    summary: List[Dict] = []
    missing: List[str] = []

    for fname, anns in by_file.items():
        path = IMG_DIR / fname
        if not path.exists():
            missing.append(fname)
            continue

        im = Image.open(path).convert("RGB")
        draw = ImageDraw.Draw(im)

        for ann in anns:
            x, y, w, h = ann["bbox"]
            label = ann.get("label", "")
            label_lower = label.lower()
            this_color = CATEGORY_COLORS.get(label_lower, color)
            if ann.get("kind") == "polygon" and ann.get("points"):
                pts = ann["points"]
                draw.polygon(pts, outline=this_color, width=LINE_WIDTH)
                text_x = min(p[0] for p in pts)
                text_y = max(0, min(p[1] for p in pts) - 10)
            else:
                draw.rectangle([x, y, x + w, y + h], outline=this_color, width=LINE_WIDTH)
                text_x, text_y = x, max(0, y - 10)

            if label:
                draw.text((text_x, text_y), label, fill=this_color, font=font)

        out_path = OUT_DIR / fname
        im.save(out_path)
        summary.append({"file": fname, "annotations": len(anns)})

    summary_path = OUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if missing:
        print("Missing images:", ", ".join(missing))
    print(f"Generated {len(summary)} overlays from Label Studio export. Summary -> {summary_path}")
    return summary


def main():
    if LS_EXPORT_PATH.exists():
        by_file = load_ls_export(LS_EXPORT_PATH)
        draw_overlays_ls(by_file)
    elif COCO_PATH.exists():
        data = load_coco(COCO_PATH)
        draw_overlays(data)
    else:
        raise FileNotFoundError("Brak pliku LS export lub COCO do narysowania overlayów")


if __name__ == "__main__":
    main()
