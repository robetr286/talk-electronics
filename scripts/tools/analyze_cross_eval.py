#!/usr/bin/env python3
"""Analyze cross-eval outputs: per-class AP tables, plots and failure examples."""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path("runs/benchmarks")


def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    pc_y = load_json(ROOT / "per_class_yolo.json")
    pc_m = load_json(ROOT / "per_class_mask.json")
    coco = load_json(Path("data/yolo_dataset/mix_small/coco_annotations.json"))
    id2name = {c["id"]: c.get("name", str(c.get("id"))) for c in coco.get("categories", [])}

    # collect mean AP values per class
    per_y = pc_y.get("per_class", {})
    per_m = pc_m.get("per_class", {})
    rows = []
    for cls in sorted(set(list(per_y.keys()) + list(per_m.keys()))):
        my = per_y.get(str(cls), {}) if isinstance(per_y, dict) and str(cls) in per_y else per_y.get(int(cls), {})
        mm = per_m.get(str(cls), {}) if isinstance(per_m, dict) and str(cls) in per_m else per_m.get(int(cls), {})
        valy = my.get("mean_ap_50_95", 0.0) if isinstance(my, dict) else my.get("mean_ap_50_95", 0.0)
        valm = mm.get("mean_ap_50_95", 0.0) if isinstance(mm, dict) else mm.get("mean_ap_50_95", 0.0)
        rows.append((int(cls), id2name.get(int(cls), str(cls)), float(valy), float(valm)))

    # sort by YOLO mean AP ascending (hardest classes)
    rows.sort(key=lambda x: x[2])

    out_csv = ROOT / "per_class_comparison.csv"
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("class_id,class_name,yolo_meanAP50_95,mask_meanAP50_95\n")
        for r in rows:
            f.write(f"{r[0]},{r[1]},{r[2]:.4f},{r[3]:.4f}\n")

    # plot top-k worst classes
    worst = rows[:10]
    labels = [r[1] for r in worst]
    yvals = [r[2] for r in worst]
    mvals = [r[3] for r in worst]
    plt.figure(figsize=(10, 5))
    x = np.arange(len(labels))
    plt.bar(x - 0.2, yvals, width=0.4, label="YOLO")
    plt.bar(x + 0.2, mvals, width=0.4, label="Mask R-CNN")
    plt.xticks(x, labels, rotation=45, ha="right")
    plt.ylabel("mean AP 50:95")
    plt.title("Worst 10 classes by YOLO mean AP 50:95")
    plt.legend()
    figp = ROOT / "fig_worst10_meanAP50_95.png"
    plt.tight_layout()
    plt.savefig(figp, dpi=150)
    print("Wrote", out_csv, "and", figp)


if __name__ == "__main__":
    main()
