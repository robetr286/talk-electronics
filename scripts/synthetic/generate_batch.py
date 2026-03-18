#!/usr/bin/env python3
"""
Masowa generacja syntetycznych schematów elektronicznych z augmentacją.

Ten skrypt generuje setki różnorodnych syntetycznych schematów do treningu YOLOv8:
- Różna liczba komponentów (5-50)
- Różne rozmiary canvas (800x600 do 2000x1500)
- Różne gęstości elementów
- Automatyczna konwersja do formatu YOLO

Użycie:
    python generate_batch.py --count 500 --output data/synthetic_batch
"""

import argparse
import json
import random
import sys
from pathlib import Path

# Dodaj ścieżkę do modułów projektu
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from scripts.synthetic.generate_schematic import SchematicConfig, SchematicGenerator
except Exception:
    # fallback - if the import above fails for some reason, try adding project root and importing again
    sys.path.insert(0, str(project_root))
    from scripts.synthetic.generate_schematic import SchematicConfig, SchematicGenerator


def generate_diverse_batch(output_dir: Path, count: int = 500, start_seed: int = 1000, op_amp_boost: int = 3):
    """
    Generuje zróżnicowany batch syntetycznych schematów.

    Args:
        output_dir: Katalog wyjściowy
        count: Liczba schematów do wygenerowania
        start_seed: Początkowy seed (dla powtarzalności)
    """
    output_dir = Path(output_dir)
    images_dir = output_dir / "images"
    labels_dir = output_dir / "labels"
    metadata_dir = output_dir / "metadata"

    # Utwórz katalogi
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    print(f"🚀 Generowanie {count} syntetycznych schematów...")
    print(f"📁 Output: {output_dir}")

    stats = {
        "total_images": 0,
        "total_components": 0,
        "by_type": {},
        "canvas_sizes": [],
    }

    # Różne rozmiary canvas dla różnorodności
    canvas_sizes = [
        (800, 600),  # Małe
        (1000, 800),  # Średnie (domyślne)
        (1200, 900),  # Większe
        (1600, 1200),  # Duże
        (2000, 1500),  # Bardzo duże
    ]

    # Różne liczby komponentów
    component_counts = list(range(5, 51, 5))  # 5, 10, 15, ..., 50

    # Większa liczba powtórzeń "A" wzmacnia udział op_amp w generatorze
    base_types = ["R", "C", "L", "D"]
    op_amp_pool = max(1, op_amp_boost)
    component_types = base_types + ["A"] * op_amp_pool

    for i in range(count):
        seed = start_seed + i

        # Losuj parametry dla różnorodności
        random.seed(seed)

        num_components = random.choice(component_counts)
        canvas_size = random.choice(canvas_sizes)

        # Konfiguracja
        config = SchematicConfig(
            seed=seed, num_components=num_components, component_types=component_types, canvas_size=canvas_size
        )

        # Generuj schemat
        generator = SchematicGenerator(config)
        metadata = generator.generate()

        # Nazwy plików
        base_name = f"synthetic_{seed:06d}"
        image_path = images_dir / f"{base_name}.png"
        metadata_path = metadata_dir / f"{base_name}.json"

        # Zapisz obraz
        generator.export_to_png(image_path)

        # Zapisz metadane (generator ma już tę metodę)
        generator.save_metadata(metadata_path)

        # Konwertuj do formatu YOLO
        yolo_label_path = labels_dir / f"{base_name}.txt"
        convert_to_yolo_format(metadata, canvas_size, yolo_label_path)

        # Statystyki
        stats["total_images"] += 1
        stats["total_components"] += len(metadata["components"])
        stats["canvas_sizes"].append(canvas_size)

        for comp in metadata["components"]:
            comp_type = comp["type"]
            stats["by_type"][comp_type] = stats["by_type"].get(comp_type, 0) + 1

        # Progress
        if (i + 1) % 50 == 0:
            print(f"✅ Wygenerowano {i + 1}/{count} schematów...")

    # Zapisz statystyki
    stats_path = output_dir / "generation_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        # Konwertuj tuple na string dla JSON
        stats["canvas_sizes"] = [f"{w}x{h}" for w, h in stats["canvas_sizes"]]
        json.dump(stats, f, indent=2)

    print("\n✅ Zakończono generację!")
    print("📊 Statystyki:")
    print(f"   - Obrazy: {stats['total_images']}")
    print(f"   - Komponenty łącznie: {stats['total_components']}")
    print(f"   - Średnio komponentów/obraz: {stats['total_components']/stats['total_images']:.1f}")
    print("   - Rozłożenie typów:")
    for comp_type, count_val in stats["by_type"].items():
        print(f"     * {comp_type}: {count_val}")

    # Generuj dataset.yaml
    generate_dataset_yaml(output_dir, stats)

    print(f"\n📝 Dataset YAML: {output_dir / 'dataset.yaml'}")
    print("\n🎯 Gotowe do treningu!")
    print("   Uruchom: python train_yolo.py")


def convert_to_yolo_format(metadata: dict, canvas_size: tuple, output_path: Path):
    """
    Konwertuje metadane do formatu YOLO (normalized bounding boxes).

    Format YOLO (dla segmentacji):
    <class_id> <x1> <y1> <x2> <y2> <x3> <y3> <x4> <y4>

    Dla prostokątów (4 punkty narożników, normalized [0,1]).
    """
    width, height = canvas_size

    # Mapowanie typów na class_id
    type_to_id = {"R": 0, "C": 1, "L": 2, "D": 3, "A": 4}  # 5 klas: + op_amp

    lines = []

    for comp in metadata.get("components", []):
        comp_type = comp["type"]
        class_id = type_to_id.get(comp_type, 0)

        # Bounding box
        x, y = comp["position"]
        w = comp["width"]
        h = comp["height"]

        # 4 narożniki prostokąta (normalized)
        x1_norm = (x - w / 2) / width
        y1_norm = (y - h / 2) / height
        x2_norm = (x + w / 2) / width
        y2_norm = (y - h / 2) / height
        x3_norm = (x + w / 2) / width
        y3_norm = (y + h / 2) / height
        x4_norm = (x - w / 2) / width
        y4_norm = (y + h / 2) / height

        # Clamp do [0, 1]
        def clamp(val):
            return max(0.0, min(1.0, val))

        x1_norm = clamp(x1_norm)
        y1_norm = clamp(y1_norm)
        x2_norm = clamp(x2_norm)
        y2_norm = clamp(y2_norm)
        x3_norm = clamp(x3_norm)
        y3_norm = clamp(y3_norm)
        x4_norm = clamp(x4_norm)
        y4_norm = clamp(y4_norm)

        # Format: class_id x1 y1 x2 y2 x3 y3 x4 y4
        line = "{} {:.6f} {:.6f} {:.6f} {:.6f} {:.6f} {:.6f} {:.6f} {:.6f}".format(
            class_id,
            x1_norm,
            y1_norm,
            x2_norm,
            y2_norm,
            x3_norm,
            y3_norm,
            x4_norm,
            y4_norm,
        )
        lines.append(line)

    # Zapisz
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_dataset_yaml(output_dir: Path, stats: dict):
    """Generuje plik dataset.yaml dla YOLOv8."""
    lines = [
        "# YOLOv8 Segmentation Dataset",
        "# Syntetyczne schematy elektroniczne - batch automatyczny",
        "",
        f"path: {output_dir.absolute()}",
        "train: images",
        "val: images",
        "test: images",
        "",
        "# Classes",
        "nc: 5",
        "names:",
        "  0: resistor",
        "  1: capacitor",
        "  2: inductor",
        "  3: diode",
        "  4: op_amp",
        "",
        "# Stats",
        f"# Total images: {stats['total_images']}",
        f"# Total components: {stats['total_components']}",
        f"# Average components per image: {stats['total_components']/stats['total_images']:.1f}",
        "",
    ]
    yaml_content = "\n".join(lines)

    yaml_path = output_dir / "dataset.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)


def main():
    parser = argparse.ArgumentParser(description="Masowa generacja syntetycznych schematów elektronicznych")
    parser.add_argument("--count", type=int, default=500, help="Liczba schematów do wygenerowania (default: 500)")
    parser.add_argument(
        "--output",
        type=str,
        default="data/synthetic_batch",
        help="Katalog wyjściowy (default: data/synthetic_batch)",
    )
    parser.add_argument(
        "--start-seed",
        type=int,
        default=1000,
        help="Początkowy seed dla generatora (default: 1000)",
    )
    parser.add_argument(
        "--op-amp-boost",
        type=int,
        default=3,
        help="Ile razy powielić op_amp w puli typów (>=1 zwiększa udział op_amp)",
    )

    args = parser.parse_args()

    generate_diverse_batch(
        output_dir=Path(args.output), count=args.count, start_seed=args.start_seed, op_amp_boost=args.op_amp_boost
    )


if __name__ == "__main__":
    main()
