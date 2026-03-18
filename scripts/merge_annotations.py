#!/usr/bin/env python
"""
Merge wielu plików COCO JSON z różnych źródeł do jednego datasetu.

Łączy anotacje COCO z różnych źródeł (np. syntetyczne + Label Studio + ręczne)
z automatyczną renumeracją ID i walidacją spójności kategorii.

Usage:
    # Merge 2 plików
    python scripts/merge_annotations.py \
        --inputs data/synthetic/coco_annotations.json data/labelstudio/export.json \
        --output data/merged/combined.json

    # Merge wielu plików
    python scripts/merge_annotations.py \
        --inputs file1.json file2.json file3.json \
        --output merged.json

    # Z automatycznym mapowaniem kategorii
    python scripts/merge_annotations.py --inputs *.json --output merged.json --auto-map-categories
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Merge multiple COCO JSON files into one dataset")
    parser.add_argument("--inputs", type=str, nargs="+", required=True, help="Input COCO JSON files to merge")
    parser.add_argument("--output", type=str, required=True, help="Output merged COCO JSON file")
    parser.add_argument(
        "--auto-map-categories",
        action="store_true",
        help="Automatically map categories by name (merge duplicates, warn on conflicts)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="Validate merged dataset for consistency (default: True)",
    )

    return parser.parse_args()


def load_coco(path: str) -> Dict:
    """Wczytaj plik COCO JSON."""
    print(f"  📂 Wczytuję: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_coco(coco: Dict, path: str):
    """Zapisz plik COCO JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(coco, f, indent=2, ensure_ascii=False)


def merge_categories(coco_files: List[Dict], auto_map: bool = False) -> Tuple[List[Dict], Dict[Tuple[int, int], int]]:
    """
    Merge kategorii z wielu plików COCO.

    Args:
        coco_files: Lista dict'ów COCO
        auto_map: Czy automatycznie mapować kategorie o tej samej nazwie

    Returns:
        Tuple of (merged_categories, category_mapping)
        category_mapping: Dict[(file_idx, old_cat_id)] = new_cat_id
    """
    category_mapping = {}  # (file_idx, old_cat_id) -> new_cat_id
    merged_categories = []
    next_cat_id = 1

    # Słownik name -> new_cat_id (do auto-mapowania)
    name_to_id = {}

    for file_idx, coco in enumerate(coco_files):
        for cat in coco.get("categories", []):
            old_cat_id = cat["id"]
            cat_name = cat["name"]

            if auto_map and cat_name in name_to_id:
                # Użyj istniejącej kategorii o tej samej nazwie
                new_cat_id = name_to_id[cat_name]
                category_mapping[(file_idx, old_cat_id)] = new_cat_id
                print(f"    ↪️  Mapowanie: plik {file_idx} kategoria '{cat_name}' (id={old_cat_id}) -> id={new_cat_id}")
            else:
                # Dodaj nową kategorię
                new_cat_id = next_cat_id
                next_cat_id += 1

                merged_categories.append(
                    {
                        "id": new_cat_id,
                        "name": cat_name,
                        "supercategory": cat.get("supercategory", "object"),
                    }
                )

                category_mapping[(file_idx, old_cat_id)] = new_cat_id
                name_to_id[cat_name] = new_cat_id

    return merged_categories, category_mapping


def merge_images(coco_files: List[Dict]) -> Tuple[List[Dict], Dict[Tuple[int, int], int]]:
    """
    Merge obrazów z wielu plików COCO.

    Args:
        coco_files: Lista dict'ów COCO

    Returns:
        Tuple of (merged_images, image_mapping)
        image_mapping: Dict[(file_idx, old_img_id)] = new_img_id
    """
    image_mapping = {}  # (file_idx, old_img_id) -> new_img_id
    merged_images = []
    next_img_id = 1

    # Śledzenie duplikatów file_name
    seen_filenames = set()

    for file_idx, coco in enumerate(coco_files):
        for img in coco.get("images", []):
            old_img_id = img["id"]
            file_name = img["file_name"]

            # Sprawdź duplikaty
            if file_name in seen_filenames:
                print(f"    ⚠️  Ostrzeżenie: Duplikat file_name '{file_name}' w pliku {file_idx} (id={old_img_id})")

            seen_filenames.add(file_name)

            # Nowy image_id
            new_img_id = next_img_id
            next_img_id += 1

            # Kopiuj obraz z nowym ID
            new_img = {
                "id": new_img_id,
                "width": img["width"],
                "height": img["height"],
                "file_name": file_name,
                "license": img.get("license", 1),
                "date_captured": img.get("date_captured", datetime.now().isoformat()),
            }

            merged_images.append(new_img)
            image_mapping[(file_idx, old_img_id)] = new_img_id

    return merged_images, image_mapping


def merge_annotations(
    coco_files: List[Dict], image_mapping: Dict[Tuple[int, int], int], category_mapping: Dict[Tuple[int, int], int]
) -> List[Dict]:
    """
    Merge anotacji z wielu plików COCO.

    Args:
        coco_files: Lista dict'ów COCO
        image_mapping: Dict[(file_idx, old_img_id)] = new_img_id
        category_mapping: Dict[(file_idx, old_cat_id)] = new_cat_id

    Returns:
        Lista merged annotations
    """
    merged_annotations = []
    next_ann_id = 1

    for file_idx, coco in enumerate(coco_files):
        for ann in coco.get("annotations", []):
            old_img_id = ann["image_id"]
            old_cat_id = ann["category_id"]

            # Mapuj ID
            new_img_id = image_mapping.get((file_idx, old_img_id))
            new_cat_id = category_mapping.get((file_idx, old_cat_id))

            if new_img_id is None:
                print(f"    ⚠️  Ostrzeżenie: Brak mapowania image_id={old_img_id} w pliku {file_idx}, pomijam anotację")
                continue

            if new_cat_id is None:
                print(
                    f"    ⚠️  Ostrzeżenie: Brak mapowania category_id={old_cat_id} w pliku {file_idx}, pomijam anotację"
                )
                continue

            # Nowa anotacja
            new_ann = {
                "id": next_ann_id,
                "image_id": new_img_id,
                "category_id": new_cat_id,
                "bbox": ann["bbox"],
                "area": ann["area"],
                "iscrowd": ann.get("iscrowd", 0),
            }

            # Segmentation (opcjonalne)
            if "segmentation" in ann:
                new_ann["segmentation"] = ann["segmentation"]

            merged_annotations.append(new_ann)
            next_ann_id += 1

    return merged_annotations


def validate_merged_coco(coco: Dict) -> bool:
    """
    Waliduj merged COCO dataset.

    Returns:
        True jeśli valid, False jeśli są błędy
    """
    print("\n🔍 Walidacja merged datasetu...")
    errors = []

    # Sprawdź wymagane pola
    required_fields = ["info", "images", "annotations", "categories"]
    for field in required_fields:
        if field not in coco:
            errors.append(f"Brak wymaganego pola: {field}")

    # Sprawdź duplikaty ID
    image_ids = [img["id"] for img in coco["images"]]
    if len(image_ids) != len(set(image_ids)):
        errors.append("Duplikaty image_id w merged dataset")

    ann_ids = [ann["id"] for ann in coco["annotations"]]
    if len(ann_ids) != len(set(ann_ids)):
        errors.append("Duplikaty annotation_id w merged dataset")

    cat_ids = [cat["id"] for cat in coco["categories"]]
    if len(cat_ids) != len(set(cat_ids)):
        errors.append("Duplikaty category_id w merged dataset")

    # Sprawdź referencje
    valid_img_ids = set(image_ids)
    valid_cat_ids = set(cat_ids)

    for ann in coco["annotations"]:
        if ann["image_id"] not in valid_img_ids:
            errors.append(f"Annotation {ann['id']}: referencja do nieistniejącego image_id={ann['image_id']}")
        if ann["category_id"] not in valid_cat_ids:
            errors.append(f"Annotation {ann['id']}: referencja do nieistniejącej category_id={ann['category_id']}")

    if errors:
        print("  ❌ Znaleziono błędy:")
        for err in errors[:10]:  # Pokaż max 10 błędów
            print(f"    - {err}")
        if len(errors) > 10:
            print(f"    ... i {len(errors) - 10} więcej")
        return False
    else:
        print("  ✅ Walidacja OK!")
        return True


def print_merge_summary(coco_files: List[Dict], merged_coco: Dict):
    """Wypisz podsumowanie merge'u."""
    print("\n" + "=" * 60)
    print("📊 Podsumowanie merge'u:")
    print("=" * 60)

    # Input files
    print(f"\n📥 Pliki wejściowe: {len(coco_files)}")
    for idx, coco in enumerate(coco_files):
        print(
            f"  {idx+1}. {len(coco.get('images', []))} obrazów, "
            f"{len(coco.get('annotations', []))} anotacji, "
            f"{len(coco.get('categories', []))} kategorii"
        )

    # Merged file
    print("\n📤 Merged dataset:")
    print(f"  Obrazy: {len(merged_coco['images'])}")
    print(f"  Anotacje: {len(merged_coco['annotations'])}")
    print(f"  Kategorie: {len(merged_coco['categories'])}")

    # Kategorie
    print("\n🏷️  Kategorie w merged datasecie:")
    for cat in merged_coco["categories"]:
        cat_anns = [ann for ann in merged_coco["annotations"] if ann["category_id"] == cat["id"]]
        print(f"  - {cat['name']} (id={cat['id']}): {len(cat_anns)} anotacji")

    print("=" * 60)


def main():
    args = parse_args()

    # Walidacja
    if len(args.inputs) < 2:
        raise ValueError("Musisz podać przynajmniej 2 pliki wejściowe do merge'u")

    # Przygotuj output dir
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Wczytaj pliki
    print("🔄 Wczytuję pliki COCO...")
    coco_files = []
    for input_path in args.inputs:
        if not Path(input_path).exists():
            print(f"  ⚠️  Ostrzeżenie: Plik nie istnieje: {input_path}, pomijam")
            continue
        coco_files.append(load_coco(input_path))

    if len(coco_files) < 2:
        raise ValueError("Nie udało się wczytać przynajmniej 2 plików")

    print(f"\n✅ Wczytano {len(coco_files)} plików")

    # Merge kategorii
    print(f"\n🏷️  Merge kategorii (auto_map={args.auto_map_categories})...")
    merged_categories, category_mapping = merge_categories(coco_files, args.auto_map_categories)
    print(f"  ✅ Merged: {len(merged_categories)} unikalnych kategorii")

    # Merge obrazów
    print("\n🖼️  Merge obrazów...")
    merged_images, image_mapping = merge_images(coco_files)
    print(f"  ✅ Merged: {len(merged_images)} obrazów")

    # Merge anotacji
    print("\n📝 Merge anotacji...")
    merged_annotations = merge_annotations(coco_files, image_mapping, category_mapping)
    print(f"  ✅ Merged: {len(merged_annotations)} anotacji")

    # Stwórz merged COCO
    merged_coco = {
        "info": {
            "description": "Merged COCO dataset from multiple sources",
            "version": "1.0",
            "year": 2025,
            "contributor": "Talk_electronic merge_annotations.py",
            "date_created": datetime.now().isoformat(),
        },
        "licenses": [{"id": 1, "name": "Mixed Licenses", "url": ""}],
        "categories": merged_categories,
        "images": merged_images,
        "annotations": merged_annotations,
    }

    # Walidacja
    if args.validate:
        if not validate_merged_coco(merged_coco):
            print("\n❌ Walidacja nie powiodła się! Sprawdź błędy powyżej.")
            return

    # Zapisz
    print(f"\n💾 Zapisuję merged dataset do: {output_path}")
    save_coco(merged_coco, str(output_path))

    # Podsumowanie
    print_merge_summary(coco_files, merged_coco)

    print("\n✅ Merge zakończony pomyślnie!")
    print(f"📁 Plik zapisany: {output_path}")


if __name__ == "__main__":
    main()
