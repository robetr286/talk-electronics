# 🔄 Merge Anotacji COCO - Dokumentacja

## Przegląd

Skrypt `merge_annotations.py` łączy wiele plików COCO Instance Segmentation z różnych źródeł (syntetyczne, Label Studio, ręczne) w jeden spójny dataset z automatyczną renumeracją ID i walidacją.

## Funkcje

### ✅ Zaimplementowane

- **Automatyczna renumeracja ID** - image_id, annotation_id, category_id są renumerowane bez konfliktów
- **Auto-mapowanie kategorii** - kategorie o tej samej nazwie są scalane automatycznie
- **Walidacja spójności** - sprawdzanie duplikatów ID, brakujących referencji
- **Wykrywanie duplikatów file_name** - ostrzeżenia o potencjalnych konfliktach
- **Zachowanie metadanych** - info, licenses, wszystkie pola anotacji
- **Szczegółowe statystyki** - liczba obrazów, anotacji, rozkład kategorii

### 🎯 Kluczowe cechy

1. **Renumeracja ID**: Wszystkie ID są renumerowane od 1, brak konfliktów między plikami
2. **Mapowanie kategorii**: Opcja `--auto-map-categories` scala kategorie o tej samej nazwie
3. **Walidacja**: Sprawdza duplikaty ID, brakujące referencje image_id/category_id
4. **Ostrzeżenia**: Informuje o duplikatach file_name (ważne przy kopiowaniu obrazów)

## Użycie

### Podstawowe użycie (2 pliki)

```bash
python scripts/merge_annotations.py \
  --inputs data/synthetic/coco_annotations.json data/labelstudio/export.json \
  --output data/merged/combined.json
```

### Z auto-mapowaniem kategorii

```bash
python scripts/merge_annotations.py \
  --inputs file1.json file2.json file3.json \
  --output merged.json \
  --auto-map-categories
```

### Merge wielu plików (glob)

```bash
# PowerShell
python scripts/merge_annotations.py `
  --inputs (Get-ChildItem data/*/annotations/*.json).FullName `
  --output data/merged/all.json `
  --auto-map-categories
```

### Bez walidacji (szybszy)

```bash
python scripts/merge_annotations.py \
  --inputs file1.json file2.json \
  --output merged.json \
  --no-validate
```

## Parametry

| Parametr | Opis | Domyślna wartość |
|----------|------|------------------|
| `--inputs` | Ścieżki do plików COCO JSON (wymagane, min 2) | - |
| `--output` | Ścieżka do wyjściowego merged pliku (wymagane) | - |
| `--auto-map-categories` | Automatycznie mapuj kategorie o tej samej nazwie | False |
| `--validate` | Waliduj merged dataset | True |

## Przykłady użycia

### Case 1: Merge syntetycznych danych (raw + augmented)

```bash
python scripts/merge_annotations.py \
  --inputs data/synthetic/coco_annotations.json data/synthetic/images_augmented/annotations.json \
  --output data/synthetic/coco_merged.json \
  --auto-map-categories
```

**Rezultat**:
- Input 1: 50 obrazów, 639 anotacji, 4 kategorie (raw)
- Input 2: 50 obrazów, 639 anotacji, 4 kategorie (augmented)
- Output: 100 obrazów, 1278 anotacji, 4 kategorie

### Case 2: Merge syntetycznych + Label Studio

```bash
python scripts/merge_annotations.py \
  --inputs data/synthetic/coco_merged.json data/labelstudio/export_coco.json \
  --output data/merged/synthetic_plus_manual.json \
  --auto-map-categories
```

### Case 3: Merge wielu źródeł

```bash
python scripts/merge_annotations.py \
  --inputs \
    data/synthetic/coco_merged.json \
    data/labelstudio/export_coco.json \
    data/manual/hand_labeled.json \
  --output data/merged/full_dataset.json \
  --auto-map-categories
```

## Struktura wyjściowa

Merged COCO JSON ma standardową strukturę:

```json
{
  "info": {
    "description": "Merged COCO dataset from multiple sources",
    "version": "1.0",
    "year": 2025,
    "contributor": "Talk_electronic merge_annotations.py",
    "date_created": "2025-11-14T..."
  },
  "licenses": [...],
  "categories": [
    {"id": 1, "name": "resistor", "supercategory": "object"},
    {"id": 2, "name": "capacitor", "supercategory": "object"},
    ...
  ],
  "images": [
    {"id": 1, "width": 1000, "height": 800, "file_name": "schematic_001.png", ...},
    ...
  ],
  "annotations": [
    {"id": 1, "image_id": 1, "category_id": 1, "bbox": [...], "area": 1200, ...},
    ...
  ]
}
```

## Test na datasecie syntetycznym

### Wynik testu (14.11.2025)

**Input**:
- Plik 1: `coco_annotations.json` - 50 obrazów, 639 anotacji (raw)
- Plik 2: `images_augmented/annotations.json` - 50 obrazów, 639 anotacji (augmented)

**Output**: `coco_merged.json`

**Statystyki**:
- Obrazy: 100 (50 raw + 50 augmented)
- Anotacje: 1278 (639 + 639)
- Kategorie: 4 (resistor, capacitor, inductor, diode)

**Rozkład kategorii**:
- resistor: 334 anotacji (26.1%)
- capacitor: 300 anotacji (23.5%)
- inductor: 330 anotacji (25.8%)
- diode: 314 anotacji (24.6%)

**Obserwacje**:
✅ Renumeracja ID działa poprawnie (image_id: 1-100, annotation_id: 1-1278)
✅ Auto-mapowanie kategorii działa (4 kategorie z 2 plików → 4 kategorie w merged)
⚠️ 50 duplikatów file_name (oczekiwane - te same obrazy z augmentacją)
✅ Walidacja przeszła pomyślnie (brak konfliktów ID, wszystkie referencje OK)

## Mapowanie ID

### Kategorie

Z `--auto-map-categories`:
- Kategorie o tej samej nazwie są scalane (np. "resistor" z pliku 1 i 2 → 1 kategoria "resistor")
- Nowe kategorie dostają kolejne ID

Bez `--auto-map-categories`:
- Każda kategoria z każdego pliku dostaje nowe ID
- Duplikaty nazw są zachowane (np. resistor_1, resistor_2)

### Obrazy

- Każdy obraz dostaje nowe, unikalne image_id (1, 2, 3, ...)
- file_name jest zachowane (może być duplikat - ostrzeżenie)
- Duplikaty file_name są dozwolone (przydatne dla augmentacji)

### Anotacje

- Każda anotacja dostaje nowe, unikalne annotation_id (1, 2, 3, ...)
- image_id i category_id są automatycznie mapowane
- Wszystkie pola (bbox, area, segmentation) są zachowane

## Walidacja

Skrypt automatycznie waliduje merged dataset:

1. **Wymagane pola**: info, images, annotations, categories
2. **Duplikaty ID**: Sprawdza czy image_id, annotation_id, category_id są unikalne
3. **Referencje**: Sprawdza czy wszystkie image_id i category_id w anotacjach istnieją
4. **Raport błędów**: Wyświetla max 10 pierwszych błędów

Wyłącz walidację dla szybszego merge'u (NIE ZALECANE):

```bash
python scripts/merge_annotations.py ... --no-validate
```

## Integracja z workflow

### Typowy workflow syntetycznych danych

```bash
# 1. Generuj raw dataset
python scripts/synthetic/batch_generate.py --num-schematics 50

# 2. Konwertuj do COCO
python scripts/synthetic/emit_annotations.py \
  --input-dir data/synthetic/annotations \
  --output data/synthetic/coco_raw.json

# 3. Augmentacja
python scripts/synthetic/augment_dataset.py \
  --input-dir data/synthetic/images_raw \
  --output-dir data/synthetic/images_augmented \
  --profile scan

# 4. Merge raw + augmented
python scripts/merge_annotations.py \
  --inputs data/synthetic/coco_raw.json data/synthetic/images_augmented/annotations.json \
  --output data/synthetic/coco_merged.json \
  --auto-map-categories

# 5. Split na train/val/test
python scripts/split_dataset.py \
  --input data/synthetic/coco_merged.json \
  --output-dir data/synthetic/splits
```

### Dodawanie danych z Label Studio

```bash
# 1. Export z Label Studio (format: COCO)
# Zapisz jako: data/labelstudio/export_coco.json

# 2. Merge z syntetycznymi
python scripts/merge_annotations.py \
  --inputs data/synthetic/coco_merged.json data/labelstudio/export_coco.json \
  --output data/merged/full_dataset.json \
  --auto-map-categories

# 3. Split
python scripts/split_dataset.py \
  --input data/merged/full_dataset.json \
  --output-dir data/merged/splits
```

## Problemy i rozwiązania

### Problem 1: Duplikaty file_name

**Objawy**: Ostrzeżenia "Duplikat file_name 'X.png'"

**Przyczyny**:
- Augmentowane obrazy z tą samą nazwą pliku
- Export z Label Studio używa oryginalnych nazw

**Rozwiązania**:
1. Ignoruj jeśli to augmentacja (OK - te same obrazy)
2. Przemianuj pliki przed merge'em (jeśli konflikt):
   ```bash
   # Dodaj prefix do augmentowanych
   Get-ChildItem data/synthetic/images_augmented/*.png | Rename-Item -NewName { "aug_" + $_.Name }
   ```

### Problem 2: Konflikt kategorii

**Objawy**: Różne kategorie o tej samej nazwie ale innych atrybutach

**Rozwiązanie**: Użyj `--auto-map-categories` (scala po nazwie) lub ręcznie popraw nazwy przed merge'em

### Problem 3: Brakujące referencje po merge'u

**Objawy**: Błędy walidacji "referencja do nieistniejącego image_id"

**Przyczyny**: Źle sformatowany input COCO (brakujące obrazy, złe ID)

**Rozwiązanie**: Waliduj input przed merge'em:
```bash
python scripts/validate_annotations.py --input file1.json
python scripts/validate_annotations.py --input file2.json
```

### Problem 4: Zbyt wiele ostrzeżeń o duplikatach

**Objawy**: Dziesiątki/setki ostrzeżeń o duplikatach file_name

**Rozwiązanie**: To normalne przy merge'u augmentacji - można zignorować lub przekierować ostrzeżenia:
```bash
python scripts/merge_annotations.py ... 2> warnings.log
```

## Następne kroki

- [ ] Dodanie opcji `--rename-duplicates` (automatyczne przemianowywanie file_name)
- [ ] Eksport raportu merge'u do JSON
- [ ] Wizualizacja rozkładu kategorii (matplotlib)
- [ ] Obsługa innych formatów (YOLO, Pascal VOC)

## Historia zmian

### 2025-11-14
- ✅ Pierwsza wersja skryptu
- ✅ Test na 100 obrazach (raw + augmented)
- ✅ Dokumentacja w języku polskim
- ✅ Auto-mapowanie kategorii
- ✅ Walidacja merged datasetu
