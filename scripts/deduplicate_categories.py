#!/usr/bin/env python3
"""
Usuń duplikaty kategorii w coco_v2_400.json - zostaw tylko 4 kategorie.
"""

import json
from pathlib import Path


def main():
    input_file = Path("data/synthetic/coco_v2_400.json")
    output_file = Path("data/synthetic/coco_v2_400_fixed.json")

    print(f"📂 Wczytywanie: {input_file}")
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("\n📊 Status przed naprawą:")
    print(f"   - Obrazy: {len(data['images'])}")
    print(f"   - Anotacje: {len(data['annotations'])}")
    print(f"   - Kategorie: {len(data['categories'])}")

    # Pokaż aktualne kategorie
    print("\n🏷️  Obecne kategorie:")
    for cat in data["categories"]:
        count = sum(1 for ann in data["annotations"] if ann["category_id"] == cat["id"])
        print(f"   - {cat['name']} (id={cat['id']}): {count} anotacji")

    # Mapowanie: name -> canonical category_id
    canonical_categories = {"resistor": 1, "capacitor": 2, "inductor": 3, "diode": 4}

    # Mapowanie: old_category_id -> new_category_id
    category_mapping = {}
    for cat in data["categories"]:
        old_id = cat["id"]
        canonical_id = canonical_categories[cat["name"]]
        category_mapping[old_id] = canonical_id

    print("\n🔄 Mapowanie kategorii:")
    for old_id, new_id in category_mapping.items():
        if old_id != new_id:
            cat_name = next(c["name"] for c in data["categories"] if c["id"] == old_id)
            print(f"   - {cat_name} (id={old_id}) -> id={new_id}")

    # Aktualizuj category_id w anotacjach
    print("\n🔄 Aktualizacja anotacji...")
    for ann in data["annotations"]:
        old_cat_id = ann["category_id"]
        ann["category_id"] = category_mapping[old_cat_id]

    # Zostaw tylko 4 unikalne kategorie
    unique_categories = []
    seen_names = set()
    for cat in data["categories"]:
        if cat["name"] not in seen_names:
            # Ustaw canonical ID
            cat["id"] = canonical_categories[cat["name"]]
            unique_categories.append(cat)
            seen_names.add(cat["name"])

    data["categories"] = unique_categories

    print(f"   ✅ Zaktualizowano {len(data['annotations'])} anotacji")

    # Weryfikacja
    print("\n🔍 Weryfikacja po naprawie:")
    print(f"   - Kategorie: {len(data['categories'])}")
    for cat in data["categories"]:
        count = sum(1 for ann in data["annotations"] if ann["category_id"] == cat["id"])
        print(f"   - {cat['name']} (id={cat['id']}): {count} anotacji")

    # Zapisz
    print(f"\n💾 Zapisywanie: {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("\n✅ Gotowe!")
    print("\n📈 Dataset v2.0 (fixed):")
    print(f"   - Obrazy: {len(data['images'])}")
    print(f"   - Anotacje: {len(data['annotations'])}")
    print(f"   - Kategorie: {len(data['categories'])} ✅")


if __name__ == "__main__":
    main()
