# Wizualizacja: Jak model "widzi" różne formaty annotacji

## 🎨 Pipeline konwersji

```
┌─────────────────────────────────────────────────────────────┐
│              LABEL STUDIO (Co TY widzisz)                   │
└─────────────────────────────────────────────────────────────┘

    ┌──────────────────┐         ┌──────────────────┐
    │  Rotated Rect    │         │     Polygon      │
    │                  │         │                  │
    │     ┌─────┐      │         │    ╱╲  ╱╲       │
    │    ╱     ╱       │         │   ╱  ╲╱  ╲      │
    │   ╱  R  ╱  45°   │         │  │    R    │     │
    │  └─────┘         │         │   ╲  ╱╲  ╱      │
    │                  │         │    ╲╱  ╲╱       │
    │  type: rectangle │         │  type: polygon   │
    │  rotation: 45°   │         │  points: 8       │
    └──────────────────┘         └──────────────────┘
            │                            │
            │                            │
            ▼                            ▼
┌─────────────────────────────────────────────────────────────┐
│           KONWERSJA (export_labelstudio_to_coco.py)         │
└─────────────────────────────────────────────────────────────┘
            │                            │
            │   Rotate & extract         │   Extract
            │   corner points            │   points
            │                            │
            ▼                            ▼
    ┌──────────────────┐         ┌──────────────────┐
    │  4-point polygon │         │  8-point polygon │
    │                  │         │                  │
    │   [x1,y1, x2,y2, │         │ [x1,y1, x2,y2,   │
    │    x3,y3, x4,y4] │         │  ..., x8,y8]     │
    └──────────────────┘         └──────────────────┘
            │                            │
            └────────────┬───────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         COCO JSON (Format pośredni)                         │
└─────────────────────────────────────────────────────────────┘

    {
      "annotations": [
        {
          "segmentation": [[100,80, 130,100, 150,120, 120,140]],
          "category_id": 1,  # resistor
          "bbox": [100, 80, 50, 60]
        },
        {
          "segmentation": [[200,100, 220,95, 250,100, ...]],
          "category_id": 1,  # resistor
          "bbox": [200, 95, 60, 65]
        }
      ]
    }

                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         ULTRALYTICS DATALOADER (Rasteryzacja)               │
└─────────────────────────────────────────────────────────────┘
                         │
        cv2.fillPoly() dla każdego poligonu
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         BINARY MASKS (Co MODEL widzi)                       │
└─────────────────────────────────────────────────────────────┘

    ┌──────────────────┐         ┌──────────────────┐
    │  Maska 1         │         │  Maska 2         │
    │                  │         │                  │
    │  0 0 0 1 1 1 0   │         │  0 0 0 0 1 1 0   │
    │  0 0 1 1 1 1 1   │         │  0 0 1 1 1 1 1   │
    │  0 1 1 1 1 1 0   │         │  0 1 1 1 1 1 1   │
    │  1 1 1 1 1 0 0   │         │  1 1 1 1 1 1 0   │
    │  1 1 1 0 0 0 0   │         │  0 1 1 1 1 0 0   │
    │                  │         │  0 0 1 1 0 0 0   │
    │  (4-pt → mask)   │         │  (8-pt → mask)   │
    └──────────────────┘         └──────────────────┘
            │                            │
            └────────────┬───────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              YOLOV8-SEG MODEL                               │
│                                                             │
│  Input:  Image (H × W × 3)                                 │
│  Target: Mask  (H × W) ← OBA WYGLĄDAJĄ TAK SAMO!           │
│                                                             │
│  Model NIE widzi różnicy między źródłem!                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔬 Szczegóły: Co dzieje się na każdym etapie

### Etap 1: Label Studio
**Ty operujesz na:**
- Narzędziach (Rectangle, Polygon)
- Wizualnej reprezentacji
- Intuicyjnych kontrolkach (rotate, resize)

**Format zapisu:**
```json
// Rectangle:
{
  "type": "rectanglelabels",
  "value": {
    "x": 10, "y": 10, "width": 30, "height": 20,  // % of image
    "rotation": 45,
    "rectanglelabels": ["resistor"]
  }
}

// Polygon:
{
  "type": "polygonlabels",
  "value": {
    "points": [[10,10], [40,12], [38,30], [8,28]],  // % of image
    "polygonlabels": ["resistor"]
  }
}
```

---

### Etap 2: Konwersja do COCO
**Skrypt**: `export_labelstudio_to_coco_seg.py`

**Co się dzieje:**
```python
# Rectangle → 4-corner polygon:
def rotated_rect_to_polygon(x, y, w, h, angle):
    # 1. Oblicz środek
    cx, cy = x + w/2, y + h/2

    # 2. Zdefiniuj 4 rogi (przed rotacją)
    corners = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]

    # 3. Obróć każdy róg wokół środka
    rotated = []
    for dx, dy in corners:
        x_rot = cx + (dx * cos(angle) - dy * sin(angle))
        y_rot = cy + (dx * sin(angle) + dy * cos(angle))
        rotated.extend([x_rot, y_rot])

    return rotated  # [x1,y1, x2,y2, x3,y3, x4,y4]

# Polygon → już jest listą punktów:
def polygon_to_segmentation(points):
    return [coord for point in points for coord in point]
    # [[x1,y1], [x2,y2], ...] → [x1,y1, x2,y2, ...]
```

**Wynik**: Jednolity format COCO (wszystko jako poligony)

---

### Etap 3: Dataloader (Ultralytics)
**Co się dzieje podczas wczytywania:**
```python
# ultralytics/data/dataset.py (uproszczone)

def load_annotation(annotation):
    # 1. Wczytaj polygon points
    segmentation = annotation["segmentation"][0]  # [x1,y1, x2,y2, ...]

    # 2. Reshape do listy punktów
    points = np.array(segmentation).reshape(-1, 2)  # [[x1,y1], [x2,y2], ...]

    # 3. Rasteryzuj do maski
    mask = np.zeros((img_height, img_width), dtype=np.uint8)
    cv2.fillPoly(mask, [points.astype(np.int32)], 1)

    # 4. Zastosuj augmentacje (rotation, flip, crop, etc.)
    mask = augment(mask)

    return mask  # Binary mask (H × W)
```

**Kluczowy punkt**: `cv2.fillPoly()` działa IDENTYCZNIE dla 4-point i 8-point polygonów!

---

### Etap 4: Trenowanie modelu
**Co widzi model:**
```python
# Forward pass:
for batch in dataloader:
    images = batch["images"]     # Tensor (B, 3, H, W) - obrazy RGB
    masks = batch["masks"]       # Tensor (B, H, W)    - maski binarne

    # Model przewiduje:
    predictions = model(images)  # → Predicted masks

    # Loss function:
    loss = binary_cross_entropy(predictions, masks)

    # Backward pass:
    loss.backward()
    optimizer.step()

# Model NIE MA DOSTĘPU DO:
# - Liczby punktów poligonu
# - Kąta rotacji
# - Typu narzędzia
# - Metadanych
```

**Model uczy się mapowania**: `pixels → mask`, nic więcej!

---

## 🎯 Kluczowy wniosek

```
┌─────────────────────────────────────────────────────────────┐
│                    SEPARATION OF CONCERNS                    │
└─────────────────────────────────────────────────────────────┘

  ANNOTATION LAYER (Label Studio)
  ↓ Conversion
  DATA LAYER (COCO JSON)
  ↓ Rasterization
  TRAINING LAYER (Binary Masks)

  MODEL WIDZI TYLKO: Training Layer
  MODEL NIE WIDZI: Annotation Layer, Data Layer details
```

**To jak warstwy w sieci:**
- **HTTP** nie dba o to czy używasz WiFi czy Ethernet
- **Python** nie dba o to czy piszesz w Vim czy VS Code
- **Model** nie dba o to czy użyłeś Rectangle czy Polygon

**Każda warstwa ma swoją abstrakcję!** 🎉

---

## 📊 Porównanie: 4-point vs 8-point polygon

### Po rasteryzacji do maski:

```
Original shape (both approximate same resistor):

4-point (from rectangle):    8-point (from polygon):
      ╱────╲                       ╱╲  ╱╲
     ╱      ╲                     ╱  ╲╱  ╲
    ╱   R    ╲                   │    R    │
   ╱          ╲                   ╲  ╱╲  ╱
  ╱────────────╲                   ╲╱  ╲╱

After cv2.fillPoly() → BOTH become:

    Pixel mask (H × W):
    0 0 0 1 1 1 1 0 0
    0 0 1 1 1 1 1 1 0
    0 1 1 1 1 1 1 1 1
    1 1 1 1 1 1 1 1 0
    0 1 1 1 1 1 1 0 0
    0 0 1 1 1 1 0 0 0

IoU between masks: ~0.95 (bardzo podobne!)
```

**Wniosek**: Dla modelu różnica jest minimalna - obie maski reprezentują "rezystor"!

---

## 🧪 Eksperyment myślowy

**Co by się stało gdyby model "wiedział" o formacie?**

```python
# Hipotetyczny (NIE PRAWDZIWY) kod:

def broken_model(image, annotation_metadata):
    # ❌ ZŁY MODEL (nie tak działa):
    if annotation_metadata["type"] == "rectangle":
        return predict_with_rectangle_bias(image)
    else:
        return predict_with_polygon_bias(image)

# To nie ma sensu! Model operuje na PIKSELACH, nie metadanych!

# ✅ PRAWDZIWY MODEL:
def real_model(image):
    features = extract_features(image)  # CNN layers
    mask = decode_segmentation(features)  # Decoder
    return mask  # No metadata needed!
```

**Model jest funkcją TYLKO obrazu**, nie annotacji!

---

## 💡 Finalna analogia

Wyobraź sobie restaurację:

```
┌─────────────────────────────────────────────┐
│  SZEF KUCHNI (Model)                        │
│                                             │
│  Dostaje: Talerz z jedzeniem (Image)       │
│  Zwraca: "To jest pizza" (Prediction)      │
│                                             │
│  NIE wie:                                   │
│  - Czy pizzę zamówiono przez telefon 📞    │
│  - Czy przez aplikację 📱                   │
│  - Czy na miejscu 🏪                        │
│                                             │
│  Szef ocenia TYLKO smak i wygląd!          │
└─────────────────────────────────────────────┘
```

Tak samo:
- **Model** = Chef
- **Obraz** = Pizza
- **Narzędzie annotacji** = Metoda zamówienia (nieistotna dla oceny!)

---

**Zrozumiałeś? Model jest "ślepy" na metodę annotacji - widzi tylko końcowy rezultat (maskę)!** 🎯
