# Quick Start: Nowy Workflow Anotacji (Rotated Rectangles + Polygons)

## 📋 Przygotowanie (jednorazowo)

### 1. Zainstaluj zależności
```bash
pip install Pillow  # Do odczytu wymiarów obrazów
```

### 2. Zaktualizuj Label Studio template
1. Otwórz Label Studio: http://localhost:8080
2. Settings → Labeling Interface
3. Usuń stary template
4. Wklej nowy z: `data/annotations/labelstudio_templates/schematic_hybrid_template.xml`
5. Save

**Nowy template wspiera:**
- ✅ Rotated Rectangles (główne narzędzie, hotkeys 1-0,q,w)
- ✅ Polygons (edge cases, hotkeys Shift+1-0,q,w)
- ✅ Quality flags (clean/noisy/partial/uncertain)
- ✅ Notes field

---

## 🎨 Workflow Anotacji

### Krok 1: Zacznij od Rotated Rectangle (80-90% przypadków)

```
1. Naciśnij hotkey klasy (np. "1" dla resistor)
2. Narysuj prostokąt wokół symbolu
3. Jeśli symbol jest obrócony:
   - Użyj okrągłego uchwytu do rotacji
   - Dopasuj kąt do orientacji symbolu
4. Doprecyzuj rozmiar (tight box!)
5. Gotowe! ✅
```

**Przykład:**
```
Rezystor poziomy:  [1] → rysuj prostokąt → 0° rotation
Rezystor pionowy:  [1] → rysuj prostokąt → 90° rotation
Rezystor skośny:   [1] → rysuj prostokąt → 45° rotation
```

---

### Krok 2: Użyj Polygon tylko gdy MUSISZ (10-20% przypadków)

**Kiedy?**
- ✅ Tekst nachodzi na symbol (nie do uniknięcia)
- ✅ Symbol częściowo widoczny (przy krawędzi)
- ✅ Nieregularny kształt (uszkodzony schemat)
- ✅ Bardzo gęsty fragment (symbole bardzo blisko)

**Jak?**
```
1. Naciśnij Shift+hotkey (np. "Shift+1" dla resistor polygon)
2. Klikaj punkty wokół konturu symbolu (4-8 punktów)
3. Podwójne kliknięcie = zamknij polygon
4. Dodaj quality flag: "noisy" lub "partial"
5. Opcjonalnie: dodaj notatkę dlaczego użyłeś polygon
```

---

## 📤 Export i Konwersja

### Krok 3: Export z Label Studio

```bash
# W Label Studio:
1. Export → JSON
2. Zapisz jako: data/annotations/labelstudio_exports/2025-11-06_1800.json
```

---

### Krok 4: Konwersja do COCO

```bash
# Konwertuj do COCO instance segmentation:
python scripts/export_labelstudio_to_coco_seg.py \
    --input data/annotations/labelstudio_exports/2025-11-06_1800.json \
    --output data/annotations/coco_seg/train.json \
    --images-dir data/images
```

**Co robi skrypt:**
- ✅ Rotated rectangles → 4-corner polygons (z zachowaniem kąta w metadata)
- ✅ Polygons → kopiowane bez zmian
- ✅ Unified COCO segmentation format
- ✅ Walidacja wymiarów obrazów
- ✅ Statystyki per-class

**Przykładowy output:**
```
📖 Reading Label Studio export: ...
📦 Found 50 tasks
============================================================
✅ Conversion complete!
📊 Summary:
   Images:      50
   Annotations: 847
   Categories:  12
💾 Saved to: data/annotations/coco_seg/train.json
============================================================

📈 Annotations per class:
   resistor            : 234
   capacitor           : 189
   op_amp              :  67
   ...
```

---

### Krok 5: Walidacja (opcjonalnie)

```bash
# Sprawdź czy COCO JSON jest poprawny:
python scripts/validate_annotations.py \
    data/annotations/coco_seg/train.json
```

---

## 🎯 Najlepsze Praktyki

### ✅ DO:
- **Używaj rectangle gdzie tylko możliwe** (80-90%)
- **Rotuj rectangle** aby uniknąć overlappingu z tekstem
- **Tight boxes** - minimalna pusta przestrzeń
- **Polygon tylko gdy MUSISZ** (rectangle nie działa mimo rotacji)
- **4-8 punktów** dla polygonów (więcej = wolniejsze)
- **Quality flags** dla trudnych przypadków

### ❌ NIE:
- Nie używaj polygonów "dla pewności" - rectangle wystarczy!
- Nie zahaczaj o tekst etykiet (R1, C2, etc.)
- Nie zahaczaj o linie połączeń
- Nie rób overlappingu między symbolami
- Nie używaj >10 punktów dla polygonów

---

## 📊 Statystyki do śledzenia

Po każdych 100 annotacjach sprawdź:

```python
# Idealny rozkład:
{
    "rectangles": "80-90%",  # Większość
    "polygons": "10-20%",    # Edge cases
    "quality_clean": ">80%",
    "avg_time_per_annotation": "15-20s"
}

# Jeśli widzisz:
# - <70% rectangles → Przesadzasz z polygonami!
# - >95% rectangles → Może pomijasz trudne przypadki?
# - <50% clean → Obrazy niskiej jakości?
```

---

## 🆘 Troubleshooting

### Problem: "Nie widzę opcji rotation"
**Rozwiązanie**: Sprawdź czy template ma `canRotate="true"`:
```xml
<RectangleLabels name="rect_label" toName="image" canRotate="true">
```

### Problem: "Polygon nie zamyka się"
**Rozwiązanie**: Podwójne kliknięcie LUB kliknij pierwszy punkt ponownie

### Problem: "Skrypt konwersji daje błąd: Missing width/height"
**Rozwiązanie**: Upewnij się że `--images-dir` wskazuje na folder z obrazami
```bash
python scripts/export_labelstudio_to_coco_seg.py \
    --images-dir data/images  # ← Ważne!
```

### Problem: "Unknown class 'measurement'"
**Rozwiązanie**: Zaktualizuj class_mapping w `data/annotations/class_mapping.json`:
```json
{
  "resistor": 1,
  "capacitor": 2,
  ...
  "measurement_point": 11,  // ← Dodaj brakujące
  "misc_symbol": 12
}
```

---

## 📚 Więcej Informacji

- **Pełna strategia**: `docs/ROTATED_BBOX_STRATEGY.md`
- **Decision tree**: `docs/ANNOTATION_DECISION_TREE.md`
- **Dlaczego mieszać formaty działa**: `docs/MYTH_BUSTING_MIXED_FORMATS.md`
- **Wizualizacja pipeline**: `docs/VISUALIZATION_ANNOTATION_PIPELINE.md`

---

## 🚀 Przykładowa sesja

```bash
# 1. Start Label Studio (jeśli nie działa)
label-studio start

# 2. Zaannotuj 50 obrazów (mix rectangles + polygons)
#    → Export do: data/annotations/labelstudio_exports/batch_001.json

# 3. Konwertuj do COCO
python scripts/export_labelstudio_to_coco_seg.py \
    -i data/annotations/labelstudio_exports/batch_001.json \
    -o data/annotations/coco_seg/train_batch_001.json \
    --images-dir data/images

# 4. Sprawdź statystyki
python scripts/validate_annotations.py \
    data/annotations/coco_seg/train_batch_001.json

# 5. (Później) Połącz wszystkie batche
python scripts/merge_coco_datasets.py \
    data/annotations/coco_seg/train_batch_*.json \
    -o data/annotations/train.json

# 6. Trenuj model!
yolo segment train \
    model=yolov8n-seg.pt \
    data=data/yolov8_seg.yaml \
    epochs=100 \
    imgsz=1024
```

---

**Gotowy do rozpoczęcia? Let's go! 🎉**

**Pamiętaj**: Rectangle (80%) + Polygon (20%) = Optimal workflow! 🎯
