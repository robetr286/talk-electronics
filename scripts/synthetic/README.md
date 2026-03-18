# Synthetic Dataset Generator

Pipeline do generowania syntetycznych schematów elektronicznych z automatycznymi anotacjami COCO.

## Struktura katalogów

```
data/synthetic/
├── images_raw/          # Czyste rendery z KiCad
├── images_augmented/    # Obrazy po augmentacji
├── annotations/         # Pliki COCO JSON
└── metadata.csv         # Parametry generatora
```

## Workflow

### 1. Generowanie schematu

```bash
python scripts/synthetic/generate_schematic.py \
    --output data/synthetic/schematic_001.pdf \
    --metadata data/synthetic/schematic_001.json \
    --seed 42 \
    --components 15 \
    --format pdf
```

**Status**: 🚧 W trakcie implementacji (wymaga KiCad API)

### 2. Eksport do PNG

```bash
python scripts/synthetic/export_png.py \
    --input data/synthetic/schematic_001.pdf \
    --output data/synthetic/images_raw/schematic_001.png \
    --dpi 300
```

**Status**: ✅ Implementacja podstawowa (PyMuPDF)

### 3. Generowanie anotacji COCO

```bash
python scripts/synthetic/emit_annotations.py \
    --metadata data/synthetic/schematic_001.json \
    --image data/synthetic/images_raw/schematic_001.png \
    --output data/synthetic/annotations/raw.json
```

**Status**: ✅ Implementacja podstawowa

### 4. Augmentacja datasetu

```bash
python scripts/synthetic/augment_dataset.py \
    --input data/synthetic/images_raw/ \
    --output data/synthetic/images_augmented/ \
    --annotations data/synthetic/annotations/raw.json \
    --profile scan
```

**Status**: ✅ Implementacja podstawowa (wymaga albumentations)

## Wymagania

### Podstawowe

```bash
pip install PyMuPDF Pillow numpy
```

### Augmentacja

```bash
pip install albumentations
```

### Generowanie (KiCad)

- KiCad 8+ z API Pythona
- Moduły `pcbnew`/`eeschema` w PYTHONPATH

## Kategorie komponentów

| ID | Nazwa | Superkategoria | Symbol |
|----|-------|----------------|--------|
| 1  | resistor | passive | R |
| 2  | capacitor | passive | C |
| 3  | inductor | passive | L |
| 4  | diode | semiconductor | D |
| 5  | transistor | semiconductor | Q |
| 6  | ic | integrated | U |
| 7  | connector | connector | J |
| 8  | node | connection | node |

## Profile augmentacji

- **light**: Drobne artefakty (szum, lekki blur)
- **scan**: Symulacja skanowania (artefakty ISO, rotacja ±5°)
- **heavy**: Maksymalne zróżnicowanie (dropout, silny szum)

Uwagi praktyczne:
- Profile są zdefiniowane w [scripts/synthetic/augment_dataset.py](scripts/synthetic/augment_dataset.py#L74-L152) i korzystają z `albumentations` (noise/blur/rotate/dropout). Domyślnie `scan` daje realistyczne skany z lekką rotacją.
- Jeśli chcesz zmieniać grubość linii już na etapie generowania, w [scripts/synthetic/generate_schematic.py](scripts/synthetic/generate_schematic.py#L105-L154) zmień parametry `width` w rysowaniu lub wprowadź losowanie 1–3 px przed `draw.*`.

## Raport klas (COCO → YOLO)
- Eksport do YOLO wykonywany skryptem [scripts/export_coco_to_yolo_split.py](../export_coco_to_yolo_split.py) zapisuje `class_report.json` (liczba obrazów/anotacji i `class_counts` dla `train`/`val`/`test`). Ostrzega, gdy `val`/`test` są zbyt małe.
- Przykład użycia:
    ```bash
    python scripts/export_coco_to_yolo_split.py \
        --input data/synthetic/coco_annotations.json \
        --output data/yolo_dataset/synthetic_split \
        --search-dirs data/synthetic/images_raw data/synthetic/images_augmented \
        --synthetic-prefix synthetic_
    ```
- Sprawdź `class_report.json` przed treningiem; jeśli brakuje klas w `val`/`test`, dodaj realne anotacje albo zwiększ pulę obrazów.

## TODO

- [ ] Integracja z KiCad API (`generate_schematic.py`)
- [ ] Konwersja SVG → PNG (`export_png.py`)
- [ ] Zaawansowane bounding boxy w zależności od rotacji
- [ ] Batch processing dla wszystkich skryptów
- [ ] Test integracyjny pipeline'u end-to-end
- [ ] CI: generowanie próbki przy każdym commit
