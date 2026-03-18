# Strategia Rotated Bounding Boxes + Polygons dla Detekcji Symboli

## ✅ Decyzja: Używamy HYBRYDOWEGO podejścia (RBB + Polygons)

### Uzasadnienie
Schematy elektroniczne są **idealnym przypadkiem użycia** dla RBB:
- Komponenty naturalne obrócone (rezystory pionowe/poziome, tranzystory w różnych konfiguracjach)
- Etykiety tekstowe pod różnymi kątami
- Tight clusters symboli wymagają precyzyjnych granic bez "pustej przestrzeni"
- Prostszy i szybszy w anotacji niż poligony

**ALE**: ~10-20% przypadków wymaga polygonów (tekst nachodzi, nieregularne kształty, częściowo widoczne)

### 🚨 MIT: "Nie można mieszać rectangles z polygonami" - FAŁSZ!

**Powszechny błąd** (propagowany przez niektóre AI jak Gemini):
> "Jeśli użyjesz różnych narzędzi anotacji (rectangles + polygons), model AI będzie zdezorientowany i trenowanie się nie uda."

**To jest całkowicie NIEPRAWDA!** Oto dlaczego:

#### 1. **Model nie widzi "narzędzia", widzi tylko KSZTAŁT**
```python
# Co WIDZISZ w Label Studio:
annotation_1 = {"type": "rectanglelabels", "rotation": 45}  # Prostokąt
annotation_2 = {"type": "polygonlabels", "points": [...]}   # Polygon

# Co WIDZI model po konwersji:
training_sample_1 = {"segmentation": [[x1,y1,x2,y2,x3,y3,x4,y4]]}  # 4-pt polygon
training_sample_2 = {"segmentation": [[x1,y1,x2,y2,...,x8,y8]]}    # 8-pt polygon

# DLA MODELU OBA SĄ PO PROSTU POLIGONAMI! ✅
```

#### 2. **Profesjonalne datasety ZAWSZE mieszają formaty**
- **COCO Dataset** (Microsoft): prostokąty + poligony + RLE masks w jednym datasecie
- **Medical Imaging**: proste organy (rectangles) + złożone (polygons)
- **Autonomous Driving**: samochody (bboxes) + piesi (polygons) + linie (polylines)

#### 3. **To jest NATURALNA augmentacja danych!**
- **Rectangles** (80-90%): Dużo prostych przykładów → szybkie uczenie podstaw
- **Polygons** (10-20%): Trudne edge cases → fine-tuning na rzeczywistych problemach
- **Efekt**: Model jest LEPSZY niż z jednym formatem!

#### 4. **Prawdziwe ryzyko to SEMANTYKA, nie FORMAT**
```python
# ❌ ŹLE (niespójność semantyczna):
resistor_1 = {"mask": "only_body", "class": "resistor"}
resistor_2 = {"mask": "body_plus_text", "class": "resistor"}  # Niespójne!

# ✅ DOBRE (różne formaty, spójna semantyka):
resistor_1 = {"mask": "only_body", "annotation_method": "rectangle"}
resistor_2 = {"mask": "only_body", "annotation_method": "polygon"}  # Spójne! ✅
```

**Wniosek**: Mieszaj rectangles z polygonami bez obaw! Model tego nie tylko "zniesie", ale będzie z tego **skorzysta**.

### Dlaczego NIE poligony?
| Kryterium | Rotated BBox | Poligon | Werdykt |
|-----------|--------------|---------|---------|
| Szybkość anotacji | ~15s/obiekt | ~45s/obiekt | ✅ RBB 3× szybsze |
| Precyzja | Wystarczająca | Idealna | ✅ RBB wystarczy |
| Wsparcie ML | YOLOv8-OBB, MMRotate | YOLO-seg, Mask R-CNN | ✅ Oba dojrzałe |
| Rozmiar danych | 5 liczb | 8-20 liczb | ✅ RBB 4× mniejsze |
| Dopasowanie do PCB | Perfekcyjne | Overkill | ✅ RBB wystarczy |

**Wynik: RBB = optymalna równowaga między dokładnością a efektywnością**

---

## 📐 Format Danych

### W Label Studio
Używaj narzędzia **RectangleLabels** z opcją **rotation**:
```xml
<View>
  <RectangleLabels name="label" toName="image" canRotate="true">
    <Label value="resistor" background="red"/>
    <Label value="capacitor" background="blue"/>
    <!-- ... inne klasy ... -->
  </RectangleLabels>
  <Image name="image" value="$image"/>
</View>
```

### Export do COCO
Każda anotacja zawiera:
```json
{
  "id": 9001,
  "image_id": 101,
  "category_id": 3,
  "bbox": [x_center, y_center, width, height],
  "attributes": {
    "bbox_rotation": 45.0,  // Kąt w stopniach (0-360)
    "annotator": "user_id",
    "confidence_hint": 1.0
  }
}
```

**WAŻNE**: `bbox` przechowuje **[x_center, y_center, width, height]**, nie [x_min, y_min, w, h]

---

## 🤖 Wybór Modelu

### Rekomendacja: Hybrydowe podejście

Ponieważ będziemy mieć **2 typy anotacji** (rotated rectangles + polygons), mamy 3 strategie:

#### **Strategia A: Instance Segmentation (REKOMENDOWANA dla >= 20% polygons) ⭐**

**Model**: YOLOv8-seg (instance segmentation) lub Mask R-CNN

**Dlaczego:**
- ✅ Natywnie obsługuje **dowolne kształty** (zarówno prostokąty jak i poligony)
- ✅ Podczas exportu: konwertuj rotated rectangles → 4-corner polygons
- ✅ Model uczy się precyzyjnych granic symboli
- ✅ Potem możesz post-process maski do rotated boxes jeśli potrzebujesz

**Trenowanie:**
```bash
# Wszystkie annotacje (rectangles + polygons) → COCO instance segmentation
yolo segment train \
  model=yolov8n-seg.pt \
  data=data/yolov8_seg.yaml \
  epochs=100 \
  imgsz=1024
```

**Zalety:**
- Uniwersalne rozwiązanie dla wszystkich kształtów
- Wysoka precyzja na edge cases
- Standardowy format COCO

**Wady:**
- ~15% wolniejszy inference niż pure detection
- Większe modele (więcej parametrów)

---

#### **Strategia B: Pure OBB z filtrowaniem (REKOMENDOWANA dla < 10% polygons)**

**Model**: YOLOv8-OBB

**Dlaczego:**
- ✅ Jeśli >90% to rotated rectangles, optymalizujemy dla większości
- ✅ Szybszy inference niż segmentation

**Trenowanie:**
```bash
# TYLKO rotated rectangles → YOLOv8-OBB
# Polygons → konwertuj do minimal rotated rectangle LUB odrzuć
yolo obb train \
  model=yolov8n-obb.pt \
  data=data/yolov8_obb.yaml \
  epochs=100
```

**Zalety:**
- Najszybszy inference
- Prostszy pipeline
- Mniejsze modele

**Wady:**
- Polygony muszą być konwertowane (strata precyzji)
- Gorzej na edge cases

---

#### **Strategia C: Ensemble (dla wymagających aplikacji)**

**Modele**: YOLOv8-OBB (fast path) + YOLOv8-seg (precision path)

**Dlaczego:**
- ✅ Best of both worlds: szybkość + precyzja

**Pipeline:**
1. YOLOv8-OBB robi szybką detekcję wszystkiego
2. Dla detekcji z confidence < threshold → użyj YOLOv8-seg
3. Lub: YOLOv8-OBB dla prostych klas, YOLOv8-seg dla złożonych (IC, custom symbols)

**Zalety:**
- Optymalna równowaga speed/accuracy
- Możliwość dostrajania trade-off

**Wady:**
- Złożoność implementacji
- Dwa modele do utrzymania

---

### 🎯 Finalna Rekomendacja dla Twojego Projektu

**Zacznij od Strategii A: YOLOv8-seg (Instance Segmentation)**

**Uzasadnienie:**
1. **Elastyczność**: Obsługuje oba formaty (rotated rect + polygon) bez konwersji
2. **Przyszłościowość**: Jeśli okaże się że >20% to polygony, jesteś gotowy
3. **Jakość**: Lepsze wyniki na trudnych przypadkach (a te są najważniejsze!)
4. **Ekosystem**: YOLOv8-seg ma świetne wsparcie, łatwy export do ONNX/TensorRT

**Jeśli okaże się, że:**
- Polygony to <5% → rozważ switch na YOLOv8-OBB (szybszy)
- Potrzebujesz max speed → ensemble (OBB + seg)

### YOLOv8-seg (zaktualizowane rekomendacje)

**Zamiast YOLOv8-OBB, używamy YOLOv8-seg:**
- ✅ Oficjalnie wspierany przez Ultralytics (aktywnie rozwijany)
- ✅ Prosty w użyciu: `yolo train model=yolov8n-obb.pt data=custom.yaml`
- ✅ Obsługuje format DOTA/COCO-OBB out-of-the-box
- ✅ Szybki inference: 50-150 FPS na GPU
- ✅ Pre-trained weights dostępne

**Alternatywy:**
- **MMRotate** (OpenMMLab): Więcej opcji modeli (Oriented R-CNN, RoI Transformer), ale trudniejsza konfiguracja
- **Oriented R-CNN**: Lepsza precyzja, wolniejszy inference

**Decyzja: Zaczynamy od YOLOv8-seg (instance segmentation)** jako uniwersalne rozwiązanie.

**Fallback**: YOLOv8-OBB jeśli okaże się że polygony to <5% i potrzebujesz maksymalnej szybkości.

---

## 🔧 Implementacja

### 1A. Aktualizacja Exportera z Label Studio (YOLOv8-seg - REKOMENDOWANY)

**Cel**: Konwertuj dane z Label Studio (rectangles + polygons) do formatu COCO instance segmentation

**Skrypt**: `scripts/export_labelstudio_to_coco_seg.py`

```python
#!/usr/bin/env python3
"""Convert Label Studio (rotated rectangles + polygons) to COCO instance segmentation."""

import json
from pathlib import Path
from typing import Dict, List
import numpy as np

def rotated_rect_to_polygon(x_pct, y_pct, w_pct, h_pct, rotation_deg, img_w, img_h):
    """Convert rotated rectangle to 4-corner polygon coordinates.

    Args:
        x_pct, y_pct, w_pct, h_pct: Rectangle in % (Label Studio format)
        rotation_deg: Rotation angle in degrees
        img_w, img_h: Image dimensions in pixels

    Returns:
        List of [x1, y1, x2, y2, x3, y3, x4, y4] in absolute pixels
    """
    import math

    # Convert to absolute pixels
    x = (x_pct / 100) * img_w
    y = (y_pct / 100) * img_h
    w = (w_pct / 100) * img_w
    h = (h_pct / 100) * img_h

    # Center coordinates
    cx = x + w / 2
    cy = y + h / 2

    # Rotation in radians
    angle = math.radians(rotation_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)

    # Four corners (relative to center)
    corners = [
        (-w/2, -h/2),  # Top-left
        (w/2, -h/2),   # Top-right
        (w/2, h/2),    # Bottom-right
        (-w/2, h/2),   # Bottom-left
    ]

    # Rotate and translate corners
    polygon = []
    for dx, dy in corners:
        x_rot = cx + (dx * cos_a - dy * sin_a)
        y_rot = cy + (dx * sin_a + dy * cos_a)
        polygon.extend([x_rot, y_rot])

    return polygon

def polygon_to_segmentation(points_pct, img_w, img_h):
    """Convert Label Studio polygon (%) to COCO segmentation (absolute pixels).

    Args:
        points_pct: List of [x1, y1, x2, y2, ...] in % (0-100)
        img_w, img_h: Image dimensions

    Returns:
        List of [x1, y1, x2, y2, ...] in absolute pixels
    """
    return [
        (points_pct[i] / 100 * img_w) if i % 2 == 0 else (points_pct[i] / 100 * img_h)
        for i in range(len(points_pct))
    ]

def convert_labelstudio_to_coco_seg(
    labelstudio_json: Path,
    output_json: Path,
    images_dir: Path,
    class_mapping: Dict[str, int]
):
    """
    Convert Label Studio export to COCO instance segmentation format.

    Handles both:
    - RectangleLabels (with rotation) → converted to 4-corner polygons
    - PolygonLabels → used directly
    """
    with open(labelstudio_json) as f:
        ls_data = json.load(f)

    coco = {
        "images": [],
        "annotations": [],
        "categories": [
            {"id": cat_id, "name": cat_name}
            for cat_name, cat_id in class_mapping.items()
        ]
    }

    annotation_id = 1

    for task in ls_data:
        # Image info
        image_id = task['id']
        file_name = Path(task['data']['image']).name
        img_w = task['data'].get('width', 1000)  # Should fetch from actual image!
        img_h = task['data'].get('height', 1000)

        coco["images"].append({
            "id": image_id,
            "file_name": file_name,
            "width": img_w,
            "height": img_h
        })

        # Annotations
        for result in task['annotations'][0]['result']:
            value = result['value']

            # Handle RectangleLabels (with optional rotation)
            if result['type'] == 'rectanglelabels':
                label = value['rectanglelabels'][0]
                rotation = value.get('rotation', 0)

                # Convert rotated rectangle to polygon
                segmentation = rotated_rect_to_polygon(
                    value['x'], value['y'],
                    value['width'], value['height'],
                    rotation, img_w, img_h
                )

            # Handle PolygonLabels
            elif result['type'] == 'polygonlabels':
                label = value['polygonlabels'][0]

                # Extract points from Label Studio format
                points_pct = []
                for point in value['points']:
                    points_pct.extend([point[0], point[1]])

                segmentation = polygon_to_segmentation(points_pct, img_w, img_h)

            else:
                continue  # Skip other annotation types

            # Calculate bounding box from segmentation
            xs = segmentation[0::2]
            ys = segmentation[1::2]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            bbox = [x_min, y_min, x_max - x_min, y_max - y_min]
            area = bbox[2] * bbox[3]

            coco["annotations"].append({
                "id": annotation_id,
                "image_id": image_id,
                "category_id": class_mapping[label],
                "bbox": bbox,
                "area": area,
                "segmentation": [segmentation],  # COCO expects list of polygons
                "iscrowd": 0,
                "attributes": {
                    "annotation_method": result['type'],
                    "rotation": value.get('rotation', 0) if result['type'] == 'rectanglelabels' else None
                }
            })
            annotation_id += 1

    # Save COCO JSON
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, 'w') as f:
        json.dump(coco, f, indent=2)

    print(f"✅ Converted {len(coco['images'])} images, {len(coco['annotations'])} annotations")
    print(f"   Saved to: {output_json}")

if __name__ == '__main__':
    convert_labelstudio_to_coco_seg(
        labelstudio_json=Path('data/annotations/labelstudio_exports/project.json'),
        output_json=Path('data/annotations/coco_seg/train.json'),
        images_dir=Path('data/images'),
        class_mapping={
            'resistor': 1, 'capacitor': 2, 'diode': 3,
            'transistor': 4, 'op_amp': 5, 'connector': 6,
            'power_rail': 7, 'ground': 8, 'ic_pin': 9,
            'net_label': 10, 'measurement_point': 11, 'misc_symbol': 12
        }
    )
```

---

### 1B. Exporter dla YOLOv8-OBB (jeśli wolisz pure rotated boxes)

**Użyj tylko jeśli**: Polygony to <5% i chcesz maksymalnej szybkości

**Skrypt**: `scripts/export_labelstudio_to_yolov8obb.py`

```python
#!/usr/bin/env python3
"""Konwertuje obrócone prostokąty z Label Studio do formatu YOLOv8-OBB.

UWAGA: Ten exporter POMIJA PolygonLabels! Używaj tylko jeśli >95% to prostokąty.
"""

import json
from pathlib import Path
from typing import Dict, List

def convert_labelstudio_to_yolov8obb(
    labelstudio_json: Path,
    output_dir: Path,
    class_mapping: Dict[str, int]
):
    """
    Args:
        labelstudio_json: Path to Label Studio export (JSON)
        output_dir: Directory to save YOLOv8-OBB txt files
        class_mapping: {"resistor": 0, "capacitor": 1, ...}
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(labelstudio_json) as f:
        data = json.load(f)

    for task in data:
        image_filename = Path(task['data']['image']).stem
        image_width = task['data'].get('width', 1000)  # Get from image metadata
        image_height = task['data'].get('height', 1000)

        annotations = []
        for annotation in task['annotations'][0]['result']:
            if annotation['type'] != 'rectanglelabels':
                continue

            value = annotation['value']
            label = value['rectanglelabels'][0]

            # Label Studio format: x, y (top-left), width, height in %
            x_pct = value['x'] / 100
            y_pct = value['y'] / 100
            w_pct = value['width'] / 100
            h_pct = value['height'] / 100
            rotation = value.get('rotation', 0)  # Degrees

            # Convert to center coordinates
            x_center = x_pct + w_pct / 2
            y_center = y_pct + h_pct / 2

            # YOLOv8-OBB format: class x_center y_center width height angle
            class_id = class_mapping[label]
            annotations.append(
                f"{class_id} {x_center:.6f} {y_center:.6f} "
                f"{w_pct:.6f} {h_pct:.6f} {rotation:.2f}"
            )

        # Save to txt file
        output_file = output_dir / f"{image_filename}.txt"
        output_file.write_text('\n'.join(annotations))

if __name__ == '__main__':
    convert_labelstudio_to_yolov8obb(
        labelstudio_json=Path('data/annotations/labelstudio_exports/project.json'),
        output_dir=Path('data/annotations/yolov8_obb/labels/train'),
        class_mapping={'resistor': 0, 'capacitor': 1, 'diode': 2}  # etc.
    )
```

### 2. Data.yaml dla YOLOv8-seg

```yaml
# data/yolov8_seg.yaml
path: ../data/annotations/coco_seg
train: train.json  # COCO format JSON
val: val.json
test: test.json

# Classes (order matters!)
names:
  0: resistor
  1: capacitor
  2: diode
  3: transistor
  4: op_amp
  5: connector
  6: power_rail
  7: ground
  8: ic_pin
  9: net_label
  10: measurement_point
  11: misc_symbol
```

### 3A. Trenowanie YOLOv8-seg (REKOMENDOWANY)

```bash
# Install ultralytics
pip install ultralytics>=8.1.0

# Train instance segmentation model
yolo segment train \
  model=yolov8n-seg.pt \
  data=data/yolov8_seg.yaml \
  epochs=100 \
  imgsz=1024 \
  batch=16 \
  device=0

# Inference
yolo segment predict \
  model=runs/segment/train/weights/best.pt \
  source=data/test_images/ \
  save_txt=True  # Saves masks
```

### 3B. Trenowanie YOLOv8-OBB (alternatywa)

```bash
# Install ultralytics with OBB support
pip install ultralytics>=8.1.0

# Train
yolo obb train \
  model=yolov8n-obb.pt \
  data=data/yolov8_obb.yaml \
  epochs=100 \
  imgsz=1024 \
  batch=16 \
  device=0

# Inference
yolo obb predict \
  model=runs/obb/train/weights/best.pt \
  source=data/test_images/
```

---

## 📊 Walidacja Formatu

Rozszerz `scripts/validate_annotations.py`:

```python
def _bbox_valid_rotated(
    bbox: List[float],
    angle: float,
    image_size: Tuple[int, int]
) -> bool:
    """Validate rotated bounding box.

    Args:
        bbox: [x_center, y_center, width, height] in absolute pixels
        angle: Rotation in degrees (0-360)
        image_size: (width, height) of image
    """
    try:
        x_c, y_c, w, h = map(float, bbox)
    except (TypeError, ValueError):
        return False

    if w <= 0 or h <= 0:
        return False

    if not (0 <= angle <= 360):
        return False

    max_x, max_y = image_size

    # Compute corner coordinates after rotation
    import math
    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    corners = [
        (x_c + (dx * cos_a - dy * sin_a), y_c + (dx * sin_a + dy * cos_a))
        for dx, dy in [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
    ]

    # Check if any corner is outside image
    for x, y in corners:
        if not (0 <= x <= max_x) or not (0 <= y <= max_y):
            return False

    return True
```

---

## 🎯 Workflow Anotacji

### Zasady dla Annotatora:

#### 1. **Wybór narzędzia (decision tree)**

```
START: Czy symbol można objąć TIGHT rotated rectangle?
  │
  ├─ TAK (80-90% przypadków)
  │   └─→ Użyj RectangleLabels z rotation
  │
  └─ NIE (10-20% przypadków)
      │
      ├─ Tekst/elementy nachodzą nie do uniknięcia?
      │   └─→ Użyj PolygonLabels (4-8 punktów)
      │
      ├─ Symbol częściowo widoczny/ucięty?
      │   └─→ Użyj PolygonLabels na widoczną część
      │
      └─ Nieregularny kształt (uszkodzony schemat)?
          └─→ Użyj PolygonLabels LUB zaznacz jako "noisy"
```

#### 2. **Rotated Rectangle (preferowane, 80-90% przypadków)**

**Kiedy używać:**
- Symbol jest prostokątny/prostokątopodobny
- Da się go obrócić, aby uniknąć overlap
- Tight box jest możliwy z marginesem <10% pustej przestrzeni

**Jak zaznaczać:**
1. Narysuj prostokąt obejmujący symbol
2. Obróć, aby dopasować orientację symbolu
3. Dopasuj rozmiar (tight, ale nie za ciasny)
4. Upewnij się, że **NIE zahaczasz** o:
   - Tekst etykiet (R1, C2, etc.)
   - Linie połączeń
   - Sąsiednie symbole

**Przykłady:**
- ✅ Rezystor z etykietą obok → obróć, aby uniknąć tekstu
- ✅ Kondensator pionowy → 90° rotation
- ✅ Tranzystor skośny → np. 135° rotation
- ⚠️ IC z pinami → jeden prostokąt na całość (bez pinów)

#### 3. **Polygon (edge cases, 10-20% przypadków)**

**Kiedy używać:**
- Rotated rectangle **nie wystarczy** mimo rotacji
- Tekst nachodzi na symbol bez możliwości separacji
- Kilka symboli zlanych razem (oznacz jako jeden obiekt z attributem `composite: true`)
- Symbol ma nietypowy kształt (ręcznie narysowany schemat)
- Symbol częściowo widoczny (przy krawędzi obrazu)

**Jak zaznaczać:**
1. Przełącz na narzędzie PolygonLabels
2. Użyj **4-8 punktów** (nie więcej, chyba że absolutnie konieczne)
3. Prowadź poligon wzdłuż konturu symbolu
4. Zamknij poligon
5. **Opcjonalnie**: Dodaj attribute `annotation_method: polygon`

**Przykłady:**
- ✅ Rezystor z tekstem R1 nachodzącym → polygon omija tekst
- ✅ Kondensator przy krawędzi (50% widoczny) → polygon na widoczną część
- ✅ Niestandardowy symbol (strzałka, custom) → polygon
- ✅ Grupa symboli nie do rozdzielenia → polygon + `composite: true`

#### 4. **Spójność kątów (dla Rotated Rectangle)**

- Rezystor poziomy: **0°** lub **180°**
- Rezystor pionowy: **90°** lub **270°**
- Kondensator polaryzowany: zorientuj według plusu
- Stosuj wielokrotności **45°** gdy możliwe (0°, 45°, 90°, 135°, etc.)
- **Wyjątek**: Schematy ręcznie rysowane mogą mieć dowolne kąty

#### 5. **Quality flags (opcjonalne, ale pomocne)**

Dla **trudnych przypadków** dodaj attributes:

```json
"attributes": {
  "bbox_rotation": 45.0,
  "quality": "clean",  // "clean" | "noisy" | "partial" | "uncertain"
  "annotation_method": "rectangle",  // "rectangle" | "polygon"
  "reason": "",  // Opcjonalne: "overlapping_text", "edge_crop", etc.
  "annotator": "user_id"
}
```

**Kiedy używać:**
- `quality: "noisy"` - prostokąt zawiera niechciany tekst/elementy
- `quality: "partial"` - symbol częściowo widoczny
- `quality: "uncertain"` - nie jesteś pewien klasy lub granic
- `reason` - dla celów audytu/debugowania

#### 6. **Edge cases - szczegółowe zasady**

| Sytuacja | Co robić | Przykład |
|----------|----------|----------|
| **Tekst nachodzi** | Polygon omijający tekst LUB rotated rect + `quality: noisy` | R1 nad rezystorem |
| **Częściowo widoczny** | Polygon na widoczną część | Symbol przy krawędzi |
| **Symbole złożone** | Jeden prostokąt na całość (bez pinów) | Op-amp (body), IC (body) |
| **Linie połączeń** | Ignoruj linie, zaznacz tylko symbol | Rezystor z nogami |
| **Sąsiednie symbole** | Osobne annotacje, bez overlaps | Kondensator + rezystor obok |
| **Nieczytelny/uszkodzony** | Pomiń LUB zaznacz + `quality: uncertain` | Zeskanowany schemat niskiej jakości |
| **Composite (np. H-bridge)** | Polygon + `composite: true` | Grupa 4 tranzystorów |

#### 7. **Szybkie sprawdzenie jakości**

Przed zapisaniem:
- [ ] Czy annotation jest **TIGHT** (minimalna pusta przestrzeń)?
- [ ] Czy **NIE zahaczyłem** o tekst/inne symbole?
- [ ] Czy wybrałem **właściwe narzędzie** (rect vs polygon)?
- [ ] Czy kąt jest **sensowny** (wielokrotność 45°)?
- [ ] Czy widoczne są **wszystkie granice** symbolu?

---

## 📈 Metryki Sukcesu

### Podczas Anotacji
- **Średni czas/obiekt**: < 20s (docelowo 15s po przeszkoleniu)
- **Inter-annotator agreement**: IoU > 0.85 dla rotated boxes
- **Pokrycie kątów**: Równomierny rozkład 0°-360°

### Po Treningu
- **mAP50 (IoU=0.5)**: > 0.75 (baseline)
- **mAP75 (IoU=0.75)**: > 0.60
- **Angle accuracy**: Mean absolute error < 5°

---

## 🚀 Next Steps

### Natychmiastowe (tydzień 1):
- [ ] Zaktualizuj template Label Studio: dodaj `canRotate="true"`
- [ ] Wygeneruj 50 testowych anotacji z rotation
- [ ] Napisz skrypt exportera do YOLOv8-OBB
- [ ] Zwaliduj format na małym samplu

### Krótkoterminowe (tydzień 2-3):
- [ ] Zaannotuj 200 obrazów z rotated boxes
- [ ] Trenuj wstępny model YOLOv8n-OBB
- [ ] Zmierz baseline metrics (mAP, angle error)
- [ ] Zidentyfikuj problematyczne klasy

### Średnioterminowe (miesiąc 1-2):
- [ ] Skaluj do 600+ schematów
- [ ] Fine-tune YOLOv8m-OBB lub YOLOv8l-OBB
- [ ] Integruj z pipeline (`talk_electronic/routes/symbol_detection.py`)
- [ ] A/B test: rotated vs axis-aligned na validation set

---

## 🔬 Troubleshooting

### Problem: Model ignoruje kąt, przewiduje tylko AABB
**Rozwiązanie**: Sprawdź, czy:
- Używasz `yolov8*-obb.pt`, nie `yolov8*.pt`
- Format danych ma 5 kolumn (class, x, y, w, h, angle)
- Loss function uwzględnia angle (powinno być automatyczne w YOLOv8-OBB)

### Problem: Duży angle error (>15°)
**Rozwiązanie**:
- Zwiększ wagi loss dla angle component
- Augmentuj dane: random rotations podczas treningu
- Użyj większego modelu (YOLOv8m/l-OBB)

### Problem: Wolny inference
**Rozwiązanie**:
- YOLOv8-OBB jest ~10% wolniejszy niż standardowy YOLO
- Użyj YOLOv8n-OBB dla speed, YOLOv8s-OBB dla balance
- Zmniejsz resolution (np. 640 zamiast 1024)

---

## 📚 Referencje

- [YOLOv8-OBB Documentation](https://docs.ultralytics.com/tasks/obb/)
- [MMRotate GitHub](https://github.com/open-mmlab/mmrotate)
- [DOTA Dataset (rotated aerial objects)](https://captain-whu.github.io/DOTA/)
- [Oriented R-CNN Paper](https://arxiv.org/abs/2108.05699)

---

## ✅ Podsumowanie

**Używaj HYBRYDOWEGO podejścia w Label Studio:**
- ✅ **Rotated Rectangle** (80-90% przypadków) - szybkie, precyzyjne dla prostokątnych symboli
- ✅ **Polygon** (10-20% przypadków) - dla edge cases gdzie rectangle nie wystarczy

**Model: YOLOv8-seg (Instance Segmentation)**
- ✅ Obsługuje oba formaty natywnie (rectangles → polygons, polygons → masks)
- ✅ Najlepsza precyzja na trudnych przypadkach
- ✅ Standardowy ekosystem (COCO format)
- ✅ Tylko ~15% wolniejszy niż pure detection

**Kiedy używać Polygon:**
```
IF symbol NIE mieści się w tight rotated rectangle:
    → Tekst nachodzi nie do uniknięcia
    → Nieregularny kształt (uszkodzony schemat)
    → Częściowo widoczny (przy krawędzi)
    → Composite symbol (grupa elementów)
THEN:
    → Użyj PolygonLabels (4-8 punktów)
ELSE:
    → Użyj RectangleLabels z rotation (preferowane)
```

**Workflow:**
1. Zacznij od Rotated Rectangle (domyślne narzędzie)
2. Jeśli nie możesz objąć symbolu tight box → przełącz na Polygon
3. Dodawaj quality flags dla trudnych przypadków
4. Eksportuj do COCO instance segmentation
5. Trenuj YOLOv8-seg

**Odpowiedź Gemini była:**
- ✅ Technicznie poprawna (rotated boxes wymagają specjalnych modeli)
- ❌ Zbyt pesymistyczna (YOLOv8-OBB/seg są dojrzałe w 2025)
- ❌ **BŁĘDNA w kwestii mieszania formatów** - to jest STANDARD branżowy!
- ❌ Nie uwzględniła hybrydowego podejścia (rect + polygon → segmentation)
- ❌ Zignorowała specyfikę schematów PCB (idealny case dla RBB)

**Ty miałeś rację** używając rotation! Teraz tylko dodaj Polygon jako "escape hatch" dla ~10-20% trudnych przypadków i jesteś gotowy! 🎉

---

## 🔬 Debunking Myths: Szczegółowe wyjaśnienie

### Mit #1: "Mieszanie formatów powoduje confusion modelu"

**Claim** (błędny):
> "Jeśli część danych to rectangles a część polygons, model nie będzie wiedział czego się uczyć."

**Rzeczywistość**:
Model uczy się funkcji: `f(piksele obrazu) → (klasa, maska)`

**Input** do modelu:
```python
# Obraz (tensor 3D):
image = np.array([[[R, G, B], [R, G, B], ...]])  # shape: (H, W, 3)
```

**Target** (ground truth):
```python
# Maska binarna (tensor 2D):
mask = np.array([[0, 0, 1, 1, ...],   # 0 = tło, 1 = symbol
                 [0, 1, 1, 1, ...],
                 ...])                 # shape: (H, W)
```

**Model NIE widzi**:
- ❌ Czy maska powstała z rectangle czy polygon
- ❌ Ile punktów miał polygon
- ❌ Jaki był kąt rotacji rectangle
- ❌ Jakie narzędzie użył annotator

**Model widzi TYLKO**:
- ✅ Piksele obrazu (RGB values)
- ✅ Maskę (które piksele należą do symbolu)

**Analogia**: To jakby twierdzić że student matematyki będzie "zdezorientowany" jeśli niektóre zadania były napisane długopisem a inne ołówkiem. Student widzi TREŚĆ, nie narzędzie pisania!

---

### Mit #2: "Potrzebujesz spójnego formatu annotacji"

**Claim** (częściowo prawdziwy, ale źle zinterpretowany):
> "Dane treningowe muszą być spójne."

**Co to NAPRAWDĘ znaczy**:

✅ **Spójność SEMANTYCZNA** (WAŻNE):
```python
# Wszystkie rezystory zaznaczane zgodnie z tą samą zasadą:
resistor_1 = {"mask": "body_only", "exclude": "text_labels"}
resistor_2 = {"mask": "body_only", "exclude": "text_labels"}  # ✅ Spójne!

# ŹLE:
resistor_3 = {"mask": "body_plus_text"}  # ❌ Niespójne!
```

❌ **Spójność FORMATU** (NIE MA ZNACZENIA):
```python
# To jest OK! Model nie widzi różnicy:
resistor_1 = {
    "mask": "body_only",
    "annotation_method": "rectangle",  # ← Metadata, nie input
    "points": 4
}
resistor_2 = {
    "mask": "body_only",
    "annotation_method": "polygon",    # ← Metadata, nie input
    "points": 8
}
# ✅ OBA SĄ SPÓJNE SEMANTYCZNIE!
```

**Kluczowa różnica**:
- **Semantyka** = "Co zaznaczamy" (body, body+pins, etc.)
- **Format** = "Jak zaznaczamy" (rectangle, polygon, freehand)

Model dba o SEMANTYKĘ, nie FORMAT.

---

### Mit #3: "Różne liczby punktów poligonów są problemem"

**Claim** (błędny):
> "Jeśli część polygonów ma 4 punkty a część 8, model będzie confused."

**Rzeczywistość**:
Model operuje na **pikselowej masce**, nie na punktach poligonu!

**Pipeline konwersji**:
```python
# Krok 1: Polygon points (różne liczby)
polygon_4pt = [[100,100], [200,100], [200,150], [100,150]]  # Prostokąt
polygon_8pt = [[100,100], [150,95], [200,100], ...complex shape]  # Złożony

# Krok 2: Konwersja do maski (TAK SAMO!)
mask_1 = cv2.fillPoly(blank, [polygon_4pt], 1)  # shape: (H, W)
mask_2 = cv2.fillPoly(blank, [polygon_8pt], 1)  # shape: (H, W)

# Krok 3: Model trenuje się na maskach
model.train(image, mask_1)  # ✅
model.train(image, mask_2)  # ✅

# Obie maski mają IDENTYCZNY format dla modelu!
```

**Analogia**: To jak twierdzić że uczeń nie nauczy się rysować okręgów jeśli pokażesz mu okręgi narysowane kompasem (wiele punktów) i monety obwiedzione (mało punktów). Uczeń uczy się KSZTAŁTU "okrąg", nie narzędzia!

---

### Mit #4: "COCO format obsługuje tylko jeden typ annotacji"

**Claim** (błędny):
> "Format COCO był stworzony dla jednego typu annotacji na dataset."

**Rzeczywistość**:
COCO **oficjalnie** wspiera mieszane typy w jednym datasecie!

**Z oficjalnej dokumentacji COCO**:
```python
{
  "annotations": [
    # Prostokąt (4-point polygon):
    {
      "segmentation": [[x1,y1, x2,y2, x3,y3, x4,y4]],
      "area": 12000.0,
      "bbox": [x, y, w, h],
      "category_id": 1
    },

    # Złożony polygon (10 points):
    {
      "segmentation": [[x1,y1, x2,y2, ..., x10,y10]],
      "area": 15000.0,
      "bbox": [x, y, w, h],
      "category_id": 1
    },

    # RLE mask (dla very complex shapes):
    {
      "segmentation": {
        "counts": [272, 2, 4, 4, ...],
        "size": [480, 640]
      },
      "area": 16000.0,
      "bbox": [x, y, w, h],
      "category_id": 1
    }
  ]
}
```

**3 różne formaty w tym samym datasecie** - oficjalnie wspierane przez COCO!

Przykłady realnych datasetów:
- **COCO 2017**: Mieszanka prostych i złożonych polygonów dla tych samych klas
- **LVIS** (Large Vocabulary Instance Segmentation): 1000+ klas, różne formaty
- **ADE20K**: Sceny z mieszanką prostych i złożonych annotacji

---

### Mit #5: "Musisz konwertować wszystko do jednego formatu"

**Claim** (niepotrzebny overhead):
> "Przed trenowaniem musisz wszystkie rectangles przekonwertować do polygonów (lub odwrotnie)."

**Rzeczywistość**:
Ultralytics (YOLOv8) robi to **automatycznie** podczas wczytywania danych!

```python
# Twój COCO JSON:
{
  "segmentation": [[100, 100, 200, 100, 200, 150, 100, 150]]  # 4 lub 8 punktów
}

# Ultralytics automatycznie:
1. Wczytuje polygon (dowolna liczba punktów) ✅
2. Rasteryzuje do maski ✅
3. Stosuje augmentacje (rotacje, flips) ✅
4. Feeduje do modelu ✅

# Ty nie musisz robić NIC! 🎉
```

**Jedyny wyjątek**: Jeśli używasz YOLOv8-OBB (pure oriented boxes), musisz:
- Rectangles → keep as OBB
- Polygons → convert to minimal rotated rectangle (lub odrzuć)

Ale dla YOLOv8-seg (instance segmentation) - **zero konwersji potrzebnej**!

---

### Prawdziwe ryzyka (o których warto wiedzieć):

#### ✅ Ryzyko #1: Niespójna definicja klas
```python
# PROBLEM:
capacitor_1 = {"mask": "body_only"}
capacitor_2 = {"mask": "body_plus_pins"}  # Niespójne!

# ROZWIĄZANIE:
# Zdefiniuj jasne zasady w annotation_guidelines.md:
# "Capacitors: body only, exclude pins and polarity marks"
```

#### ✅ Ryzyko #2: Różne poziomy precyzji
```python
# PROBLEM:
resistor_1 = {"mask": "very_tight"}      # 99% accurate
resistor_2 = {"mask": "loose_with_20%_background"}  # Sloppy!

# ROZWIĄZANIE:
# Quality control: reject annotations with >10% empty space
# Użyj quality flags: mark "noisy" cases
```

#### ✅ Ryzyko #3: Brak walidacji
```python
# PROBLEM:
# Annotator myli klasy (resistor ← capacitor)
# Brak sprawdzenia przed trenowaniem

# ROZWIĄZANIE:
# scripts/validate_annotations.py:
- Check każda annotacja ma valid class
- Check bounding box w granicach obrazu
- Check brak overlappingów (jeśli niepożądane)
- Inter-annotator agreement na próbce
```

---

### � Studium przypadku: Nasza implementacja

**Dlaczego nasz hybrid approach jest optymalny:**

```python
# Statystyki po 600 annotacjach (zakładane):
{
  "total": 10000,
  "rectangles": 8500,  # 85% - proste przypadki
  "polygons": 1500,    # 15% - edge cases

  "average_time": {
    "rectangle": 12,  # sekund
    "polygon": 35     # sekund
  },

  "total_time": (8500 * 12 + 1500 * 35) / 3600,  # = 42.9 godzin

  # Gdyby TYLKO polygons:
  "alternative_time": (10000 * 35) / 3600,  # = 97.2 godzin ❌

  # Oszczędność czasu: 54.3 godziny! �🎉
}
```

**Korzyści z hybrydowego podejścia:**
1. ⚡ **50%+ szybsze** anotacje niż pure polygons
2. 🎯 **Lepszy model** - uczy się łatwych + trudnych przypadków
3. 💪 **Robustness** - model radzi sobie z różnorodnymi kształtami
4. 🔄 **Elastyczność** - możesz dodać więcej polygonów gdzie potrzeba

---

## 🎯 Finalna odpowiedź na mit Gemini

**Pytanie**: "Czy można mieszać rectangles z polygonami?"

**Gemini powiedział**: ❌ NIE, to spowoduje problemy z treningiem

**Prawda**: ✅ TAK, to jest STANDARD w przemyśle i często POPRAWIA wyniki!

**Dowody**:
1. Microsoft COCO - oficjalnie wspiera mixed formats
2. Tesla/Waymo autonomous driving - mieszają bboxes, polygons, polylines
3. Medical imaging - proste + złożone kształty w jednym datasecie
4. Ultralytics dokumentacja - explicit support dla mixed annotations

**Twoja strategia** (rectangles 80% + polygons 20%) jest **perfekcyjna** i zgodna z best practices branżowymi! 🏆

---

## 🎓 Dodatkowe Porady

### Statystyki do śledzenia podczas anotacji:
```python
# scripts/annotation_stats.py
{
  "total_annotations": 1000,
  "by_method": {
    "rotated_rectangle": 850,  # 85%
    "polygon": 150              # 15%
  },
  "by_quality": {
    "clean": 800,    # 80%
    "noisy": 150,    # 15%
    "uncertain": 50  # 5%
  },
  "avg_polygon_points": 5.2,
  "avg_annotation_time_sec": {
    "rectangle": 12,
    "polygon": 35
  }
}
```

**Idealna dystrybucja:**
- Rectangles: 75-90%
- Polygons: 10-25%
- Polygon points: 4-8 średnio (im mniej tym lepiej)

### Inter-annotator Agreement Test:
1. Wybierz 50 trudnych schematów
2. 2-3 annotatorów zaznacza niezależnie
3. Oblicz IoU między annotacjami
4. **Target**: IoU > 0.80 dla rectangles, IoU > 0.75 dla polygons

### Quality Audit (co 100 annotacji):
```bash
# Sprawdź czy:
- Rectangles są naprawdę tight (nie >20% pustej przestrzeni)
- Polygons mają sensowny powód (nie używane z lenistwa)
- Kąty rotacji są sensowne (wielokrotności 45° gdy możliwe)
- Nie ma duplikatów/overlappingów
```
