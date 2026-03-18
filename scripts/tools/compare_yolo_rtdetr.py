#!/usr/bin/env python3
"""A.4.2 — Porównanie metryk YOLO vs RT-DETR na zbiorze walidacyjnym.

Uruchamia walidację obu detektorów na tym samym datasecie i generuje
raport porównawczy w reports/detector_comparison_yolo_vs_rtdetr.md.

Użycie:
    python scripts/tools/compare_yolo_rtdetr.py
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np


def validate_model(model_cls, weights: str, data: str, label: str) -> dict:
    """Run Ultralytics val() and return key metrics."""
    model = model_cls(weights)
    print(f"\n{'='*60}")
    print(f"  Walidacja: {label}")
    print(f"  Wagi: {weights}")
    print(f"{'='*60}\n")

    start = time.perf_counter()
    results = model.val(data=data, imgsz=640, batch=4, verbose=True)
    elapsed = time.perf_counter() - start

    # Extract metrics
    box = results.box
    metrics = {
        "label": label,
        "weights": weights,
        "mAP50": float(box.map50),
        "mAP50_95": float(box.map),
        "precision": float(box.mp),
        "recall": float(box.mr),
        "per_class": {},
        "wall_time_s": round(elapsed, 1),
    }

    # Per-class metrics
    names = results.names
    ap50 = box.ap50
    ap = box.ap
    p_arr = box.p
    r_arr = box.r

    for i, cls_name in names.items():
        if i < len(ap50):
            metrics["per_class"][cls_name] = {
                "mAP50": float(ap50[i]),
                "mAP50_95": float(ap[i]),
                "P": float(p_arr[i]) if i < len(p_arr) else 0.0,
                "R": float(r_arr[i]) if i < len(r_arr) else 0.0,
            }

    # Speed from results
    speed = getattr(results, "speed", {})
    if speed:
        metrics["inference_ms"] = round(speed.get("inference", 0.0), 1)
        metrics["preprocess_ms"] = round(speed.get("preprocess", 0.0), 1)
        metrics["postprocess_ms"] = round(speed.get("postprocess", 0.0), 1)

    return metrics


def generate_report(yolo_m: dict, rtdetr_m: dict, output: Path) -> None:
    """Write comparison report as Markdown."""
    output.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Porównanie detektorów: YOLOv8 vs RT-DETR-L",
        "",
        f"Data: {time.strftime('%Y-%m-%d %H:%M')}",
        f"Dataset: `configs/rtdetr_symbols.yaml` (val split, 30 obrazów, 539 anotacji)",
        "",
        "## Metryki ogólne",
        "",
        "| Metryka | YOLOv8 | RT-DETR-L | Δ |",
        "|---|---|---|---|",
    ]

    for key, label in [
        ("mAP50", "mAP@0.5"),
        ("mAP50_95", "mAP@0.5:0.95"),
        ("precision", "Precision"),
        ("recall", "Recall"),
    ]:
        y = yolo_m[key]
        r = rtdetr_m[key]
        delta = r - y
        sign = "+" if delta >= 0 else ""
        lines.append(f"| {label} | {y:.3f} | {r:.3f} | {sign}{delta:.3f} |")

    # Inference speed
    y_inf = yolo_m.get("inference_ms", "?")
    r_inf = rtdetr_m.get("inference_ms", "?")
    lines.append(f"| Inference (ms/img) | {y_inf} | {r_inf} | — |")

    lines.extend([
        "",
        "## Metryki per klasa",
        "",
        "### YOLOv8",
        "",
        "| Klasa | P | R | mAP@0.5 | mAP@0.5:0.95 |",
        "|---|---|---|---|---|",
    ])
    for cls, m in yolo_m["per_class"].items():
        lines.append(f"| {cls} | {m['P']:.3f} | {m['R']:.3f} | {m['mAP50']:.3f} | {m['mAP50_95']:.3f} |")

    lines.extend([
        "",
        "### RT-DETR-L",
        "",
        "| Klasa | P | R | mAP@0.5 | mAP@0.5:0.95 |",
        "|---|---|---|---|---|",
    ])
    for cls, m in rtdetr_m["per_class"].items():
        lines.append(f"| {cls} | {m['P']:.3f} | {m['R']:.3f} | {m['mAP50']:.3f} | {m['mAP50_95']:.3f} |")

    # Conclusion
    winner_map50 = "RT-DETR-L" if rtdetr_m["mAP50"] >= yolo_m["mAP50"] else "YOLOv8"
    winner_speed = "YOLOv8" if (yolo_m.get("inference_ms", 999) < rtdetr_m.get("inference_ms", 999)) else "RT-DETR-L"

    lines.extend([
        "",
        "## Wnioski",
        "",
        f"- **Dokładność (mAP@0.5):** Lepszy → **{winner_map50}**",
        f"- **Szybkość inferencji:** Szybszy → **{winner_speed}**",
        f"- YOLOv8 wagi: `{yolo_m['weights']}` ({Path(yolo_m['weights']).stat().st_size / 1e6:.1f} MB)",
        f"- RT-DETR-L wagi: `{rtdetr_m['weights']}` ({Path(rtdetr_m['weights']).stat().st_size / 1e6:.1f} MB)",
        "",
        "---",
        f"*Raport wygenerowany automatycznie przez `scripts/tools/compare_yolo_rtdetr.py`*",
    ])

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nRaport zapisany: {output}")


def main() -> None:
    from ultralytics import RTDETR, YOLO

    data = "configs/rtdetr_symbols.yaml"
    yolo_weights = "weights/train6_best.pt"
    rtdetr_weights = "weights/rtdetr_best.pt"
    output = Path("reports/detector_comparison_yolo_vs_rtdetr.md")

    yolo_metrics = validate_model(YOLO, yolo_weights, data, "YOLOv8")
    rtdetr_metrics = validate_model(RTDETR, rtdetr_weights, data, "RT-DETR-L")

    generate_report(yolo_metrics, rtdetr_metrics, output)

    print("\n" + "=" * 60)
    print("  PODSUMOWANIE")
    print("=" * 60)
    print(f"  YOLOv8    mAP@0.5={yolo_metrics['mAP50']:.3f}  mAP@0.5:0.95={yolo_metrics['mAP50_95']:.3f}  {yolo_metrics.get('inference_ms', '?')} ms/img")
    print(f"  RT-DETR-L mAP@0.5={rtdetr_metrics['mAP50']:.3f}  mAP@0.5:0.95={rtdetr_metrics['mAP50_95']:.3f}  {rtdetr_metrics.get('inference_ms', '?')} ms/img")
    print("=" * 60)


if __name__ == "__main__":
    main()
