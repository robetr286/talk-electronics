# Szczegółowy Opis Treningu Modelu YOLOv8 - Dokumentacja Techniczna

## 🎯 Cel i Architektura

### Problem
Segmentacja instancji komponentów elektronicznych (resistor, capacitor, inductor, diode) na syntetycznych schematach.

### Model
**YOLOv8n-seg** (You Only Look Once v8 - nano - segmentation)
- **Architektura:** CSPDarknet53 backbone + PAN neck + Segmentation head
- **Parametry:** 3,264,396 (3.26M)
- **Warstwy:** 151 layers
- **GFLOPs:** 11.5
- **Rozmiar:** ~6.5 MB (.pt file)
- **Framework:** PyTorch 2.9.1 + Ultralytics 8.3.228

---

## 📂 Krok 1: Generowanie Datasetu Syntetycznego

### 1.1 Generator Schematów (`batch_generate.py`)

**Technologia:**
- **PIL (Pillow)** - rendering 2D graphics
- **Random seed control** - reprodukowalność
- **Parametryzacja:** liczba komponentów (5-20), pozycje, rotacje (0-360°)

**Proces:**
```python
for seed in range(start_seed, start_seed + num_schematics):
    np.random.seed(seed)
    schema = create_blank_canvas(800, 600, dpi=300)

    for component_type in ['resistor', 'capacitor', 'inductor', 'diode']:
        position = random_position()
        rotation = random_rotation()
        component = draw_component(component_type, rotation)
        schema.paste(component, position)

        metadata = {
            'bbox': [x, y, width, height],
            'segmentation': polygon_points,
            'rotation': rotation,
            'category': component_type
        }

    schema.save(f'schematic_{seed:03d}.png')
    json.dump(metadata, f'schematic_{seed:03d}.json')
```

**Output:**
- `images_batch3/schematic_251.png` - PNG image (800×600, 300 DPI)
- `annotations_batch3/schematic_251.json` - Per-image metadata

**Parametry generacji:**
```yaml
seed_range: 450-649 (200 schematów)
components_per_image: 5-20 (średnio 12.7)
image_size: 800×600 pixels
dpi: 300
background: białe tło (#FFFFFF)
components:
  - resistor: prostokąt z paskami
  - capacitor: dwie równoległe linie
  - inductor: spirala
  - diode: trójkąt w prostokącie
```

---

### 1.2 Konwersja do COCO Format (`emit_annotations.py`)

**COCO (Common Objects in Context)** - standard format dla object detection/segmentation.

**Struktura COCO JSON:**
```json
{
  "images": [
    {
      "id": 251,
      "file_name": "schematic_251.png",
      "width": 800,
      "height": 600,
      "date_captured": "2025-11-14T19:00:00"
    }
  ],
  "annotations": [
    {
      "id": 5001,
      "image_id": 251,
      "category_id": 1,
      "bbox": [120, 150, 40, 20],           # XYWH format
      "segmentation": [[x1,y1, x2,y2, ...]], # Polygon points
      "area": 800.0,                         # pixels²
      "iscrowd": 0
    }
  ],
  "categories": [
    {"id": 1, "name": "resistor", "supercategory": "component"},
    {"id": 2, "name": "capacitor", "supercategory": "component"},
    {"id": 3, "name": "inductor", "supercategory": "component"},
    {"id": 4, "name": "diode", "supercategory": "component"}
  ]
}
```

**Proces konwersji:**
```python
coco_data = {'images': [], 'annotations': [], 'categories': [...]}
annotation_id = 1

for json_file in glob('annotations_batch3/*.json'):
    metadata = json.load(open(json_file))

    # Dodaj obraz
    image_entry = {
        'id': image_id,
        'file_name': f'schematic_{image_id}.png',
        'width': metadata['width'],
        'height': metadata['height']
    }
    coco_data['images'].append(image_entry)

    # Dodaj anotacje komponentów
    for component in metadata['components']:
        annotation = {
            'id': annotation_id,
            'image_id': image_id,
            'category_id': category_map[component['type']],
            'bbox': component['bbox'],
            'segmentation': [component['polygon']],
            'area': compute_area(component['polygon'])
        }
        coco_data['annotations'].append(annotation)
        annotation_id += 1

json.dump(coco_data, open('coco_batch3.json', 'w'))
```

**Output:** `coco_batch3.json` (1.3 MB)
- 200 images
- 2547 annotations
- 4 categories

---

### 1.3 Merge Zbiorów Danych (`merge_annotations.py`)

**Problem:** Łączenie wielu zbiorów COCO z zachowaniem unikalnych ID.

**ID Remapping:**
```python
def merge_coco_datasets(files):
    merged = {'images': [], 'annotations': [], 'categories': []}

    next_image_id = 1
    next_annotation_id = 1
    next_category_id = 1

    old_to_new_image_id = {}
    old_to_new_category_id = {}

    for coco_file in files:
        data = json.load(open(coco_file))

        # Remap image IDs
        for img in data['images']:
            old_id = img['id']
            img['id'] = next_image_id
            old_to_new_image_id[old_id] = next_image_id
            merged['images'].append(img)
            next_image_id += 1

        # Remap category IDs (deduplikacja po nazwie)
        for cat in data['categories']:
            if cat['name'] not in [c['name'] for c in merged['categories']]:
                cat['id'] = next_category_id
                old_to_new_category_id[cat['id']] = next_category_id
                merged['categories'].append(cat)
                next_category_id += 1

        # Remap annotation IDs + image_id + category_id
        for ann in data['annotations']:
            ann['id'] = next_annotation_id
            ann['image_id'] = old_to_new_image_id[ann['image_id']]
            ann['category_id'] = old_to_new_category_id[ann['category_id']]
            merged['annotations'].append(ann)
            next_annotation_id += 1

    return merged
```

**Problem napotkany:** Duplicate filenames
- `coco_fixed_200.json` zawiera `schematic_001-150.png`
- `coco_batch3.json` zawiera `schematic_001-200.png`
- **Kolizja:** 150 plików o tych samych nazwach

**Rozwiązanie:** `renumber_batch3.py`
```python
# Offset wszystkich ID i nazw plików
OFFSET = 250

for img in coco_batch3['images']:
    old_filename = img['file_name']  # schematic_042.png
    old_num = int(old_filename.replace('schematic_', '').replace('.png', ''))
    new_num = old_num + OFFSET  # 42 -> 292
    new_filename = f'schematic_{new_num:03d}.png'

    # Zmień nazwę w JSON
    img['file_name'] = new_filename
    img['id'] += OFFSET

    # Zmień fizyczną nazwę pliku
    os.rename(f'images_batch3/{old_filename}',
              f'images_batch3/{new_filename}')

# Zaktualizuj image_id w annotations
for ann in coco_batch3['annotations']:
    ann['image_id'] += OFFSET
```

**Output po merge:** `coco_v2_400_fixed.json`
- 400 images (1-150 + 251-450)
- 6227 annotations
- 4 categories

---

## ✂️ Krok 2: Stratified Dataset Split

### 2.1 Podział Train/Val/Test (`split_dataset.py`)

**Algorytm:** Stratified sampling z zachowaniem proporcji klas.

**Mathematyka:**
```
Total images: N = 400
Train ratio: r_train = 0.70 → N_train = 280
Val ratio: r_val = 0.15 → N_val = 60
Test ratio: r_test = 0.15 → N_test = 60
```

**Stratyfikacja per kategoria:**
```python
from sklearn.model_selection import train_test_split

# Grupuj obrazy po liczbie instancji każdej klasy
image_class_counts = {}
for img in coco['images']:
    img_id = img['id']
    counts = defaultdict(int)
    for ann in coco['annotations']:
        if ann['image_id'] == img_id:
            counts[ann['category_id']] += 1
    image_class_counts[img_id] = counts

# Stratyfikuj po dominującej klasie
y_stratify = [max(counts.items(), key=lambda x: x[1])[0]
              for counts in image_class_counts.values()]

# Split z zachowaniem proporcji
train_imgs, test_val_imgs, _, y_temp = train_test_split(
    coco['images'], y_stratify,
    train_size=0.70, stratify=y_stratify, random_state=42
)

val_imgs, test_imgs = train_test_split(
    test_val_imgs,
    test_size=0.5,  # 15/30 = 0.5
    stratify=y_temp, random_state=42
)
```

**Statystyki per split:**
```
TRAIN (280 images, 4375 annotations):
  - resistor:  1119 (25.6%)
  - capacitor: 1074 (24.5%)
  - inductor:  1110 (25.4%)
  - diode:     1072 (24.5%)

VAL (60 images, 956 annotations):
  - resistor:  274 (28.7%)
  - capacitor: 206 (21.5%)
  - inductor:  239 (25.0%)
  - diode:     237 (24.8%)

TEST (60 images, 896 annotations):
  - resistor:  218 (24.3%)
  - capacitor: 239 (26.7%)
  - inductor:  223 (24.9%)
  - diode:     216 (24.1%)
```

**Balans klas:** Doskonały (24-29% per klasa w każdym split)

---

### 2.2 Konwersja do YOLO Format

**YOLO Format** - prostszy niż COCO, jeden plik `.txt` per obraz.

**Format pliku label:**
```
# schematic_001.txt (normalized coordinates)
<class_id> <x_center> <y_center> <width> <height> <seg_x1> <seg_y1> <seg_x2> <seg_y2> ...

Przykład:
0 0.45 0.52 0.08 0.04 0.41 0.50 0.43 0.50 0.45 0.52 0.47 0.54 0.49 0.54
^class  ^bbox(normalized)    ^segmentation polygon (normalized)
```

**Normalizacja:**
```python
def bbox_to_yolo(bbox, img_width, img_height):
    x, y, w, h = bbox  # COCO format (top-left x, y, width, height)

    # Konwersja do center-based
    x_center = (x + w/2) / img_width
    y_center = (y + h/2) / img_height
    width = w / img_width
    height = h / img_height

    return [x_center, y_center, width, height]

def segmentation_to_yolo(polygon, img_width, img_height):
    # Polygon: [x1, y1, x2, y2, ..., xn, yn]
    normalized = []
    for i in range(0, len(polygon), 2):
        x_norm = polygon[i] / img_width
        y_norm = polygon[i+1] / img_height
        normalized.extend([x_norm, y_norm])
    return normalized
```

**Struktura katalogów:**
```
data/synthetic/splits_yolo/
├── train/
│   ├── images/
│   │   ├── schematic_001.png
│   │   ├── schematic_002.png
│   │   └── ... (280 total)
│   └── labels/
│       ├── schematic_001.txt
│       ├── schematic_002.txt
│       └── ... (280 total)
├── val/
│   ├── images/ (60 images)
│   └── labels/ (60 labels)
└── test/
    ├── images/ (60 images)
    └── labels/ (60 labels)
```

---

## 🧠 Krok 3: Architektura Modelu YOLOv8-seg

### 3.1 Struktura Sieci

**Backbone: CSPDarknet53**
```
Input: 640×640×3 RGB image

Stem:
  Conv(3→16, k=3, s=2) → 320×320×16
  Conv(16→32, k=3, s=2) → 160×160×32

Stage 1:
  C2f(32→32, n=1) → 160×160×32

Stage 2:
  Conv(32→64, k=3, s=2) → 80×80×64
  C2f(64→64, n=2) → 80×80×64

Stage 3:
  Conv(64→128, k=3, s=2) → 40×40×128
  C2f(128→128, n=2) → 40×40×128

Stage 4:
  Conv(128→256, k=3, s=2) → 20×20×256
  C2f(256→256, n=1) → 20×20×256

SPPF(256→256, k=5) → 20×20×256
```

**C2f Block** (CSP Bottleneck with 2 convolutions):
```python
class C2f(nn.Module):
    def __init__(self, c_in, c_out, n=1):
        self.cv1 = Conv(c_in, c_out, 1)  # 1×1 conv
        self.cv2 = Conv(c_in, c_out, 1)
        self.m = nn.Sequential(*[Bottleneck(c_out) for _ in range(n)])
        self.cv3 = Conv(2*c_out, c_out, 1)  # Concat + compress

    def forward(self, x):
        y1 = self.cv1(x)
        y2 = self.cv2(x)
        y2 = self.m(y2)
        return self.cv3(torch.cat([y1, y2], dim=1))
```

**SPPF (Spatial Pyramid Pooling - Fast):**
```python
class SPPF(nn.Module):
    def __init__(self, c_in, c_out, k=5):
        self.cv1 = Conv(c_in, c_out // 2, 1)
        self.cv2 = Conv(c_out * 2, c_out, 1)
        self.m = nn.MaxPool2d(kernel_size=k, stride=1, padding=k // 2)

    def forward(self, x):
        x = self.cv1(x)
        y1 = self.m(x)
        y2 = self.m(y1)
        y3 = self.m(y2)
        return self.cv2(torch.cat([x, y1, y2, y3], dim=1))
```

**Neck: PAN (Path Aggregation Network)**
```
# Upsampling path
P5 (20×20×256) → Upsample → 40×40×256
P5 + P4 (40×40×128) → Concat → 40×40×384 → C2f → 40×40×128

P4 (40×40×128) → Upsample → 80×80×128
P4 + P3 (80×80×64) → Concat → 80×80×192 → C2f → 80×80×64

# Downsampling path
P3 (80×80×64) → Conv → 40×40×64
P3 + P4 → Concat → 40×40×192 → C2f → 40×40×128

P4 (40×40×128) → Conv → 20×20×128
P4 + P5 → Concat → 20×20×384 → C2f → 20×20×256
```

**Head: Segment Head**
```
3 output scales: P3 (80×80), P4 (40×40), P5 (20×20)

Per scale:
  Detection branch:
    - Classification: 4 classes (resistor, capacitor, inductor, diode)
    - Bounding box: 4 coordinates (x, y, w, h)
    - Objectness: 1 score

  Segmentation branch:
    - Proto masks: 32 prototype masks per image (160×160)
    - Mask coefficients: 32 weights per detection

Final mask = Linear combination of proto masks:
  mask = Σ(coeff_i × proto_mask_i)
```

---

### 3.2 Transfer Learning - Pretrained Weights

**YOLOv8n-seg.pt (pretrained on COCO):**
- Wytrenowany na **COCO dataset** (80 klas: person, car, dog, etc.)
- 118k obrazów treningowych
- Zawiera ogólne feature extractors (krawędzie, tekstury, kształty)

**Fine-tuning process:**
```python
# Wczytaj pretrained model
model = YOLO('yolov8n-seg.pt')

# Wymiana classification head (80→4 klasy)
model.model[-1] = SegmentHead(nc=4, ...)

# Częściowe zamrożenie
# Layers 0-21: freeze (feature extraction - już nauczone)
# Layer 22 (head): train from scratch (nowe klasy)

for i, layer in enumerate(model.model):
    if i < 22:
        for param in layer.parameters():
            param.requires_grad = False
```

**Dlaczego to działa?**
- **Low-level features** (krawędzie, linie) są uniwersalne
- **Mid-level features** (kształty, wzorce) przenoszą się dobrze
- **High-level features** (konkretne obiekty) wymagają fine-tuningu

---

## 🏋️ Krok 4: Trening (Fine-tuning)

### 4.1 Hyperparameters

**Baseline Config:**
```yaml
# Model & Data
model: yolov8n-seg.pt (pretrained)
data: configs/yolov8_splits_200.yaml
task: segment
nc: 4  # number of classes

# Training
epochs: 50
batch: 16
imgsz: 640  # image size
device: cpu  # lub cuda:0

# Optimizer (auto-selected: AdamW)
lr0: 0.01      # initial learning rate
lrf: 0.01      # final learning rate (lr0 * lrf)
momentum: 0.9  # SGD momentum / Adam beta1
weight_decay: 0.0005

# Learning rate schedule (Cosine annealing)
warmup_epochs: 3.0
warmup_momentum: 0.8
warmup_bias_lr: 0.1

# Loss weights
box: 7.5       # box loss gain
cls: 0.5       # classification loss gain
dfl: 1.5       # distribution focal loss gain
```

**Heavy Augmentations Config:**
```yaml
# Geometric augmentations
degrees: 15.0      # rotation ±15° (baseline: 7.0)
shear: 5.0         # shear ±5° (baseline: 0.0)
translate: 0.1     # translation ±10%
scale: 0.5         # scale 0.5-1.5x
perspective: 0.0   # perspective transform (disabled)

# Flip augmentations
fliplr: 0.5        # horizontal flip 50%
flipud: 0.5        # vertical flip 50% (baseline: 0.0)

# Color augmentations
hsv_h: 0.015       # hue ±1.5%
hsv_s: 0.7         # saturation ±70%
hsv_v: 0.4         # value/brightness ±40%

# Mosaic & mixup
mosaic: 1.0        # mosaic 4-images (zawsze włączone)
mixup: 0.0         # mixup (wyłączone dla segmentacji)
copy_paste: 0.0    # copy-paste augmentation (wyłączone)

# Advanced augmentations (via albumentations)
auto_augment: randaugment
- Blur(p=0.01)
- MedianBlur(p=0.01)
- ToGray(p=0.01)
- CLAHE(p=0.01)
```

---

### 4.2 Data Augmentation Pipeline

**Mosaic Augmentation:**
```python
def mosaic_augmentation(images, labels):
    """Łączy 4 obrazy w jeden"""
    h, w = 640, 640
    mosaic_img = np.full((h, w, 3), 114, dtype=np.uint8)  # Gray background

    # Losowy punkt przecięcia
    xc, yc = [int(random.uniform(w*0.25, w*0.75)) for _ in range(2)]

    indices = random.sample(range(len(images)), 4)

    for i, idx in enumerate(indices):
        img = images[idx]

        # Placement (4 quadrants)
        if i == 0:  # top left
            x1a, y1a, x2a, y2a = max(xc - w, 0), max(yc - h, 0), xc, yc
        elif i == 1:  # top right
            x1a, y1a, x2a, y2a = xc, max(yc - h, 0), min(xc + w, w), yc
        elif i == 2:  # bottom left
            x1a, y1a, x2a, y2a = max(xc - w, 0), yc, xc, min(yc + h, h)
        elif i == 3:  # bottom right
            x1a, y1a, x2a, y2a = xc, yc, min(xc + w, w), min(yc + h, h)

        # Crop & paste
        mosaic_img[y1a:y2a, x1a:x2a] = img[...]

        # Adjust labels (bbox & segmentation)
        labels[idx] = adjust_labels(labels[idx], x1a, y1a, x2a, y2a)

    return mosaic_img, concatenate(labels)
```

**Affine Transform:**
```python
def apply_affine_transform(img, labels, degrees, scale, shear, translate):
    """Geometric transformations"""
    h, w = img.shape[:2]

    # Random parameters
    angle = random.uniform(-degrees, degrees)
    scale_factor = random.uniform(1-scale, 1+scale)
    shear_x = random.uniform(-shear, shear)
    translate_x = random.uniform(-translate, translate) * w
    translate_y = random.uniform(-translate, translate) * h

    # Build transformation matrix
    center = (w / 2, h / 2)
    M = cv2.getRotationMatrix2D(center, angle, scale_factor)
    M[0, 2] += translate_x  # x translation
    M[1, 2] += translate_y  # y translation

    # Add shear
    M_shear = np.array([
        [1, math.tan(math.radians(shear_x)), 0],
        [0, 1, 0]
    ])
    M = M @ M_shear

    # Apply to image
    img_aug = cv2.warpAffine(img, M, (w, h),
                              borderMode=cv2.BORDER_CONSTANT,
                              borderValue=(114, 114, 114))

    # Apply to labels (bbox + segmentation points)
    for label in labels:
        label['bbox'] = transform_bbox(label['bbox'], M)
        label['segmentation'] = transform_polygon(label['segmentation'], M)

    return img_aug, labels
```

---

### 4.3 Loss Functions

**Multi-task Loss:**
```
L_total = λ_box * L_box + λ_cls * L_cls + λ_dfl * L_dfl + λ_seg * L_seg

gdzie:
  λ_box = 7.5
  λ_cls = 0.5
  λ_dfl = 1.5
  λ_seg = 1.0 (implicit)
```

**1. Box Loss (CIoU Loss):**
```python
def ciou_loss(pred_box, target_box):
    """Complete IoU Loss"""
    # IoU (Intersection over Union)
    iou = compute_iou(pred_box, target_box)

    # Distance between centers
    center_dist = torch.sum((pred_center - target_center) ** 2)

    # Diagonal length of enclosing box
    c = torch.sum((enclose_x2 - enclose_x1) ** 2) + \
        torch.sum((enclose_y2 - enclose_y1) ** 2)

    # Aspect ratio consistency
    v = (4 / math.pi**2) * torch.pow(
        torch.atan(target_w / target_h) - torch.atan(pred_w / pred_h), 2
    )
    alpha = v / (1 - iou + v + 1e-7)

    # CIoU = IoU - (distance penalty) - (aspect ratio penalty)
    ciou = iou - (center_dist / c) - alpha * v

    return 1 - ciou  # Loss (minimize)
```

**2. Classification Loss (BCE Loss):**
```python
def bce_loss(pred_cls, target_cls):
    """Binary Cross Entropy dla multi-class"""
    # pred_cls: [batch, num_anchors, num_classes]
    # target_cls: [batch, num_anchors, num_classes] (one-hot)

    loss = -target_cls * torch.log(pred_cls + 1e-7) \
           - (1 - target_cls) * torch.log(1 - pred_cls + 1e-7)

    return loss.mean()
```

**3. DFL Loss (Distribution Focal Loss):**
```python
def dfl_loss(pred_dist, target):
    """Distribution Focal Loss - modeluje bbox jako rozkład prawdopodobieństwa"""
    # Zamiast regresji punktowej (x, y, w, h),
    # modelujemy rozkład wokół prawdziwej wartości

    target_left = target.long()
    target_right = target_left + 1
    weight_left = target_right.float() - target
    weight_right = 1 - weight_left

    loss_left = F.cross_entropy(pred_dist, target_left, reduction='none')
    loss_right = F.cross_entropy(pred_dist, target_right, reduction='none')

    return (loss_left * weight_left + loss_right * weight_right).mean()
```

**4. Segmentation Loss (Mask Loss):**
```python
def mask_loss(pred_masks, target_masks, pred_boxes, target_boxes):
    """Mask loss - tylko wewnątrz bounding boxes"""
    # pred_masks: [batch, 160, 160] (proto masks)
    # mask_coeff: [num_objects, 32] (coefficients)

    # Generuj maski z proto masks
    pred = torch.einsum('ik,khw->ihw', mask_coeff, proto_masks)
    pred = pred.sigmoid()

    # Crop do bounding box (oszczędność obliczeń)
    pred_crop = crop_mask(pred, pred_boxes)
    target_crop = crop_mask(target_masks, target_boxes)

    # Binary Cross Entropy
    loss = F.binary_cross_entropy(pred_crop, target_crop, reduction='mean')

    return loss
```

---

### 4.4 Training Loop

**Pseudo-kod jednej epoki:**
```python
def train_one_epoch(model, train_loader, optimizer, scaler, epoch):
    model.train()
    total_loss = 0

    for batch_idx, (images, labels) in enumerate(train_loader):
        # images: [batch_size, 3, 640, 640]
        # labels: list of dicts with bbox, class, segmentation

        # Forward pass (mixed precision)
        with torch.cuda.amp.autocast():
            predictions = model(images)
            # predictions: (boxes, classes, masks)

            # Compute losses
            loss_box = box_loss(predictions['boxes'], labels['boxes'])
            loss_cls = cls_loss(predictions['classes'], labels['classes'])
            loss_dfl = dfl_loss(predictions['dfl'], labels['boxes'])
            loss_seg = mask_loss(predictions['masks'], labels['masks'])

            total_loss_batch = (7.5 * loss_box +
                                 0.5 * loss_cls +
                                 1.5 * loss_dfl +
                                 1.0 * loss_seg)

        # Backward pass
        optimizer.zero_grad()
        scaler.scale(total_loss_batch).backward()

        # Gradient clipping (prevent explosion)
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=10.0)

        # Optimizer step
        scaler.step(optimizer)
        scaler.update()

        total_loss += total_loss_batch.item()

        # Progress bar
        print(f"Epoch {epoch}/{epochs} | Batch {batch_idx}/{len(train_loader)} | "
              f"Loss: {total_loss_batch:.3f}")

    return total_loss / len(train_loader)
```

**Learning Rate Schedule:**
```python
def get_lr(epoch, epochs, lr0, lrf, warmup_epochs):
    """Cosine annealing with warmup"""
    if epoch < warmup_epochs:
        # Linear warmup
        return lr0 * (epoch / warmup_epochs)
    else:
        # Cosine annealing
        progress = (epoch - warmup_epochs) / (epochs - warmup_epochs)
        return lrf + (lr0 - lrf) * 0.5 * (1 + math.cos(math.pi * progress))

# Przykład dla epochs=50, lr0=0.01, lrf=0.0001, warmup=3:
# Epoch 0: lr = 0.00333
# Epoch 1: lr = 0.00667
# Epoch 3: lr = 0.01000 (peak)
# Epoch 25: lr = 0.00505
# Epoch 50: lr = 0.0001
```

---

### 4.5 Validation Loop

**Wykonywane co epokę:**
```python
@torch.no_grad()
def validate(model, val_loader, conf_thresh=0.001, iou_thresh=0.6):
    model.eval()

    all_predictions = []
    all_targets = []

    for images, labels in val_loader:
        # Forward pass (inference mode)
        predictions = model(images)

        # Post-processing (NMS)
        predictions = non_max_suppression(
            predictions,
            conf_thresh=conf_thresh,
            iou_thresh=iou_thresh
        )

        all_predictions.extend(predictions)
        all_targets.extend(labels)

    # Compute metrics
    metrics = compute_metrics(all_predictions, all_targets)

    return metrics
```

**Non-Maximum Suppression (NMS):**
```python
def non_max_suppression(predictions, conf_thresh, iou_thresh):
    """Usuwa zduplikowane detekcje"""
    output = []

    for pred in predictions:  # Per image
        # Filter by confidence
        pred = pred[pred[:, 4] > conf_thresh]

        # Sort by confidence (descending)
        pred = pred[pred[:, 4].argsort(descending=True)]

        keep = []
        while len(pred) > 0:
            # Keep highest confidence detection
            keep.append(pred[0])

            # Remove detections with high IoU overlap
            ious = bbox_iou(pred[0], pred[1:])
            pred = pred[1:][ious < iou_thresh]

        output.append(torch.stack(keep) if keep else torch.empty(0))

    return output
```

---

### 4.6 Metrics Computation

**Precision & Recall:**
```python
def compute_ap(recalls, precisions):
    """Average Precision (area under PR curve)"""
    # Dodaj sentinel values
    recalls = np.concatenate(([0.0], recalls, [1.0]))
    precisions = np.concatenate(([1.0], precisions, [0.0]))

    # Compute envelope (maksymalna precision dla danego recall)
    for i in range(len(precisions) - 1, 0, -1):
        precisions[i - 1] = max(precisions[i - 1], precisions[i])

    # Compute area (trapezoidal integration)
    indices = np.where(recalls[1:] != recalls[:-1])[0]
    ap = np.sum((recalls[indices + 1] - recalls[indices]) * precisions[indices + 1])

    return ap

def compute_metrics(predictions, targets, iou_thresholds=[0.5, 0.75]):
    """
    predictions: list of [num_det, 6+] (x1, y1, x2, y2, conf, class, ...)
    targets: list of [num_gt, 5+] (x1, y1, x2, y2, class, ...)
    """

    # Grupuj po klasach
    aps = []
    precisions = []
    recalls = []

    for cls in range(num_classes):
        # Filter predictions & targets for this class
        cls_preds = [p[p[:, 5] == cls] for p in predictions]
        cls_targets = [t[t[:, 4] == cls] for t in targets]

        # Dla każdego IoU threshold
        for iou_thresh in iou_thresholds:
            # Compute TP, FP, FN
            tp, fp, fn = [], [], 0

            for pred, target in zip(cls_preds, cls_targets):
                if len(pred) == 0:
                    fn += len(target)
                    continue

                if len(target) == 0:
                    fp.extend([1] * len(pred))
                    continue

                # Compute IoU matrix
                ious = bbox_iou(pred[:, :4], target[:, :4])

                # Matching (Hungarian algorithm lub greedy)
                matches = match_predictions(ious, iou_thresh)

                # Count TP, FP
                tp_mask = matches >= 0
                tp.extend(tp_mask.tolist())
                fp.extend((~tp_mask).tolist())
                fn += len(target) - tp_mask.sum()

            # Compute precision & recall at each confidence threshold
            tp = np.array(tp)
            fp = np.array(fp)
            confidences = np.concatenate([p[:, 4] for p in cls_preds])

            # Sort by confidence
            indices = np.argsort(-confidences)
            tp = tp[indices]
            fp = fp[indices]

            # Cumulative sums
            tp_cumsum = np.cumsum(tp)
            fp_cumsum = np.cumsum(fp)

            # Precision = TP / (TP + FP)
            precision = tp_cumsum / (tp_cumsum + fp_cumsum + 1e-7)

            # Recall = TP / (TP + FN)
            recall = tp_cumsum / (tp_cumsum.sum() + fn + 1e-7)

            # Compute AP
            ap = compute_ap(recall, precision)
            aps.append(ap)

            # Store final precision & recall
            precisions.append(precision[-1])
            recalls.append(recall[-1])

    # mAP = mean over all classes & IoU thresholds
    mAP = np.mean(aps)

    return {
        'precision': np.mean(precisions),
        'recall': np.mean(recalls),
        'mAP@0.5': np.mean([ap for ap, t in zip(aps, iou_thresholds) if t == 0.5]),
        'mAP@0.5-0.95': np.mean(aps)
    }
```

**IoU Computation:**
```python
def bbox_iou(box1, box2):
    """
    box1: [N, 4] (x1, y1, x2, y2)
    box2: [M, 4] (x1, y1, x2, y2)
    returns: [N, M] IoU matrix
    """
    # Intersection area
    x1_inter = torch.max(box1[:, None, 0], box2[:, 0])
    y1_inter = torch.max(box1[:, None, 1], box2[:, 1])
    x2_inter = torch.min(box1[:, None, 2], box2[:, 2])
    y2_inter = torch.min(box1[:, None, 3], box2[:, 3])

    inter_area = (x2_inter - x1_inter).clamp(min=0) * \
                 (y2_inter - y1_inter).clamp(min=0)

    # Union area
    box1_area = (box1[:, 2] - box1[:, 0]) * (box1[:, 3] - box1[:, 1])
    box2_area = (box2[:, 2] - box2[:, 0]) * (box2[:, 3] - box2[:, 1])
    union_area = box1_area[:, None] + box2_area - inter_area

    # IoU
    iou = inter_area / (union_area + 1e-7)

    return iou
```

---

## 📊 Krok 5: Monitoring & Logging

### 5.1 TensorBoard Logging

```python
from torch.utils.tensorboard import SummaryWriter

writer = SummaryWriter(log_dir='runs/segment/heavy_aug_200')

# Per batch
writer.add_scalar('train/loss', loss, global_step)
writer.add_scalar('train/box_loss', box_loss, global_step)
writer.add_scalar('train/cls_loss', cls_loss, global_step)
writer.add_scalar('train/seg_loss', seg_loss, global_step)

# Per epoch
writer.add_scalar('val/mAP@0.5', metrics['mAP@0.5'], epoch)
writer.add_scalar('val/precision', metrics['precision'], epoch)
writer.add_scalar('val/recall', metrics['recall'], epoch)
writer.add_scalar('lr', optimizer.param_groups[0]['lr'], epoch)

# Images (visualizations)
writer.add_image('val/predictions', vis_image, epoch)
```

### 5.2 CSV Results

**Format:** `results.csv`
```csv
epoch,train/box_loss,train/seg_loss,train/cls_loss,train/dfl_loss,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B),metrics/precision(M),metrics/recall(M),metrics/mAP50(M),metrics/mAP50-95(M),val/box_loss,val/seg_loss,val/cls_loss,val/dfl_loss,lr/pg0,lr/pg1,lr/pg2
1,4.431,6.067,4.628,2.461,0.000,0.000,0.000,0.000,0.000,0.000,0.000,0.000,3.892,5.245,3.892,1.985,0.00125,0.00125,0.00125
2,3.487,4.106,4.120,1.673,0.001,0.016,0.001,0.000,0.001,0.015,0.001,0.000,3.245,4.012,3.456,1.723,0.00250,0.00250,0.00250
...
50,0.452,0.823,0.156,0.892,0.861,0.789,0.812,0.625,0.854,0.781,0.805,0.618,0.523,0.912,0.189,0.945,0.0001,0.0001,0.0001
```

### 5.3 Checkpoints

**Model saving:**
```python
# Best model (highest mAP)
if val_mAP > best_mAP:
    best_mAP = val_mAP
    torch.save({
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'mAP': val_mAP,
        'class_names': ['resistor', 'capacitor', 'inductor', 'diode']
    }, 'runs/segment/heavy_aug_200/weights/best.pt')

# Last model (every epoch)
torch.save({...}, 'runs/segment/heavy_aug_200/weights/last.pt')
```

---

## 🔍 Krok 6: Analiza Wyników

### 6.1 Per-Class Performance

**Confusion Matrix:**
```python
from sklearn.metrics import confusion_matrix

def compute_confusion_matrix(predictions, targets, num_classes):
    all_pred_classes = []
    all_true_classes = []

    for pred, target in zip(predictions, targets):
        # Match predictions to targets (IoU > 0.5)
        ious = bbox_iou(pred[:, :4], target[:, :4])
        matches = ious.argmax(dim=1)
        matched = ious.max(dim=1)[0] > 0.5

        # Matched predictions
        pred_matched_classes = pred[matched, 5].int()
        target_matched_classes = target[matches[matched], 4].int()

        all_pred_classes.extend(pred_matched_classes.tolist())
        all_true_classes.extend(target_matched_classes.tolist())

    cm = confusion_matrix(all_true_classes, all_pred_classes,
                          labels=range(num_classes))
    return cm

# Visualize
import matplotlib.pyplot as plt
import seaborn as sns

cm = compute_confusion_matrix(predictions, targets, 4)
plt.figure(figsize=(8, 6))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
            xticklabels=['resistor', 'capacitor', 'inductor', 'diode'],
            yticklabels=['resistor', 'capacitor', 'inductor', 'diode'])
plt.ylabel('True Label')
plt.xlabel('Predicted Label')
plt.savefig('confusion_matrix.png')
```

### 6.2 Error Analysis

**False Negatives (pominięte komponenty):**
```python
def analyze_false_negatives(predictions, targets):
    fn_stats = defaultdict(list)

    for pred, target in zip(predictions, targets):
        # Compute IoU
        if len(pred) == 0:
            # All targets are FN
            for t in target:
                cls = int(t[4])
                fn_stats[cls].append({
                    'area': (t[2] - t[0]) * (t[3] - t[1]),
                    'aspect_ratio': (t[2] - t[0]) / (t[3] - t[1] + 1e-7),
                    'reason': 'no_detection'
                })
            continue

        ious = bbox_iou(pred[:, :4], target[:, :4])
        matched_target = ious.max(dim=0)[0] > 0.5

        # Unmatched targets are FN
        for i, matched in enumerate(matched_target):
            if not matched:
                t = target[i]
                cls = int(t[4])
                fn_stats[cls].append({
                    'area': (t[2] - t[0]) * (t[3] - t[1]),
                    'aspect_ratio': (t[2] - t[0]) / (t[3] - t[1] + 1e-7),
                    'reason': 'low_iou' if ious[:, i].max() > 0 else 'no_overlap'
                })

    # Analyze patterns
    for cls, fns in fn_stats.items():
        areas = [fn['area'] for fn in fns]
        ars = [fn['aspect_ratio'] for fn in fns]

        print(f"Class {cls}:")
        print(f"  False Negatives: {len(fns)}")
        print(f"  Avg area: {np.mean(areas):.1f} px²")
        print(f"  Avg aspect ratio: {np.mean(ars):.2f}")
        print(f"  Small objects (<500px²): {sum(a < 500 for a in areas)}")
```

**Wyniki Baseline:**
```
Class 1 (resistor):
  False Negatives: 89
  Avg area: 1180 px²
  Avg aspect ratio: 1.72
  Small objects: 12 (13.5%)

Class 2 (capacitor):  ← WORST!
  False Negatives: 142
  Avg area: 780 px²
  Avg aspect ratio: 1.15
  Small objects: 45 (31.7%)  ← Many small!

Class 3 (inductor):
  False Negatives: 119
  Avg area: 1210 px²
  Avg aspect ratio: 1.58
  Small objects: 18 (15.1%)

Class 4 (diode):  ← BEST!
  False Negatives: 67
  Avg area: 1620 px²
  Avg aspect ratio: 1.02
  Small objects: 8 (11.9%)
```

**Hipotezy:**
1. **Capacitor:** Małe obiekty + prosty kształt (||) → trudne do wykrycia
2. **Diode:** Duże obiekty + charakterystyczny kształt (▷|) → łatwe
3. **Small objects:** Problem dla wszystkich klas (<500px²)

---

## 💾 Krok 7: Zapisywanie Modeli

### 7.1 Model Serialization

**PyTorch `.pt` format:**
```python
# Full checkpoint
checkpoint = {
    'epoch': 50,
    'model_state_dict': model.state_dict(),  # Wagi wszystkich warstw
    'optimizer_state_dict': optimizer.state_dict(),  # Stan optymalizatora
    'scaler_state_dict': scaler.state_dict(),  # AMP scaler state
    'best_fitness': 0.812,  # mAP@0.5
    'class_names': ['resistor', 'capacitor', 'inductor', 'diode'],
    'ema': ema.state_dict() if ema else None,  # Exponential moving average
    'date': datetime.now().isoformat(),
    'training_args': {
        'epochs': 50,
        'batch_size': 16,
        'lr0': 0.01,
        'augmentations': {'degrees': 15.0, 'shear': 5.0, ...}
    }
}

torch.save(checkpoint, 'runs/segment/heavy_aug_200/weights/best.pt')
```

**Model.state_dict() zawiera:**
```python
{
  'model.0.conv.weight': Tensor(shape=[16, 3, 3, 3]),     # First conv layer
  'model.0.conv.bias': Tensor(shape=[16]),
  'model.0.bn.weight': Tensor(shape=[16]),                # BatchNorm
  'model.0.bn.bias': Tensor(shape=[16]),
  ...
  'model.22.cv2.0.0.conv.weight': Tensor(shape=[...]),    # Head layers
  'model.22.cv2.0.0.conv.bias': Tensor(shape=[...]),
  ...
  # Total: 3,264,396 parameters
}
```

### 7.2 Model Loading (Inference)

```python
# Load checkpoint
checkpoint = torch.load('runs/segment/heavy_aug_200/weights/best.pt')

# Reconstruct model
model = YOLO('yolov8n-seg.yaml')  # Architecture from config
model.load_state_dict(checkpoint['model_state_dict'])
model.eval()

# Inference
img = cv2.imread('test_schematic.png')
img = letterbox(img, new_shape=640)  # Resize with padding
img = img.transpose(2, 0, 1)  # HWC -> CHW
img = torch.from_numpy(img).float() / 255.0

with torch.no_grad():
    predictions = model(img.unsqueeze(0))

# Post-process
predictions = non_max_suppression(predictions, conf_thresh=0.25, iou_thresh=0.6)
```

### 7.3 Export Formats

**ONNX (Open Neural Network Exchange):**
```python
# Export to ONNX (portable format)
dummy_input = torch.randn(1, 3, 640, 640)
torch.onnx.export(
    model,
    dummy_input,
    'yolov8n_seg_electronics.onnx',
    opset_version=12,
    input_names=['images'],
    output_names=['boxes', 'scores', 'classes', 'masks'],
    dynamic_axes={
        'images': {0: 'batch'},
        'boxes': {0: 'batch'},
        'masks': {0: 'batch'}
    }
)

# Inference with ONNX Runtime (faster than PyTorch)
import onnxruntime as ort

session = ort.InferenceSession('yolov8n_seg_electronics.onnx')
outputs = session.run(None, {'images': img_numpy})
```

**TensorRT (GPU optimization):**
```bash
# Konwersja ONNX → TensorRT engine (NVIDIA)
trtexec --onnx=yolov8n_seg_electronics.onnx \
        --saveEngine=yolov8n_seg_electronics.engine \
        --fp16  # Half precision (2x faster)
```

---

## 📈 Krok 8: Porównanie Eksperymentów

### Baseline vs Heavy Augmentations

**Baseline (Trening 1):**
```yaml
Data: 200 images (140 train)
Augmentations:
  - degrees: 7.0
  - shear: 0.0
  - flipud: 0.0
  - mosaic: 1.0

Results (Epoch 50):
  - Precision: 85.5%
  - Recall: 74.9%      ← LOW!
  - mAP@0.5: 80.4%
  - mAP@0.5-95: 61.9%

Per-class Recall:
  - Diode: 87.3%
  - Resistor: 76.2%
  - Inductor: 67.1%
  - Capacitor: 68.8%   ← WORST!

Training time: ~1.4 hours (50 epochs)
```

**Heavy Aug (Trening 2):**
```yaml
Data: 200 images (140 train) - SAME
Augmentations:
  - degrees: 15.0      ← INCREASED
  - shear: 5.0         ← NEW!
  - flipud: 0.5        ← NEW!
  - mosaic: 1.0

Results (Epoch 50):  [PENDING - trening w toku]
  - Precision: TBD
  - Recall: TBD (target: 80-85%)
  - mAP@0.5: TBD
  - mAP@0.5-95: TBD

Training time: ~10-15 minutes (50 epochs) [FASTER! CPU efficient for small dataset]
```

**Hipoteza:**
Mocniejsze augmentacje (szczególnie rotacje i shear) powinny pomóc modelowi generalizować lepiej na:
- Komponenty pod różnymi kątami
- Deformacje perspektywiczne
- Małe komponenty w różnych orientacjach

**Oczekiwany gain:** Recall +5-10% (74.9% → 80-85%)

---

## 🔬 Advanced Topics

### Mixed Precision Training (AMP)

**Automatic Mixed Precision** - używa FP16 tam gdzie możliwe, FP32 gdzie konieczne.

```python
from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()

for images, labels in train_loader:
    optimizer.zero_grad()

    # Forward pass in FP16
    with autocast():
        predictions = model(images)
        loss = compute_loss(predictions, labels)

    # Backward pass (scale gradients to prevent underflow)
    scaler.scale(loss).backward()

    # Unscale gradients before clipping
    scaler.unscale_(optimizer)
    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=10.0)

    # Optimizer step
    scaler.step(optimizer)
    scaler.update()
```

**Benefits:**
- **2x faster training** (GPU)
- **50% less memory** (więcej batch size)
- **Minimal accuracy loss** (<0.1% difference)

---

### EMA (Exponential Moving Average)

**Smooth model weights:**
```python
class ModelEMA:
    def __init__(self, model, decay=0.9999):
        self.model = copy.deepcopy(model).eval()
        self.decay = decay
        self.updates = 0

    def update(self, model):
        with torch.no_grad():
            self.updates += 1
            d = self.decay * (1 - math.exp(-self.updates / 2000))

            # EMA: ema_param = decay * ema_param + (1-decay) * param
            for ema_p, p in zip(self.model.parameters(), model.parameters()):
                ema_p.mul_(d).add_(p, alpha=1-d)

# Usage
ema = ModelEMA(model, decay=0.9999)

for epoch in range(epochs):
    train_one_epoch(model, ...)
    ema.update(model)  # Update EMA weights

    # Validate with EMA model (usually better)
    val_metrics = validate(ema.model, val_loader)
```

**Benefits:**
- **Smoother convergence**
- **Better generalization** (+0.5-1% mAP)
- **More stable predictions**

---

## 📊 Podsumowanie Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. DATA GENERATION                                              │
│    batch_generate.py: 200 PNG + 200 JSON                        │
│    ↓                                                             │
│ 2. COCO CONVERSION                                              │
│    emit_annotations.py: → coco_batch3.json (2547 annotations)   │
│    ↓                                                             │
│ 3. MERGE DATASETS                                               │
│    merge_annotations.py + deduplicate:                          │
│    200 + 200 → coco_v2_400_fixed.json (6227 annotations)        │
│    ↓                                                             │
│ 4. STRATIFIED SPLIT                                             │
│    split_dataset.py: 280 train / 60 val / 60 test              │
│    ↓                                                             │
│ 5. TRAINING                                                     │
│    YOLOv8n-seg: 50 epochs × ~12 sec/epoch = ~10 minutes        │
│    ├─ Data augmentation (degrees, shear, flip, mosaic)         │
│    ├─ Loss: CIoU + BCE + DFL + Mask                           │
│    ├─ Optimizer: AdamW (lr: 0.01 → 0.0001)                    │
│    └─ Validation: mAP, Precision, Recall per epoch             │
│    ↓                                                             │
│ 6. EVALUATION                                                   │
│    - Per-class metrics (confusion matrix)                       │
│    - Error analysis (false negatives, small objects)            │
│    - Visualization (val_batch predictions)                      │
│    ↓                                                             │
│ 7. MODEL SAVE                                                   │
│    best.pt (highest mAP) + last.pt (epoch 50)                  │
│    Format: PyTorch checkpoint (state_dict + metadata)           │
│    ↓                                                             │
│ 8. ITERATION                                                    │
│    Analyze results → Hypothesis → Change hyperparams → Retrain  │
└─────────────────────────────────────────────────────────────────┘
```

**Czasy wykonania (CPU: Intel Core i5-9300HF):**
- Generowanie 200 schematów: ~30 min
- Konwersja + merge + split: ~2 min
- Trening 50 epok: ~10-15 min (small dataset, efficient)
- Analiza wyników: ~5 min
- **Total per iteration: ~50 min**

**Metryki sukcesu:**
- ✅ **Precision >85%** - gdy model coś wykrywa, to prawdopodobnie prawda
- ❌ **Recall <75%** - model pomija ~25% komponentów (PROBLEM!)
- ✅ **mAP@0.5 >80%** - ogólna jakość dobra
- 🎯 **Target: Recall 85%+** (heavy aug experiment)

---

**Autor:** GitHub Copilot + Robert
**Data:** 14 listopada 2025
**Projekt:** Talk_electronic - YOLOv8 Component Segmentation
**Status:** Heavy Augmentations Test (Experiment 2/∞) - In Progress
