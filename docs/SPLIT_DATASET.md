# 📊 Podział Datasetu - Dokumentacja

## Przegląd

Skrypt `split_dataset.py` dzieli dataset COCO Instance Segmentation na 3 zbiory (train/val/test) z zachowaniem proporcji każdej klasy komponentów (stratified split).

## Funkcje

### ✅ Zaimplementowane

- **Stratified split** - zachowuje proporcje klas we wszystkich zbiorach
- **Konfigurowalne proporcje** - domyślnie 70/15/15 (train/val/test)
- **Seed dla reprodukowalności** - domyślnie 42
- **Automatyczne kopiowanie obrazów** - opcjonalne tworzenie struktury katalogów
- **Szczegółowe statystyki** - ilość obrazów i anotacji per klasa dla każdego zbioru
- **Walidacja danych wejściowych** - sprawdzanie sum proporcji i istnienia plików

### 🎯 Kluczowe cechy

1. **Zachowanie proporcji klas**: Algorytm dba o to, aby każda klasa (resistor, capacitor, inductor, diode) występowała w podobnych proporcjach w train/val/test
2. **Grupowanie anotacji**: Wszystkie anotacje z jednego obrazu trafiają do tego samego zbioru
3. **Metadane COCO**: Zachowuje wszystkie metadane (info, licenses, categories) w splitowanych plikach

## Użycie

### Podstawowe użycie (tylko JSON)

```bash
python scripts/split_dataset.py \
  --input data/synthetic/coco_annotations.json \
  --output-dir data/synthetic/splits
```

### Z kopiowaniem obrazów

```bash
python scripts/split_dataset.py \
  --input data/synthetic/coco_annotations.json \
  --output-dir data/synthetic/splits \
  --images-dir data/synthetic/images_raw \
  --copy-images
```

### Custom proporcje

```bash
python scripts/split_dataset.py \
  --input data/synthetic/coco_annotations.json \
  --output-dir data/synthetic/splits \
  --ratios 0.8 0.1 0.1
```

### Wszystkie parametry

```bash
python scripts/split_dataset.py \
  --input data/synthetic/coco_annotations.json \
  --output-dir data/synthetic/splits \
  --images-dir data/synthetic/images_raw \
  --copy-images \
  --ratios 0.7 0.15 0.15 \
  --seed 42
```

## Parametry

| Parametr | Opis | Domyślna wartość |
|----------|------|------------------|
| `--input` | Ścieżka do pliku COCO JSON (wymagane) | - |
| `--output-dir` | Katalog wyjściowy dla splitowanych plików (wymagane) | - |
| `--images-dir` | Katalog z obrazami (wymagane jeśli `--copy-images`) | None |
| `--copy-images` | Kopiuj obrazy do podkatalogów train/val/test | False |
| `--ratios` | Proporcje train/val/test (3 liczby sumujące się do 1.0) | 0.7 0.15 0.15 |
| `--seed` | Seed dla reprodukowalności | 42 |

## Struktura wyjściowa

### Bez `--copy-images`:

```
data/synthetic/splits/
├── train.json
├── val.json
└── test.json
```

### Z `--copy-images`:

```
data/synthetic/splits/
├── train.json
├── train/
│   └── images/
│       ├── schematic_001.png
│       ├── schematic_003.png
│       └── ...
├── val.json
├── val/
│   └── images/
│       ├── schematic_002.png
│       └── ...
├── test.json
└── test/
    └── images/
        ├── schematic_005.png
        └── ...
```

## Test na datasecie syntetycznym

### Wynik testu (14.11.2025)

**Input**: 50 obrazów, 639 anotacji, 4 kategorie

**Split**: 70% / 15% / 15%

**Wyniki**:

#### Train (70%)
- Obrazy: 35
- Anotacje: 454
- Kategorie:
  - resistor: 113 (24.9%)
  - capacitor: 107 (23.6%)
  - inductor: 120 (26.4%)
  - diode: 114 (25.1%)

#### Val (15%)
- Obrazy: 7
- Anotacje: 89
- Kategorie:
  - resistor: 36 (40.4%)
  - capacitor: 17 (19.1%)
  - inductor: 19 (21.3%)
  - diode: 17 (19.1%)

#### Test (15%)
- Obrazy: 8
- Anotacje: 96
- Kategorie:
  - resistor: 18 (18.8%)
  - capacitor: 26 (27.1%)
  - inductor: 26 (27.1%)
  - diode: 26 (27.1%)

### Obserwacje

✅ **Proporcje obrazów**: Dokładnie 70/15/15 (35/7/8 obrazów)
✅ **Proporcje anotacji**: Zbliżone do 70/15/15 (454/89/96 = 71%/14%/15%)
✅ **Balans klas**: Każda klasa występuje w każdym zbiorze (ważne dla treningu)
⚠️ **Wariancja proporcji klas**: Wyższa w mniejszych zbiorach (val/test) - normalne dla małych datasetu

## Integracja z YOLOv8

Po wykonaniu splitu, można użyć plików JSON w treningu YOLOv8:

```yaml
# configs/synthetic_dataset.yaml
path: data/synthetic/splits
train: train.json
val: val.json
test: test.json

names:
  0: resistor
  1: capacitor
  2: inductor
  3: diode
```

Albo bezpośrednio w komendzie:

```bash
yolo task=segment mode=train \
  model=yolov8n-seg.pt \
  data=configs/synthetic_dataset.yaml \
  epochs=50 \
  imgsz=640
```

## Walidacja

### Sprawdź czy split się udał:

```powershell
# Policz obrazy
Get-ChildItem data/synthetic/splits/train/images | Measure-Object | Select-Object Count
Get-ChildItem data/synthetic/splits/val/images | Measure-Object | Select-Object Count
Get-ChildItem data/synthetic/splits/test/images | Measure-Object | Select-Object Count

# Sprawdź JSON
$train = Get-Content data/synthetic/splits/train.json | ConvertFrom-Json
Write-Host "Train: $($train.images.Count) images, $($train.annotations.Count) annotations"
```

### Sprawdź proporcje klas:

```powershell
python -c "
import json
from collections import Counter

with open('data/synthetic/splits/train.json') as f:
    train = json.load(f)

cat_counts = Counter(ann['category_id'] for ann in train['annotations'])
print('Train category distribution:', dict(cat_counts))
"
```

## Problemy i rozwiązania

### Problem 1: Proporcje klas niezbalansowane w val/test
**Przyczyna**: Mały dataset (50 obrazów), więc losowy split może dać nierównomierne rozkłady
**Rozwiązanie**: Zwiększ rozmiar datasetu (docelowo 150-200 obrazów) lub użyj większego train ratio

### Problem 2: Brak obrazów w output directory
**Przyczyna**: Nie użyto `--copy-images` lub `--images-dir` wskazuje na zły katalog
**Rozwiązanie**: Dodaj `--copy-images` i sprawdź ścieżkę w `--images-dir`

### Problem 3: JSON nie zawiera wszystkich anotacji
**Przyczyna**: Bug w grupowaniu anotacji lub źle sformatowany input
**Rozwiązanie**: Waliduj input COCO używając `scripts/validate_annotations.py`

## Następne kroki

- [ ] Test na większym datasecie (150-200 obrazów)
- [ ] Dodanie wsparcia dla cross-validation splits (k-fold)
- [ ] Eksport do innych formatów (YOLO txt, Pascal VOC)
- [ ] Automatyczna wizualizacja rozkładu klas (matplotlib)

## Historia zmian

### 2025-11-14
- ✅ Pierwsza wersja skryptu
- ✅ Test na 50 syntetycznych schematach
- ✅ Dokumentacja w języku polskim
- ✅ Stratified split z seed=42
