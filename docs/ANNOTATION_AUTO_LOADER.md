# Automatyczny Loader Anotacji z Detekcją Rotacji

## 📋 Przegląd

System automatycznie wykrywa i konwertuje **rotated rectangles** (obrócone prostokąty) z Label Studio do standardowego formatu **COCO instance segmentation**.

**Użytkownik NIE musi martwić się konwersją** - wszystko dzieje się automatycznie! 🎉

---

## 🎯 Jak to działa

```
Krok 1: Eksport z Label Studio
    ↓
Krok 2: Aplikacja automatycznie wykrywa format
    ↓
Krok 3: Jeśli wykryto rotated rectangles → KONWERSJA
    ↓
Krok 4: Użytkownik dostaje standardowy COCO format
```

---

## 🔧 Użycie w Aplikacji

### Backend (Python)

```python
from talk_electronic.services.annotation_loader import load_annotations

# Automatyczna konwersja!
coco_data = load_annotations(Path("data/annotations/exported.json"))

# Gotowe do użycia z YOLOv8-seg
# annotations mają pole 'segmentation' jako wielokąty
```

### Frontend (JavaScript)

```javascript
import { loadAnnotations } from './static/js/symbolDetection.js';

// Załaduj anotacje z automatyczną konwersją
const cocoData = await loadAnnotations('data/annotations/labelstudio_export.json');

// Użytkownik zobaczy powiadomienie:
// "✅ Automatycznie przekonwertowano 42 rotated rectangles do formatu segmentacji"
```

### REST API

**Endpoint**: `POST /api/symbols/load-annotations`

**Request**:
```json
{
  "annotationFile": "labelstudio_exports/project_1.json",
  "validate": true
}
```

**Response (z konwersją)**:
```json
{
  "success": true,
  "data": {
    "images": [...],
    "annotations": [
      {
        "id": 1,
        "image_id": 1,
        "category_id": 1,
        "bbox": [100, 100, 50, 30],
        "segmentation": [[75, 85, 125, 85, 125, 115, 75, 115]],  // ← Automatycznie przekonwertowane!
        "area": 1500
      }
    ],
    "categories": [...]
  },
  "info": {
    "format": "label_studio",
    "conversionPerformed": true,
    "rotatedCount": 42,
    "totalAnnotations": 100,
    "message": "✅ Automatycznie przekonwertowano 42 rotated rectangles do formatu segmentacji",
    "filePath": "c:/Users/.../data/annotations/labelstudio_exports/project_1.json"
  }
}
```

**Response (bez konwersji - już w COCO)**:
```json
{
  "success": true,
  "data": {...},
  "info": {
    "format": "coco_standard",
    "conversionPerformed": false,
    "rotatedCount": 0,
    "totalAnnotations": 100,
    "message": "✅ Anotacje już w standardowym formacie COCO"
  }
}
```

---

## 📊 Obsługiwane Formaty Wejściowe

### 1. Label Studio (z rotacją)

```json
{
  "annotations": [
    {
      "id": 1,
      "image_id": 1,
      "category_id": 1,
      "bbox": [100, 100, 50, 30],
      "rotation": 45.0,  // ← Pole rotation
      "area": 1500
    }
  ]
}
```

**Konwersja**: `rotation` + `bbox` → `segmentation` (4-punktowy wielokąt)

### 2. YOLOv8-OBB (oriented bounding box)

```json
{
  "annotations": [
    {
      "id": 1,
      "image_id": 1,
      "category_id": 1,
      "bbox": [125, 115, 50, 30, 45.0],  // ← [x_center, y_center, w, h, angle]
      "area": 1500
    }
  ]
}
```

**Konwersja**: 5-elementowy `bbox` → standardowy `bbox` + `segmentation`

### 3. COCO Standard (bez rotacji)

```json
{
  "annotations": [
    {
      "id": 1,
      "image_id": 1,
      "category_id": 1,
      "bbox": [100, 100, 50, 30],
      "segmentation": [[100, 100, 150, 100, 150, 130, 100, 130]],  // ← Już jest
      "area": 1500
    }
  ]
}
```

**Konwersja**: BRAK - pozostaje bez zmian ✅

---

## 🎨 Powiadomienia dla Użytkownika

### W Konsoli (Backend)

```
INFO: Ładowanie anotacji z: data/annotations/exported.json
WARNING: ⚠️  Wykryto 42 anotacji z rotacją (format: label_studio) - uruchamiam automatyczną konwersję...
DEBUG: Konwersja Label Studio: bbox=[100, 100, 50, 30], angle=45.0°
INFO: ✅ Konwersja zakończona pomyślnie: 42 prostokątów → wielokąty segmentacji
```

### W UI (Frontend)

**Toast Notification**:
```
🔄 Automatycznie przekonwertowano 42 rotated rectangles do formatu segmentacji
```

**Typ powiadomienia**:
- 🟢 **Zielony** (success): Anotacje już w COCO, brak konwersji
- 🟡 **Żółty** (warning): Wykonano konwersję (wszystko OK, ale było coś do zrobienia)
- 🔴 **Czerwony** (error): Błąd ładowania/konwersji

---

## 🔬 Matematyka Konwersji

### Rotated Rectangle → 4-punktowy Wielokąt

Dane wejściowe:
- `(x, y)` - centrum prostokąta
- `(w, h)` - szerokość i wysokość
- `angle` - kąt obrotu w stopniach

Algorytm:
```python
angle_rad = math.radians(angle)
cos_a = math.cos(angle_rad)
sin_a = math.sin(angle_rad)

# 4 rogi względem centrum (przed rotacją)
corners = [
    (-w/2, -h/2),  # lewy górny
    (w/2, -h/2),   # prawy górny
    (w/2, h/2),    # prawy dolny
    (-w/2, h/2)    # lewy dolny
]

# Obróć każdy róg i przesuń do pozycji globalnej
for (cx, cy) in corners:
    rx = x + cx * cos_a - cy * sin_a
    ry = y + cx * sin_a + cy * cos_a
    points.extend([rx, ry])

# Wynik: [x1, y1, x2, y2, x3, y3, x4, y4]
```

**Przykład**:
- Wejście: `bbox=[100, 100, 50, 30], rotation=45°`
- Wyjście: `segmentation=[[75.5, 85.7, 124.5, 85.7, 139.3, 114.3, 90.7, 114.3]]`

---

## ✅ Walidacja Formatu

System automatycznie waliduje czy:
- Anotacje mają wymagane pola: `id`, `image_id`, `category_id`
- Każda anotacja ma `segmentation` LUB `bbox`
- `segmentation` jest listą list: `[[x1,y1,x2,y2,...]]`
- Wielokąty mają co najmniej 3 punkty (6 wartości)

**Jeśli są błędy**:
- Backend: logi WARNING z listą błędów
- Frontend: Toast `⚠️  X ostrzeżeń walidacji (sprawdź konsolę)`
- Response: pole `validationErrors` z szczegółami

---

## 🧪 Testy

```bash
# Uruchom testy annotation loadera
pytest tests/test_annotation_loader.py -v

# Testy obejmują:
# ✅ Wykrywanie formatu Label Studio
# ✅ Wykrywanie formatu COCO standard
# ✅ Konwersję rotated rectangles (0°, 45°, 90°)
# ✅ Walidację formatu
# ✅ Obsługę błędów (brak pliku, nieprawidłowy JSON)
```

---

## 🎯 Przykłady Użycia

### Przykład 1: Ładowanie z CLI

```bash
# Najpierw eksportuj z Label Studio
# Potem załaduj w aplikacji:

curl -X POST http://localhost:5000/api/symbols/load-annotations \
  -H "Content-Type: application/json" \
  -d '{
    "annotationFile": "labelstudio_exports/resistors_v1.json",
    "validate": true
  }'
```

### Przykład 2: Integracja z Treningiem YOLOv8

```python
from talk_electronic.services.annotation_loader import load_annotations
from pathlib import Path

# Załaduj anotacje (automatyczna konwersja rotated rectangles)
annotations_path = Path("data/annotations/labelstudio_export.json")
coco_data = load_annotations(annotations_path)

# Zapisz do formatu YOLOv8-seg
output_dir = Path("data/yolov8_seg/annotations")
output_dir.mkdir(parents=True, exist_ok=True)

with open(output_dir / "train.json", 'w') as f:
    json.dump(coco_data, f)

# Trenuj YOLOv8-seg
from ultralytics import YOLO
model = YOLO('yolov8n-seg.pt')
model.train(
    data='data/yolov8_seg.yaml',
    epochs=100,
    imgsz=1024
)
```

### Przykład 3: Frontend - Button Click

```javascript
// HTML
<button id="load-annotations-btn">Załaduj Anotacje</button>

// JavaScript
document.getElementById('load-annotations-btn').addEventListener('click', async () => {
    try {
        const data = await loadAnnotations('labelstudio_exports/project_1.json');
        console.log('Załadowano:', data);

        // Możesz teraz użyć danych np. do wizualizacji
        renderAnnotations(data);
    } catch (error) {
        console.error('Błąd:', error);
    }
});
```

---

## 🚀 Następne Kroki dla Użytkownika

1. **Zacznij anotacje w Label Studio** z template `schematic_hybrid_template.xml`
2. **Eksportuj do JSON** (Label Studio → Export → JSON)
3. **Uruchom aplikację** - konwersja dzieje się AUTOMATYCZNIE! 🎉
4. **Trenuj YOLOv8-seg** z przekonwertowanymi danymi

**Nie musisz:**
- ❌ Ręcznie uruchamiać skryptów konwersji
- ❌ Martwić się formatem (Label Studio vs COCO)
- ❌ Sprawdzać czy rotated rectangles są obsługiwane

**System robi to za Ciebie!** ✅

---

## 📝 FAQ

**Q: Co jeśli zapominam czy wyeksportowałem z rotacją czy bez?**
A: Nie ma znaczenia! System automatycznie wykrywa format i konwertuje jeśli potrzeba.

**Q: Czy konwersja zmienia oryginalne pliki?**
A: NIE. Oryginalne pliki pozostają niezmienione. Konwersja dzieje się w pamięci.

**Q: Czy mogę nadal używać `export_labelstudio_to_coco_seg.py`?**
A: Tak, ale nie musisz! Aplikacja robi to automatycznie przy ładowaniu.

**Q: Co jeśli mam mieszane formaty (część rotated, część polygons)?**
A: Działa! System konwertuje tylko rotated rectangles, reszta pozostaje bez zmian.

**Q: Jak sprawdzić czy konwersja zadziałała?**
A: Sprawdź logi (backend) lub powiadomienia (frontend). Zobaczysz komunikat o konwersji.

---

## 🛠️ Troubleshooting

### Problem: "Plik nie istnieje"
**Rozwiązanie**: Sprawdź ścieżkę. Ścieżki względne szukają w `data/annotations/`.

### Problem: "Nieprawidłowy format JSON"
**Rozwiązanie**: Sprawdź czy plik JSON jest poprawny (`jq . file.json` w terminalu).

### Problem: "Ostrzeżenia walidacji"
**Rozwiązanie**: Sprawdź szczegóły w `info.validationErrors`. Zazwyczaj brakuje pól `id` lub `category_id`.

### Problem: "Konwersja nie działa"
**Rozwiązanie**: Sprawdź logi backendu. Włącz DEBUG: `export FLASK_DEBUG=1`.

---

**Autor**: Talk Electronics Team
**Data**: 2025-01-06
**Wersja**: 1.0
