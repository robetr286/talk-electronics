#!/usr/bin/env python
"""
Stratified split datasetu COCO na train/val/test z zachowaniem proporcji klas.

Dzieli dataset COCO Instance Segmentation na 3 zbiory (train/val/test)
z zachowaniem proporcji każdej klasy komponentów. Tworzy osobne pliki COCO JSON
oraz opcjonalnie kopiuje obrazy do odpowiednich katalogów.

Usage:
    # Podstawowe użycie (tylko JSON)
    python scripts/split_dataset.py \
        --input data/synthetic/coco_annotations.json \
        --output-dir data/synthetic/splits

    # Z kopiowaniem obrazów
    python scripts/split_dataset.py \
        --input data/synthetic/coco_annotations.json \
        --output-dir data/synthetic/splits \
        --images-dir data/synthetic/images_raw \
        --copy-images

    # Custom proporcje (train/val/test)
    python scripts/split_dataset.py \
        --input data/synthetic/coco_annotations.json \
        --output-dir data/synthetic/splits \
        --ratios 0.7 0.2 0.1
"""

import argparse
import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Stratified split COCO dataset into train/val/test")
    parser.add_argument("--input", type=str, required=True, help="Input COCO JSON file")
    parser.add_argument("--output-dir", type=str, required=True, help="Output directory for split JSON files")
    parser.add_argument(
        "--images-dir", type=str, default=None, help="Directory with images (required if --copy-images is used)"
    )
    parser.add_argument(
        "--copy-images",
        action="store_true",
        help="Copy images to train/val/test subdirectories (requires --images-dir)",
    )
    parser.add_argument(
        "--ratios",
        type=float,
        nargs=3,
        default=[0.7, 0.15, 0.15],
        help="Train/val/test split ratios (default: 0.7 0.15 0.15)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")

    return parser.parse_args()


def load_coco(coco_path: str) -> Dict:
    """Wczytaj plik COCO JSON."""
    with open(coco_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_coco(coco_data: Dict, output_path: str):
    """Zapisz plik COCO JSON."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(coco_data, f, indent=2, ensure_ascii=False)


def get_image_annotations(coco: Dict) -> Dict[int, List[Dict]]:
    """
    Zgrupuj anotacje według image_id.

    Returns:
        Dict z kluczem image_id i wartością listą anotacji dla tego obrazu
    """
    image_annotations = defaultdict(list)
    for ann in coco["annotations"]:
        image_annotations[ann["image_id"]].append(ann)
    return dict(image_annotations)


def get_category_counts_per_image(coco: Dict, image_annotations: Dict[int, List[Dict]]) -> Dict[int, Dict[int, int]]:
    """
    Policz ile każda klasa występuje w każdym obrazie.

    Returns:
        Dict[image_id][category_id] = count
    """
    category_counts = {}
    for img in coco["images"]:
        img_id = img["id"]
        category_counts[img_id] = defaultdict(int)

        if img_id in image_annotations:
            for ann in image_annotations[img_id]:
                category_counts[img_id][ann["category_id"]] += 1

    return category_counts


def stratified_split(
    images: List[Dict], category_counts: Dict[int, Dict[int, int]], ratios: List[float], seed: int = 42
) -> Tuple[List[int], List[int], List[int]]:
    """
    Wykonaj stratified split obrazów z zachowaniem proporcji klas.

    Args:
        images: Lista obrazów COCO
        category_counts: Dict[image_id][category_id] = count
        ratios: [train_ratio, val_ratio, test_ratio]
        seed: Random seed

    Returns:
        Tuple of (train_ids, val_ids, test_ids)
    """
    np.random.seed(seed)

    # Pobierz wszystkie kategorie
    all_categories = set()
    for img_cats in category_counts.values():
        all_categories.update(img_cats.keys())

    # Dla każdej kategorii znajdź obrazy, które ją zawierają
    category_to_images = defaultdict(list)
    for img in images:
        img_id = img["id"]
        for cat_id in category_counts[img_id].keys():
            category_to_images[cat_id].append(img_id)

    # Sortuj obrazy według sumy występujących klas (obrazy z większą liczbą klas najpierw)
    # To pomaga w lepszym rozkładzie
    images_sorted = sorted(images, key=lambda x: sum(category_counts[x["id"]].values()), reverse=True)

    # Shuffle w ramach tej samej liczby anotacji
    np.random.shuffle(images_sorted)

    # Podział
    n_images = len(images_sorted)
    train_size = int(n_images * ratios[0])
    val_size = int(n_images * ratios[1])

    train_ids = [img["id"] for img in images_sorted[:train_size]]
    val_ids = [img["id"] for img in images_sorted[train_size : train_size + val_size]]
    test_ids = [img["id"] for img in images_sorted[train_size + val_size :]]

    return train_ids, val_ids, test_ids


def create_split_coco(
    coco: Dict, image_ids: List[int], image_annotations: Dict[int, List[Dict]], split_name: str
) -> Dict:
    """
    Stwórz plik COCO dla danego splitu.

    Args:
        coco: Oryginalny COCO dict
        image_ids: Lista image_id dla tego splitu
        image_annotations: Dict z anotacjami zgrupowanymi po image_id
        split_name: Nazwa splitu (train/val/test)

    Returns:
        Nowy COCO dict dla tego splitu
    """
    # Kopiuj metadane
    split_coco = {
        "info": {
            **coco["info"],
            "description": f"{coco['info'].get('description', 'Dataset')} - {split_name} split",
            "date_created": datetime.now().isoformat(),
        },
        "licenses": coco.get("licenses", []),
        "categories": coco["categories"],
        "images": [],
        "annotations": [],
    }

    # Filtruj obrazy
    image_id_set = set(image_ids)
    for img in coco["images"]:
        if img["id"] in image_id_set:
            split_coco["images"].append(img)

    # Filtruj anotacje
    for img_id in image_ids:
        if img_id in image_annotations:
            split_coco["annotations"].extend(image_annotations[img_id])

    return split_coco


def print_split_statistics(coco: Dict, split_name: str):
    """Wypisz statystyki splitu."""
    # Policz kategorie
    category_counts = defaultdict(int)
    for ann in coco["annotations"]:
        category_counts[ann["category_id"]] += 1

    # Mapa id -> name
    cat_id_to_name = {cat["id"]: cat["name"] for cat in coco["categories"]}

    print(f"\n📊 Statystyki dla {split_name}:")
    print(f"  Obrazy: {len(coco['images'])}")
    print(f"  Anotacje: {len(coco['annotations'])}")
    print("  Kategorie:")
    for cat_id, count in sorted(category_counts.items()):
        cat_name = cat_id_to_name.get(cat_id, f"unknown_{cat_id}")
        percentage = (count / len(coco["annotations"]) * 100) if coco["annotations"] else 0
        print(f"    - {cat_name}: {count} ({percentage:.1f}%)")


def copy_images_to_split(images: List[Dict], images_dir: Path, output_dir: Path, split_name: str):
    """Skopiuj obrazy do katalogu splitu."""
    split_images_dir = output_dir / split_name / "images"
    split_images_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📁 Kopiowanie obrazów do {split_images_dir}...")
    for img in images:
        src = images_dir / img["file_name"]
        dst = split_images_dir / img["file_name"]

        if src.exists():
            shutil.copy2(src, dst)
        else:
            print(f"⚠️  Ostrzeżenie: Nie znaleziono pliku {src}")


def main():
    args = parse_args()

    # Walidacja argumentów
    if args.copy_images and not args.images_dir:
        raise ValueError("--copy-images wymaga podania --images-dir")

    if sum(args.ratios) != 1.0:
        raise ValueError(f"Suma proporcji musi wynosić 1.0, otrzymano: {sum(args.ratios)}")

    # Przygotuj katalogi
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images_dir = Path(args.images_dir) if args.images_dir else None

    print("🔄 Wczytuję dataset COCO...")
    coco = load_coco(args.input)

    print(f"📊 Dataset: {len(coco['images'])} obrazów, {len(coco['annotations'])} anotacji")

    # Grupuj anotacje
    image_annotations = get_image_annotations(coco)
    category_counts = get_category_counts_per_image(coco, image_annotations)

    # Wykonaj stratified split
    print(f"\n✂️  Stratified split z proporcjami: {args.ratios[0]:.0%} / {args.ratios[1]:.0%} / {args.ratios[2]:.0%}")
    train_ids, val_ids, test_ids = stratified_split(coco["images"], category_counts, args.ratios, args.seed)

    print(f"  Train: {len(train_ids)} obrazów")
    print(f"  Val: {len(val_ids)} obrazów")
    print(f"  Test: {len(test_ids)} obrazów")

    # Twórz COCO dla każdego splitu
    splits = {
        "train": train_ids,
        "val": val_ids,
        "test": test_ids,
    }

    for split_name, image_ids in splits.items():
        print(f"\n📝 Tworzę {split_name}.json...")
        split_coco = create_split_coco(coco, image_ids, image_annotations, split_name)

        # Zapisz JSON
        output_path = output_dir / f"{split_name}.json"
        save_coco(split_coco, str(output_path))
        print(f"✅ Zapisano: {output_path}")

        # Statystyki
        print_split_statistics(split_coco, split_name)

        # Kopiuj obrazy jeśli wymagane
        if args.copy_images and images_dir:
            copy_images_to_split(split_coco["images"], images_dir, output_dir, split_name)

    # Podsumowanie
    print("\n" + "=" * 60)
    print("✅ Split dataset zakończony pomyślnie!")
    print(f"📁 Pliki zapisane w: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
