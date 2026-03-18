# ✅ CHECKLIST: Nowy Workflow Anotacji - Rotated Rectangles + Polygons

## 🎯 Co zostało zrobione:

### 📁 Dokumentacja
- ✅ `docs/ROTATED_BBOX_STRATEGY.md` - Pełna strategia z debunkingiem mitów
- ✅ `docs/ANNOTATION_DECISION_TREE.md` - Quick decision guide
- ✅ `docs/MYTH_BUSTING_MIXED_FORMATS.md` - Dlaczego mieszanie formatów jest OK
- ✅ `docs/VISUALIZATION_ANNOTATION_PIPELINE.md` - Wizualne wyjaśnienie
- ✅ `docs/ANNOTATION_WORKFLOW_QUICKSTART.md` - Quick start guide
- ✅ `docs/annotation_tools.md` - Zaktualizowany template Label Studio

### 🛠️ Narzędzia
- ✅ `scripts/export_labelstudio_to_coco_seg.py` - Konwerter LS → COCO segmentation
- ✅ `scripts/test_labelstudio_conversion.py` - Test script do weryfikacji
- ✅ `data/annotations/labelstudio_templates/schematic_hybrid_template.xml` - Nowy template LS
- ✅ `data/annotations/class_mapping.json` - Mapowanie klas

### 📝 Zaktualizowane pliki
- ✅ `README.md` - Dodane linki do nowej dokumentacji
- ✅ `data/annotations/README.md` - Dodane linki do dokumentacji

---

## 🚀 Co musisz teraz zrobić:

### 1. Zaktualizuj Label Studio template (5 minut)

```bash
# 1. Otwórz Label Studio
label-studio start  # Jeśli nie działa

# 2. Przejdź do projektu → Settings → Labeling Interface
# 3. Skopiuj zawartość z:
#    data/annotations/labelstudio_templates/schematic_hybrid_template.xml
# 4. Wklej do Label Studio
# 5. Save
```

**Sprawdź**: Czy widzisz opcję rotacji prostokątów? ✅

---

### 2. Przetestuj workflow (10 minut)

```bash
# Test 1: Uruchom test conversion
python scripts/test_labelstudio_conversion.py

# Powinien wyświetlić:
# ✅ TEST PASSED - Pipeline is working correctly!

# Test 2: Zaannotuj 1-2 obrazy testowe w Label Studio
# - Użyj hotkey "1" dla rectangle (obróć jeśli trzeba)
# - Użyj "Shift+1" dla polygon (jeśli rectangle nie działa)

# Test 3: Export z Label Studio
# → Export → JSON → Zapisz jako: data/annotations/labelstudio_exports/test_001.json

# Test 4: Konwertuj do COCO
python scripts/export_labelstudio_to_coco_seg.py \
    -i data/annotations/labelstudio_exports/test_001.json \
    -o data/annotations/coco_seg/test_001.json \
    --images-dir data/images

# Sprawdź output - powinien pokazać statystyki ✅
```

---

### 3. Rozpocznij produkcyjne anotacje! 🎨

```bash
# Workflow:
1. Zaannotuj 50-100 obrazów (mix rectangles + polygons)
2. Export → JSON → data/annotations/labelstudio_exports/batch_001.json
3. Konwertuj:
   python scripts/export_labelstudio_to_coco_seg.py \
       -i data/annotations/labelstudio_exports/batch_001.json \
       -o data/annotations/coco_seg/train_batch_001.json \
       --images-dir data/images
4. Powtórz dla kolejnych batchy
```

---

## 📊 Śledzenie postępu

Po każdych 100 annotacjach sprawdź statystyki:

```python
# Idealny rozkład:
{
    "rectangles": "80-90%",      # ✅ Większość
    "polygons": "10-20%",        # ✅ Edge cases
    "quality_clean": ">80%",     # ✅ Czyste annotacje
    "avg_time": "15-20s/obiekt"  # ✅ Szybko
}
```

**Jeśli nie zgadza się:**
- <70% rectangles → Za dużo polygonów! Używaj rectangles gdzie możliwe
- >95% rectangles → Może pomijasz trudne przypadki?
- <50% clean → Obrazy niskiej jakości?
- >30s/obiekt → Może za wolno? Użyj hotkeyów!

---

## 🎓 Kluczowe zasady (przypomnienie)

### ✅ Używaj Rectangle gdy:
- Symbol jest prostokątny/box-like
- Da się obrócić aby uniknąć overlappingu
- Tight box jest możliwy

### ✅ Używaj Polygon gdy:
- Tekst nachodzi NA symbol (nie do uniknięcia)
- Symbol częściowo widoczny (przy krawędzi)
- Nieregularny kształt (uszkodzony schemat)
- Bardzo gęsty fragment (symbole bardzo blisko)

### ❌ NIE:
- Nie używaj polygonów "dla pewności"
- Nie zahaczaj o tekst etykiet
- Nie rób overlappingu między symbolami

---

## 🆘 Problemy?

### Problem: "Conversion script nie działa"
```bash
# Sprawdź czy masz wszystkie zależności:
pip install Pillow

# Sprawdź czy images-dir jest poprawny:
python scripts/export_labelstudio_to_coco_seg.py \
    --images-dir data/images  # ← Musi wskazywać na folder z obrazami
```

### Problem: "Unknown class 'xyz'"
```bash
# Dodaj klasę do class_mapping.json:
{
  "resistor": 1,
  ...
  "xyz": 13  # ← Dodaj nową klasę
}
```

### Problem: "Label Studio nie ma rotation"
```bash
# Sprawdź template - musi mieć:
<RectangleLabels name="rect_label" toName="image" canRotate="true">
#                                                   ^^^^^^^^^^^^ ← Ważne!
```

---

## 📚 Dokumentacja

| Dokument | Opis | Kiedy czytać |
|----------|------|--------------|
| `ANNOTATION_WORKFLOW_QUICKSTART.md` | Quick start | **NAJPIERW** |
| `ANNOTATION_DECISION_TREE.md` | Rectangle vs Polygon | Podczas anotacji |
| `ROTATED_BBOX_STRATEGY.md` | Pełna strategia | Dla szczegółów |
| `MYTH_BUSTING_MIXED_FORMATS.md` | Dlaczego mieszać formaty | Jeśli masz wątpliwości |
| `VISUALIZATION_ANNOTATION_PIPELINE.md` | Jak działa pipeline | Dla ciekawskich |

---

## 🎉 Gotowe!

Masz teraz:
- ✅ Zaktualizowany template Label Studio (rotated rectangles + polygons)
- ✅ Skrypt konwersji do COCO segmentation
- ✅ Kompletną dokumentację
- ✅ Test script do weryfikacji
- ✅ Odpowiedzi na mity Gemini

**Next step**: Zaktualizuj template w Label Studio i rozpocznij anotacje! 🚀

**Pamiętaj**: Rectangle (80%) + Polygon (20%) = Perfect balance! 🎯
