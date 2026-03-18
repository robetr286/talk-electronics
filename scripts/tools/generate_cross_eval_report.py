#!/usr/bin/env python3
"""Generate a Markdown report summarizing cross-eval results and recommendations."""
import csv
import json
from pathlib import Path

ROOT = Path("runs/benchmarks")


def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def load_per_class_csv(p):
    rows = []
    with open(p, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(
                {
                    "class_id": int(row["class_id"]),
                    "class_name": row["class_name"],
                    "yolo": float(row["yolo_meanAP50_95"]),
                    "mask": float(row["mask_meanAP50_95"]),
                }
            )
    return rows


def recommend_for_class(yolo, mask):
    # simple heuristics
    if yolo <= 0.01 and mask <= 0.01:
        return (
            "Brak wykryć w obu modelach — sprawdź jakość i liczbę anotacji, "
            "rozważ zebranie więcej danych lub scalenie klasy."
        )
    if yolo <= 0.05 and mask >= 0.3:
        return (
            "Mask R-CNN radzi sobie lepiej — rozważyć użycie Mask R-CNN dla tej klasy "
            "lub wzmocnić trening YOLO (dodatkowe przykłady, augmentacje, class weight)."
        )
    if mask <= 0.05 and yolo >= 0.3:
        return (
            "YOLO ma przewagę — jeśli wystarczają pola bbox, możesz preferować YOLO; "
            "dla masek: poprawić anotacje masek lub trenować Mask R-CNN dłużej."
        )
    if yolo < 0.2 and mask < 0.2:
        return (
            "Oba modele słabe — zebrać więcej przykładów, zastosować augmentacje, "
            "rozważyć oversampling rzadkich klas i poprawę anotacji."
        )
    return "Wyniki umiarkowane — drobne usprawnienia: tuning progów, więcej epok, augmentacje."


def main():
    summary = load_json(ROOT / "cross_eval_summary.json")
    per_class = load_per_class_csv(ROOT / "per_class_comparison.csv")

    report = []
    report.append("# Cross-eval Report")
    report.append("")
    report.append("**Summary**")
    report.append("")
    report.append(f"- YOLO bbox mAP@0.5: {summary['yolo'].get('map50_box', 0.0):.4f}")
    report.append(f"- Mask R-CNN bbox mAP@0.5: {summary['maskrcnn'].get('map50_box', 0.0):.4f}")
    report.append(f"- YOLO mean mAP@0.5:0.95: {summary['yolo'].get('mean_map_50_95', 0.0):.4f}")
    report.append(f"- Mask R-CNN mean mAP@0.5:0.95: {summary['maskrcnn'].get('mean_map_50_95', 0.0):.4f}")
    report.append(f"- YOLO mean mask IoU: {summary['yolo'].get('mean_mask_iou', 0.0):.4f}")
    report.append(f"- Mask R-CNN mean mask IoU: {summary['maskrcnn'].get('mean_mask_iou', 0.0):.4f}")
    report.append("")

    report.append("**Plots & examples**")
    report.append("")
    if (ROOT / "fig_worst10_meanAP50_95.png").exists():
        report.append(f"![Worst 10 classes]({ROOT / 'fig_worst10_meanAP50_95.png'})")
    report.append("")
    report.append(
        "Overlays and failure examples are saved in `runs/benchmarks/overlays` "
        "and `runs/benchmarks/failure_examples`. Below are a few examples per class."
    )
    report.append("")

    # small per-class table (worst 12 by YOLO)
    report.append("## Per-class comparison (worst by YOLO mean AP 50:95)")
    report.append("")
    report.append("|class_id|class_name|yolo_meanAP50_95|mask_meanAP50_95|delta|recommendation|")
    report.append("|--:|--|--:|--:|--:|--|")
    per_class_sorted = sorted(per_class, key=lambda x: x["yolo"])[:20]
    for r in per_class_sorted:
        delta = r["mask"] - r["yolo"]
        rec = recommend_for_class(r["yolo"], r["mask"])
        report.append(f"|{r['class_id']}|{r['class_name']}|{r['yolo']:.4f}|{r['mask']:.4f}|{delta:.4f}|{rec}|")

    report.append("")
    report.append("## Example failure images")
    report.append("")
    # attach up to two images per worst class if available
    for r in per_class_sorted[:6]:
        cid = r["class_id"]
        report.append(f"### Class {cid}: {r['class_name']}")
        img_dir = ROOT / "failure_examples"
        imgs = sorted([p for p in img_dir.glob(f"cls{cid}_*.jpg")])
        for p in imgs[:2]:
            report.append(f"![{p.name}]({p})")
        report.append("")

    report.append("## Recommendations (general)")
    report.append("")
    report.append(
        "- Sprawdź klasy o zerowej AP w obu modelach: możliwe błędy anotacji lub brak danych. "
        "Rozważ doprecyzowanie schematu anotacji i zebranie więcej próbek."
    )
    report.append(
        "- Dla klas, gdzie Mask R-CNN jest znacznie lepszy: rozważyć Mask R-CNN w produkcji lub "
        "wzbogacić trening YOLO (więcej masek, augmentacje, większe imgsz)."
    )
    report.append(
        "- Dla klas, gdzie YOLO wypada lepiej i maski nie są krytyczne: "
        "używać YOLO jako szybszego modelu produkcyjnego."
    )
    report.append(
        "- Ogólne techniki: tuning thresholds (score, NMS IoU), class-balanced sampling, "
        "augmentacje (scale, rotate, cutmix), i ewentualne dodatkowe etapy walidacji."
    )

    out = ROOT / "cross_eval_report.md"
    out.write_text("\n".join(report), encoding="utf-8")
    print("Wygenerowano raport:", out)


if __name__ == "__main__":
    main()
