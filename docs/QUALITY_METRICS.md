# 📊 Quality Metrics - Analiza Jakości Anotacji

## Przegląd

Skrypt `quality_metrics.py` analizuje jakość datasetu COCO i generuje szczegółowy raport z statystykami, wykrywaniem outliers i wizualizacjami rozkładów.

## Funkcje

### ✅ Zaimplementowane

- **Statystyki per kategoria** - liczność, rozmiar bbox, aspect ratio, wymiary
- **Wykrywanie outliers** - z-score dla obszaru bbox (konfigurowalne)
- **Heatmap pokrycia** - wizualizacja rozmieszczenia anotacji na obrazach
- **Wizualizacje matplotlib** - wykresy słupkowe, boxploty, heatmapy
- **Export do JSON** - kompletny raport z wszystkimi metrykami
- **Statystyki opisowe** - mean, std, min, max, median, quartiles

### 🎯 Kluczowe metryki

1. **Liczność kategorii**: Ile razy każda klasa występuje w datasecie
2. **Obszar bbox**: Rozkład obszarów (px²) per kategoria
3. **Aspect ratio**: Proporcje width/height per kategoria
4. **Wymiary**: Średnie rozmiary bbox (width × height)
5. **Outliers**: Anotacje z nietypowymi metrykami (z-score > 3.0)
6. **Pokrycie**: Heatmap pokazująca gdzie na obrazach są anotacje

## Użycie

### Podstawowa analiza (tylko JSON)

```bash
python scripts/quality_metrics.py \
  --input data/synthetic/coco_annotations.json \
  --output reports/quality_report.json
```

### Z wizualizacjami

```bash
python scripts/quality_metrics.py \
  --input data/synthetic/coco_merged.json \
  --output reports/quality_merged.json \
  --visualize \
  --output-dir reports/visualizations
```

### Bez outliers (szybsze dla dużych datasetów)

```bash
python scripts/quality_metrics.py \
  --input data/large_dataset.json \
  --output reports/quality.json \
  --no-outliers
```

### Custom próg outliers

```bash
python scripts/quality_metrics.py \
  --input data.json \
  --output report.json \
  --outlier-threshold 2.5
```

## Parametry

| Parametr | Opis | Domyślna wartość |
|----------|------|------------------|
| `--input` | Ścieżka do pliku COCO JSON (wymagane) | - |
| `--output` | Ścieżka do raportu JSON (wymagane) | - |
| `--visualize` | Generuj wizualizacje matplotlib | False |
| `--output-dir` | Katalog dla wizualizacji | reports/visualizations |
| `--no-outliers` | Pomiń wykrywanie outliers (szybsze) | False |
| `--outlier-threshold` | Próg z-score dla outliers | 3.0 |

## Struktura raportu JSON

```json
{
  "metadata": {
    "date_generated": "2025-11-14T...",
    "input_file": "data/synthetic/coco_merged.json",
    "total_images": 100,
    "total_annotations": 1278,
    "total_categories": 4
  },
  "category_statistics": {
    "resistor": {
      "count": 334,
      "percentage": 26.1,
      "bbox_area": {
        "mean": 1256.4,
        "std": 99.0,
        "min": 1200.0,
        "max": 1542.0,
        "median": 1200.0,
        "q25": 1200.0,
        "q75": 1200.0
      },
      "aspect_ratio": {
        "mean": 1.58,
        "std": 1.28,
        ...
      },
      "width": { ... },
      "height": { ... }
    },
    ...
  },
  "outliers": {
    "count": 7,
    "annotations": [
      {
        "annotation_id": 1238,
        "image_id": 88,
        "category_id": 3,
        "category_name": "inductor",
        "bbox": [x, y, w, h],
        "area": 1542.0,
        "aspect_ratio": 3.0,
        "reason": "area_outlier",
        "z_score": 3.20
      },
      ...
    ]
  },
  "coverage_heatmap": {
    "grid_size": [10, 10],
    "max_density": 34.0
  }
}
```

## Test na datasecie merged

### Wynik testu (14.11.2025)

**Input**: `coco_merged.json` - 100 obrazów, 1278 anotacji, 4 kategorie

**Statystyki per kategoria**:

#### Resistor (26.1%)
- Liczność: 334 anotacji
- Obszar bbox: 1256.4 ± 99.0 px² (min: 1200, max: 1542)
- Aspect ratio: 1.58 ± 1.28 (min: 0.33, max: 3.0)
- Wymiary: 39.9 × 41.2 px (±19.8 × 19.7)

#### Capacitor (23.5%)
- Liczność: 300 anotacji
- Obszar bbox: 825.6 ± 47.9 px² (min: 800, max: 971)
- Aspect ratio: 1.29 ± 0.73 (min: 0.5, max: 2.0)
- Wymiary: 31.0 × 29.7 px (±9.8 × 9.9)

#### Inductor (25.8%)
- Liczność: 330 anotacji
- Obszar bbox: 1248.0 ± 91.8 px² (min: 1200, max: 1542)
- Aspect ratio: 1.63 ± 1.29 (min: 0.33, max: 3.0)
- Wymiary: 40.4 × 40.6 px (±19.7 × 19.8)

#### Diode (24.6%)
- Liczność: 314 anotacji
- Obszar bbox: 1643.3 ± 78.6 px² (min: 1600, max: 1873.6)
- Aspect ratio: 1.00 ± 0.00 (zawsze kwadratowe)
- Wymiary: 40.5 × 40.5 px (±1.0 × 1.0)

**Outliers wykryte**: 7 anotacji
- Top outlier: inductor z area=1542 px² (z-score=3.20)
- Głównie induktory i kondensatory z dużymi obszarami

**Pokrycie**:
- Grid 10×10
- Max density: 34 anotacje/komórka
- Rozkład równomierny (syntetyczne dane)

## Wygenerowane wizualizacje

### 1. `category_counts.png` - Rozkład liczności kategorii
- Bar chart pokazujący ile razy każda kategoria występuje
- Pomaga zidentyfikować niezbalansowanie klas

### 2. `bbox_areas_boxplot.png` - Rozkład obszarów bbox
- Box plot dla każdej kategorii
- Pokazuje median, quartiles, outliers
- Identyfikuje kategorie z dużą wariancją rozmiarów

### 3. `aspect_ratios_boxplot.png` - Rozkład aspect ratio
- Box plot proporcji width/height
- Linia referencyjna 1:1 (kwadrat)
- Pomaga zrozumieć typowe kształty komponentów

### 4. `coverage_heatmap.png` - Heatmap pokrycia
- Pokazuje gdzie na obrazach są środki bbox
- Grid 10×10 z liczbą anotacji per komórka
- Identyfikuje obszary z brakiem anotacji (potencjalne problemy)

## Obserwacje z testu

### ✅ Pozytywne
- **Balans klas**: Wszystkie kategorie mają podobną liczność (23-26%)
- **Konsystencja diod**: Zawsze kwadratowe (aspect ratio = 1.0)
- **Równomierne pokrycie**: Heatmap pokazuje równomierny rozkład (syntetyczne dane)

### ⚠️ Do uwagi
- **Wariancja aspect ratio**: Rezystory i induktory mają wysoką wariancję (±1.28-1.29)
  - To OK dla schematów (różne orientacje)
- **7 outliers**: Głównie induktory i kondensatory z większymi obszarami
  - Z-score ~3.0, więc nie są ekstremalne
  - Prawdopodobnie rotowane komponenty

### 🔍 Rekomendacje
1. **Zwiększ dataset**: 100 obrazów to mało, cel: 150-200+
2. **Dodaj realne dane**: Merge z Label Studio (realne schematy)
3. **Monitoruj outliers**: Po merge'u sprawdź czy outliers nie są błędami anotacji

## Integracja z workflow

### Typowy workflow z quality metrics

```bash
# 1. Generuj syntetyczne dane
python scripts/synthetic/batch_generate.py --num-schematics 50

# 2. Konwertuj do COCO
python scripts/synthetic/emit_annotations.py \
  --input-dir data/synthetic/annotations \
  --output data/synthetic/coco_raw.json

# 3. Pierwsza analiza jakości (raw)
python scripts/quality_metrics.py \
  --input data/synthetic/coco_raw.json \
  --output reports/quality_raw.json \
  --visualize

# 4. Augmentacja
python scripts/synthetic/augment_dataset.py ...

# 5. Merge raw + augmented
python scripts/merge_annotations.py \
  --inputs data/synthetic/coco_raw.json data/synthetic/images_augmented/annotations.json \
  --output data/synthetic/coco_merged.json

# 6. Druga analiza jakości (merged)
python scripts/quality_metrics.py \
  --input data/synthetic/coco_merged.json \
  --output reports/quality_merged.json \
  --visualize \
  --output-dir reports/visualizations_merged

# 7. Porównaj raporty (manual check)
```

### Przed treningiem

```bash
# Analiza jakości przed split
python scripts/quality_metrics.py \
  --input data/full_dataset.json \
  --output reports/quality_pre_split.json \
  --visualize

# Split
python scripts/split_dataset.py \
  --input data/full_dataset.json \
  --output-dir data/splits

# Analiza per split
python scripts/quality_metrics.py --input data/splits/train.json --output reports/quality_train.json
python scripts/quality_metrics.py --input data/splits/val.json --output reports/quality_val.json
python scripts/quality_metrics.py --input data/splits/test.json --output reports/quality_test.json
```

## Interpretacja metryk

### Obszar bbox (area)
- **Niski**: Małe komponenty, trudne do wykrycia
- **Wysoki**: Duże komponenty, łatwe do wykrycia
- **Duża wariancja**: Różne rozmiary, potrzebna augmentacja scale

### Aspect ratio
- **~1.0**: Kwadratowe komponenty (diody, IC)
- **>2.0**: Wydłużone komponenty (rezystory poziome, linie)
- **Duża wariancja**: Różne orientacje (dobre dla rotacji)

### Outliers
- **Area outliers**: Zbyt małe/duże bbox → sprawdź czy nie błąd anotacji
- **High z-score (>4.0)**: Prawdopodobnie błąd, manualnie sprawdź
- **Moderate z-score (3.0-4.0)**: Nietypowe ale prawdopodobnie OK

### Pokrycie (heatmap)
- **Równomierne**: Dobre, model zobaczy różne konteksty
- **Skupione w centrum**: Typowe dla schematów, ale może być bias
- **Puste obszary**: Brak anotacji w rogach → dodaj więcej danych

## Problemy i rozwiązania

### Problem 1: Zbyt wiele outliers (>10% datasetu)

**Przyczyny**:
- Błędne anotacje (zbyt małe/duże bbox)
- Niepełny dataset (brak przykładów pośrednich rozmiarów)

**Rozwiązania**:
1. Manualnie sprawdź top 10 outliers
2. Popraw błędne anotacje w Label Studio
3. Dodaj więcej przykładów w brakującym przedziale rozmiarów

### Problem 2: Niezbalansowane klasy (>40% dla jednej klasy)

**Przyczyny**:
- Oversampling jednej klasy w syntetycznych danych
- Naturalne niezbalansowanie w realnych schematach

**Rozwiązania**:
1. Zmień proporcje w batch_generate.py
2. Użyj class weights w treningu YOLOv8
3. Augmentuj mniej liczbne klasy

### Problem 3: Puste obszary w heatmap

**Przyczyny**:
- Komponenty zawsze w centrum
- Brak anotacji w rogach obrazów

**Rozwiązania**:
1. Dodaj padding/crop augmentację
2. Wygeneruj schematy z różnym rozmieszczeniem
3. Użyj RandomCrop w treningu

## Wymagane pakiety

```bash
pip install matplotlib numpy
```

Lub dodaj do `requirements.txt`:
```
matplotlib>=3.7.0
numpy>=1.24.0
```

## Następne kroki

- [ ] Eksport heatmap do numpy array (analiza programistyczna)
- [ ] Dodanie wizualizacji per-image (sample z bbox overlay)
- [ ] Porównanie dwóch raportów (diff metrics)
- [ ] Integration z CI/CD (automatyczna walidacja przed treningiem)

## Historia zmian

### 2025-11-14
- ✅ Pierwsza wersja skryptu
- ✅ Test na 100 obrazach (merged dataset)
- ✅ 4 typy wizualizacji
- ✅ Wykrywanie outliers z z-score
- ✅ Dokumentacja w języku polskim
