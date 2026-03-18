#!/usr/bin/env python
"""
Analiza jakości anotacji COCO - statystyki, outliers, wizualizacje.

Generuje szczegółowy raport jakości datasetu COCO:
- Statystyki per klasa (count, rozmiar bbox, aspect ratio)
- Wykrywanie outliers (zbyt małe/duże bbox, nietypowe proporcje)
- Heatmap pokrycia obrazów (gdzie są anotacje)
- Wizualizacje rozkładu (matplotlib)
- Export do JSON

Usage:
    # Podstawowa analiza
    python scripts/quality_metrics.py --input data/synthetic/coco_annotations.json --output reports/quality_report.json

    # Z wizualizacjami
    python scripts/quality_metrics.py \
        --input data/synthetic/coco_merged.json \
        --output reports/quality_merged.json \
        --visualize \
        --output-dir reports/visualizations

    # Tylko statystyki (bez outliers)
    python scripts/quality_metrics.py --input data.json --output report.json --no-outliers
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

# Use Agg backend for non-interactive plotting (CI/CD friendly)
matplotlib.use("Agg")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Analyze COCO dataset quality metrics")
    parser.add_argument("--input", type=str, required=True, help="Input COCO JSON file")
    parser.add_argument("--output", type=str, required=True, help="Output report JSON file")
    parser.add_argument("--visualize", action="store_true", help="Generate matplotlib visualizations")
    parser.add_argument("--output-dir", type=str, default="reports/visualizations", help="Directory for visualizations")
    parser.add_argument("--no-outliers", action="store_true", help="Skip outlier detection (faster for large datasets)")
    parser.add_argument("--outlier-threshold", type=float, default=3.0, help="Outlier threshold (std devs)")

    return parser.parse_args()


def load_coco(path: str) -> Dict:
    """Wczytaj plik COCO JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Dict, path: str):
    """Zapisz JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def compute_bbox_metrics(bbox: List[float]) -> Dict[str, float]:
    """
    Oblicz metryki dla bbox.

    Args:
        bbox: [x, y, width, height]

    Returns:
        Dict z metrykami: area, aspect_ratio, diagonal
    """
    x, y, width, height = bbox
    area = width * height
    aspect_ratio = width / height if height > 0 else 0
    diagonal = np.sqrt(width**2 + height**2)

    return {"area": area, "aspect_ratio": aspect_ratio, "diagonal": diagonal, "width": width, "height": height}


def analyze_category_statistics(coco: Dict) -> Dict[int, Dict]:
    """
    Analizuj statystyki per kategoria.

    Returns:
        Dict[category_id] = {
            "name": str,
            "count": int,
            "bbox_areas": [float, ...],
            "aspect_ratios": [float, ...],
            "widths": [float, ...],
            "heights": [float, ...],
        }
    """
    cat_id_to_name = {cat["id"]: cat["name"] for cat in coco["categories"]}

    # Inicjalizuj statystyki
    stats = {}
    for cat_id in cat_id_to_name.keys():
        stats[cat_id] = {
            "name": cat_id_to_name[cat_id],
            "count": 0,
            "bbox_areas": [],
            "aspect_ratios": [],
            "widths": [],
            "heights": [],
        }

    # Zbierz metryki
    for ann in coco["annotations"]:
        cat_id = ann["category_id"]
        if cat_id not in stats:
            continue

        metrics = compute_bbox_metrics(ann["bbox"])
        stats[cat_id]["count"] += 1
        stats[cat_id]["bbox_areas"].append(metrics["area"])
        stats[cat_id]["aspect_ratios"].append(metrics["aspect_ratio"])
        stats[cat_id]["widths"].append(metrics["width"])
        stats[cat_id]["heights"].append(metrics["height"])

    return stats


def compute_summary_statistics(values: List[float]) -> Dict[str, float]:
    """Oblicz statystyki opisowe."""
    if not values:
        return {"mean": 0, "std": 0, "min": 0, "max": 0, "median": 0, "q25": 0, "q75": 0}

    arr = np.array(values)
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "median": float(np.median(arr)),
        "q25": float(np.percentile(arr, 25)),
        "q75": float(np.percentile(arr, 75)),
    }


def detect_outliers(values: List[float], threshold: float = 3.0) -> List[int]:
    """
    Wykryj outliers używając z-score.

    Args:
        values: Lista wartości
        threshold: Próg z-score (domyślnie 3.0 std devs)

    Returns:
        Lista indeksów outliers
    """
    if len(values) < 2:
        return []

    arr = np.array(values)
    mean = np.mean(arr)
    std = np.std(arr)

    if std == 0:
        return []

    z_scores = np.abs((arr - mean) / std)
    outlier_indices = np.where(z_scores > threshold)[0].tolist()

    return outlier_indices


def find_annotation_outliers(coco: Dict, category_stats: Dict, threshold: float = 3.0) -> List[Dict]:
    """
    Znajdź anotacje będące outliers.

    Returns:
        Lista outlier annotations z dodatkowymi informacjami
    """
    outliers = []

    # Zgrupuj anotacje po kategorii
    annotations_by_category = defaultdict(list)
    for ann in coco["annotations"]:
        annotations_by_category[ann["category_id"]].append(ann)

    # Dla każdej kategorii wykryj outliers
    for cat_id, anns in annotations_by_category.items():
        if cat_id not in category_stats:
            continue

        cat_name = category_stats[cat_id]["name"]
        areas = [compute_bbox_metrics(ann["bbox"])["area"] for ann in anns]

        outlier_indices = detect_outliers(areas, threshold)

        for idx in outlier_indices:
            ann = anns[idx]
            metrics = compute_bbox_metrics(ann["bbox"])

            outliers.append(
                {
                    "annotation_id": ann["id"],
                    "image_id": ann["image_id"],
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "bbox": ann["bbox"],
                    "area": metrics["area"],
                    "aspect_ratio": metrics["aspect_ratio"],
                    "reason": "area_outlier",
                    "z_score": float(
                        np.abs((metrics["area"] - np.mean(areas)) / np.std(areas)) if np.std(areas) > 0 else 0
                    ),
                }
            )

    return outliers


def compute_coverage_heatmap(coco: Dict, grid_size: Tuple[int, int] = (10, 10)) -> np.ndarray:
    """
    Oblicz heatmap pokrycia anotacji na obrazach.

    Args:
        coco: COCO dict
        grid_size: Rozmiar siatki (rows, cols)

    Returns:
        2D array z liczbą anotacji w każdej komórce siatki
    """
    # Pobierz wymiary obrazów (zakładamy, że wszystkie mają te same wymiary)
    if not coco["images"]:
        return np.zeros(grid_size)

    img_width = coco["images"][0]["width"]
    img_height = coco["images"][0]["height"]

    # Inicjalizuj heatmap
    heatmap = np.zeros(grid_size)
    grid_h, grid_w = grid_size

    # Dla każdej anotacji
    for ann in coco["annotations"]:
        bbox = ann["bbox"]  # [x, y, width, height]
        x, y, w, h = bbox

        # Środek bbox
        cx = x + w / 2
        cy = y + h / 2

        # Indeksy siatki
        grid_x = int(cx / img_width * grid_w)
        grid_y = int(cy / img_height * grid_h)

        # Clamp
        grid_x = min(max(grid_x, 0), grid_w - 1)
        grid_y = min(max(grid_y, 0), grid_h - 1)

        heatmap[grid_y, grid_x] += 1

    return heatmap


def visualize_category_distributions(category_stats: Dict, output_dir: Path):
    """Wizualizuj rozkłady metryk per kategoria."""
    output_dir.mkdir(parents=True, exist_ok=True)

    categories = sorted(category_stats.keys())
    cat_names = [category_stats[cid]["name"] for cid in categories]

    # 1. Liczność kategorii (bar chart)
    fig, ax = plt.subplots(figsize=(10, 6))
    counts = [category_stats[cid]["count"] for cid in categories]
    ax.bar(cat_names, counts, color="steelblue")
    ax.set_xlabel("Kategoria", fontsize=12)
    ax.set_ylabel("Liczba anotacji", fontsize=12)
    ax.set_title("Rozkład liczności kategorii", fontsize=14, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "category_counts.png", dpi=150)
    plt.close()
    print(f"  ✅ Zapisano: {output_dir / 'category_counts.png'}")

    # 2. Rozkład obszarów bbox (box plot)
    fig, ax = plt.subplots(figsize=(10, 6))
    areas_data = [category_stats[cid]["bbox_areas"] for cid in categories]
    ax.boxplot(areas_data, labels=cat_names, patch_artist=True)
    ax.set_xlabel("Kategoria", fontsize=12)
    ax.set_ylabel("Obszar bbox (px²)", fontsize=12)
    ax.set_title("Rozkład obszarów bbox per kategoria", fontsize=14, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "bbox_areas_boxplot.png", dpi=150)
    plt.close()
    print(f"  ✅ Zapisano: {output_dir / 'bbox_areas_boxplot.png'}")

    # 3. Rozkład aspect ratio (box plot)
    fig, ax = plt.subplots(figsize=(10, 6))
    ar_data = [category_stats[cid]["aspect_ratios"] for cid in categories]
    ax.boxplot(ar_data, labels=cat_names, patch_artist=True)
    ax.set_xlabel("Kategoria", fontsize=12)
    ax.set_ylabel("Aspect Ratio (width/height)", fontsize=12)
    ax.set_title("Rozkład aspect ratio per kategoria", fontsize=14, fontweight="bold")
    ax.axhline(y=1.0, color="red", linestyle="--", alpha=0.5, label="1:1 (kwadrat)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "aspect_ratios_boxplot.png", dpi=150)
    plt.close()
    print(f"  ✅ Zapisano: {output_dir / 'aspect_ratios_boxplot.png'}")


def visualize_coverage_heatmap(heatmap: np.ndarray, output_dir: Path):
    """Wizualizuj heatmap pokrycia."""
    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(heatmap, cmap="YlOrRd", interpolation="nearest")
    ax.set_xlabel("Współrzędna X (grid)", fontsize=12)
    ax.set_ylabel("Współrzędna Y (grid)", fontsize=12)
    ax.set_title("Heatmap pokrycia anotacji (środki bbox)", fontsize=14, fontweight="bold")

    # Colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Liczba anotacji", fontsize=12)

    # Grid
    ax.set_xticks(np.arange(heatmap.shape[1]))
    ax.set_yticks(np.arange(heatmap.shape[0]))
    ax.grid(which="both", color="white", linestyle="-", linewidth=0.5)

    plt.tight_layout()
    plt.savefig(output_dir / "coverage_heatmap.png", dpi=150)
    plt.close()
    print(f"  ✅ Zapisano: {output_dir / 'coverage_heatmap.png'}")


def generate_report(coco: Dict, category_stats: Dict, outliers: List[Dict], heatmap: np.ndarray, args) -> Dict:
    """Generuj kompletny raport jakości."""
    report = {
        "metadata": {
            "date_generated": datetime.now().isoformat(),
            "input_file": args.input,
            "total_images": len(coco["images"]),
            "total_annotations": len(coco["annotations"]),
            "total_categories": len(coco["categories"]),
        },
        "category_statistics": {},
        "outliers": {"count": len(outliers), "annotations": outliers if not args.no_outliers else []},
        "coverage_heatmap": {"grid_size": heatmap.shape, "max_density": float(np.max(heatmap))},
    }

    # Statystyki per kategoria
    for cat_id, stats in category_stats.items():
        report["category_statistics"][stats["name"]] = {
            "count": stats["count"],
            "percentage": (stats["count"] / len(coco["annotations"]) * 100) if coco["annotations"] else 0,
            "bbox_area": compute_summary_statistics(stats["bbox_areas"]),
            "aspect_ratio": compute_summary_statistics(stats["aspect_ratios"]),
            "width": compute_summary_statistics(stats["widths"]),
            "height": compute_summary_statistics(stats["heights"]),
        }

    return report


def print_report_summary(report: Dict):
    """Wypisz podsumowanie raportu."""
    print("\n" + "=" * 60)
    print("📊 RAPORT JAKOŚCI DATASETU")
    print("=" * 60)

    meta = report["metadata"]
    print(f"\n📁 Plik: {meta['input_file']}")
    print(f"📅 Data: {meta['date_generated']}")
    print(f"🖼️  Obrazy: {meta['total_images']}")
    print(f"📝 Anotacje: {meta['total_annotations']}")
    print(f"🏷️  Kategorie: {meta['total_categories']}")

    print("\n🏷️  STATYSTYKI PER KATEGORIA:")
    for cat_name, stats in report["category_statistics"].items():
        print(f"\n  {cat_name}:")
        print(f"    Liczność: {stats['count']} ({stats['percentage']:.1f}%)")
        print(
            f"    Obszar bbox: {stats['bbox_area']['mean']:.1f} ± {stats['bbox_area']['std']:.1f} px² "
            f"(min: {stats['bbox_area']['min']:.1f}, max: {stats['bbox_area']['max']:.1f})"
        )
        print(
            f"    Aspect ratio: {stats['aspect_ratio']['mean']:.2f} ± {stats['aspect_ratio']['std']:.2f} "
            f"(min: {stats['aspect_ratio']['min']:.2f}, max: {stats['aspect_ratio']['max']:.2f})"
        )
        print(
            f"    Wymiary: {stats['width']['mean']:.1f}x{stats['height']['mean']:.1f} px "
            f"(±{stats['width']['std']:.1f}x{stats['height']['std']:.1f})"
        )

    print("\n⚠️  OUTLIERS:")
    print(f"  Wykryte: {report['outliers']['count']} anotacji")
    if report["outliers"]["annotations"]:
        print("  Top 5 outliers:")
        for outlier in sorted(report["outliers"]["annotations"], key=lambda x: x["z_score"], reverse=True)[:5]:
            print(
                f"    - Ann {outlier['annotation_id']}: {outlier['category_name']}, "
                f"area={outlier['area']:.1f} px², z-score={outlier['z_score']:.2f}"
            )

    print("\n🗺️  POKRYCIE:")
    print(f"  Grid size: {report['coverage_heatmap']['grid_size']}")
    print(f"  Max density: {report['coverage_heatmap']['max_density']:.1f} anotacji/komórka")

    print("\n" + "=" * 60)


def main():
    args = parse_args()

    print("🔄 Wczytuję dataset COCO...")
    coco = load_coco(args.input)
    print(f"  ✅ {len(coco['images'])} obrazów, {len(coco['annotations'])} anotacji")

    print("\n📊 Analizuję statystyki kategorii...")
    category_stats = analyze_category_statistics(coco)
    print(f"  ✅ Przeanalizowano {len(category_stats)} kategorii")

    # Outliers
    outliers = []
    if not args.no_outliers:
        print(f"\n🔍 Wykrywanie outliers (próg: {args.outlier_threshold} std dev)...")
        outliers = find_annotation_outliers(coco, category_stats, args.outlier_threshold)
        print(f"  ✅ Wykryto {len(outliers)} outliers")

    # Heatmap
    print("\n🗺️  Obliczanie heatmap pokrycia...")
    heatmap = compute_coverage_heatmap(coco, grid_size=(10, 10))
    print(f"  ✅ Heatmap {heatmap.shape}")

    # Generuj raport
    print("\n📝 Generowanie raportu...")
    report = generate_report(coco, category_stats, outliers, heatmap, args)

    # Zapisz JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(report, str(output_path))
    print(f"  ✅ Zapisano: {output_path}")

    # Wizualizacje
    if args.visualize:
        print("\n📊 Generowanie wizualizacji...")
        output_dir = Path(args.output_dir)
        visualize_category_distributions(category_stats, output_dir)
        visualize_coverage_heatmap(heatmap, output_dir)
        print(f"  ✅ Wizualizacje zapisane w: {output_dir}")

    # Podsumowanie
    print_report_summary(report)

    print("\n✅ Analiza zakończona pomyślnie!")


if __name__ == "__main__":
    main()
