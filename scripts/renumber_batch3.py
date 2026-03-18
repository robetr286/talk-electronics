#!/usr/bin/env python3
"""
Przenumeruj pliki w batch3: schematic_001-200 -> schematic_251-450
Aktualizuje zarówno JSON jak i nazwy plików PNG.
"""

import json
import shutil
from pathlib import Path


def main():
    # Parametry
    coco_input = Path("data/synthetic/coco_batch3.json")
    coco_output = Path("data/synthetic/coco_batch3_renamed.json")
    images_dir = Path("data/synthetic/images_batch3")
    offset = 250  # schematic_001 -> schematic_251

    print(f"📂 Wczytywanie: {coco_input}")
    with open(coco_input, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("📊 Status:")
    print(f"   - Obrazy: {len(data['images'])}")
    print(f"   - Anotacje: {len(data['annotations'])}")
    print(f"   - Kategorie: {len(data['categories'])}")

    # Przygotuj mapowanie starych ID -> nowych ID
    old_to_new_id = {}

    # 1. Przenumeruj obrazy i nazwy plików
    print(f"\n🔄 Przenumerowanie obrazów (offset +{offset})...")
    for img in data["images"]:
        old_id = img["id"]
        new_id = old_id + offset
        old_filename = img["file_name"]

        # Wyciągnij numer z nazwy (np. schematic_042.png -> 42)
        old_num = int(old_filename.replace("schematic_", "").replace(".png", ""))
        new_num = old_num + offset
        new_filename = f"schematic_{new_num:03d}.png"

        # Zaktualizuj JSON
        img["id"] = new_id
        img["file_name"] = new_filename

        # Zapisz mapowanie
        old_to_new_id[old_id] = new_id

        # Zmień nazwę pliku fizycznego
        old_path = images_dir / old_filename
        new_path = images_dir / new_filename

        if old_path.exists():
            shutil.move(str(old_path), str(new_path))

    print(f"   ✅ Przenumerowano {len(data['images'])} obrazów")

    # 2. Zaktualizuj image_id w anotacjach
    print("\n🔄 Aktualizacja anotacji...")
    for ann in data["annotations"]:
        old_image_id = ann["image_id"]
        if old_image_id in old_to_new_id:
            ann["image_id"] = old_to_new_id[old_image_id]

    print(f"   ✅ Zaktualizowano {len(data['annotations'])} anotacji")

    # 3. Zapisz nowy JSON
    print(f"\n💾 Zapisywanie: {coco_output}")
    with open(coco_output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("\n✅ Gotowe!")
    print("\n📈 Nowe zakresy:")
    print(f"   - Image IDs: {min(img['id'] for img in data['images'])} - {max(img['id'] for img in data['images'])}")
    first_idx = min(old_to_new_id.values())
    last_idx = max(old_to_new_id.values())
    print(f"   - Filenames: schematic_{first_idx:03d}.png - schematic_{last_idx:03d}.png")

    # Weryfikacja
    filenames = {img["file_name"] for img in data["images"]}
    print("\n🔍 Weryfikacja:")
    print(f"   - Unikalne nazwy plików: {len(filenames)}")
    print(f"   - Pierwsze 5: {sorted(list(filenames))[:5]}")
    print(f"   - Ostatnie 5: {sorted(list(filenames))[-5:]}")


if __name__ == "__main__":
    main()
