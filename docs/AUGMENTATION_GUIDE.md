# Augmentacja Datasetu - Przewodnik

## Co to jest augmentacja?

**Augmentacja danych (data augmentation)** to technika sztucznego zwiększania rozmiaru i różnorodności datasetu treningowego poprzez zastosowanie transformacji do istniejących danych, które **zachowują ich znaczenie semantyczne**.

### Przykład prosty

Masz zdjęcie kota:
- **Oryginał**: Kot patrzy w prawo, jasne oświetlenie
- **Augmentacja 1**: Odbicie lustrzane → Kot patrzy w lewo (nadal kot!)
- **Augmentacja 2**: Lekka rotacja 5° → Kot lekko skośny (nadal kot!)
- **Augmentacja 3**: Zmiana jasności → Kot w ciemniejszym pomieszczeniu (nadal kot!)

**Rezultat**: Z 1 zdjęcia kota masz teraz 4 różne obrazy kota. Model uczy się rozpoznawać kota w różnych warunkach.

## Dlaczego augmentacja?

### 1. **Zwiększenie rozmiaru datasetu**
- **Problem**: Masz 50 ręcznie zaadnotowanych schematów
- **Augmentacja**: Generujesz 5 wersji każdego → 250 obrazów total
- **Benefit**: Model widzi 5x więcej przykładów bez dodatkowej pracy anotacji

### 2. **Zapobieganie overfittingowi**
- **Bez augmentacji**: Model zapamiętuje konkretne obrazy ("ten schemat ma rezystor w lewym górnym rogu")
- **Z augmentacją**: Model uczy się rozpoznawać rezystor niezależnie od pozycji, oświetlenia, rotacji
- **Benefit**: Lepsze generalizowanie na nowe dane

### 3. **Symulacja warunków rzeczywistych**
- **Problem**: Treningujesz na czystych renderach, ale użytkownik wgrywa skany z szumem
- **Augmentacja**: Dodajesz szum, artefakty papierowe, nieostroć → model jest gotowy
- **Benefit**: Production-ready model od razu

### 4. **Robustność**
- **Cel**: Model powinien działać dla:
  - Różnych jakości skanów (300 DPI vs 150 DPI)
  - Różnych poziomów oświetlenia
  - Lekko przekrzywionych dokumentów
  - Różnych stylów rysowania schematów
- **Augmentacja**: Trenuje model na wszystkich tych wariantach

## Jak działa augmentacja?

### Kluczowa zasada: **Transformacja + Zachowanie anotacji**

```
Obraz wejściowy:         Obraz wyjściowy:
┌─────────────┐          ┌─────────────┐
│  [R1]       │          │    [R1]     │  <- Obrócony 10°
│   ┌──┐      │  ──────> │   ╱──╲      │
│   └──┘      │          │  ╱    ╲     │
└─────────────┘          └─────────────┘
Bbox: [10,10,50,30]      Bbox: [12,8,48,35] <- Zaktualizowany!
```

**Ważne**:
- Jeśli obrócisz obraz o 10°, to bbox też musisz obrócić o 10°
- Jeśli przeskalujesz obraz 2x, to bbox też przeskalujesz 2x
- Inaczej anotacje będą wskazywać na niewłaściwe miejsca!

### Biblioteka: albumentations

[albumentations](https://albumentations.ai/) to biblioteka Pythona która:
1. Stosuje transformacje do obrazów
2. **Automatycznie** transformuje bounding boxy, segmentation masks, keypoints
3. Jest zoptymalizowana dla computer vision (szybka, GPU support)

```python
import albumentations as A

# Definicja augmentacji
transform = A.Compose([
    A.Rotate(limit=10, p=0.5),           # Rotacja ±10° (50% szans)
    A.GaussianBlur(blur_limit=3, p=0.3),  # Blur (30% szans)
    A.RandomBrightness(limit=0.2, p=0.5), # Jasność ±20% (50% szans)
], bbox_params=A.BboxParams(format='coco'))  # <- Mówi: "Transformuj też boxy!"

# Zastosowanie
augmented = transform(
    image=image,
    bboxes=[[10, 10, 50, 30]],  # [x, y, width, height]
    category_ids=[1]             # Klasa: resistor
)

# Wynik: augmented['image'], augmented['bboxes'] (zaktualizowane!)
```

## 3 Profile augmentacji w Talk electronics

### 1. **Light** - Subtelne modyfikacje

**Kiedy używać**: Wysokiej jakości źródła (CAD exports, czyste PDF-y)

**Transformacje**:
```python
A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.05, rotate_limit=5)
# - Przesunięcie ±5%
# - Skalowanie ±5%
# - Rotacja ±5°

A.GaussianBlur(blur_limit=3)
# - Lekkie rozmycie (symulacja lekko nieostrych skanerów)

A.ImageCompression(quality_lower=70, quality_upper=90)
# - JPEG compression 70-90 quality
# - Symulacja zapisanych i ponownie otwartych plików

A.RandomBrightnessContrast(brightness_limit=0.1, contrast_limit=0.1)
# - Jasność ±10%
# - Kontrast ±10%
```

**Przykład**: Czyste rendery z KiCad → lekko zmodyfikowane wersje

### 2. **Scan** - Realistyczne skany dokumentów 📄

**Kiedy używać**: Przygotowanie do rozpoznawania skanowanych schematów papierowych (NASZ GŁÓWNY USE CASE!)

**Transformacje**:
```python
A.GaussNoise(var_limit=(10, 50))
# - Szum gaussowski (ziarnistość skanów)

A.Rotate(limit=10)
# - Rotacja ±10° (krzywo położony dokument na skanerze)

A.GaussianBlur(blur_limit=(3, 5))
# - Blur (nieostre skanery, ruch podczas skanowania)

A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2)
# - Różne oświetlenie, różne ustawienia skanera

A.ImageCompression(quality_lower=60, quality_upper=90)
# - Kompresja (skany zapisywane jako JPEG)

# Specjalne:
- Paper texture overlay (tekstura papieru - żółtawe, pomarszczone)
- Scanning artifacts (linie skanera, drobne plamki)
```

**Przykład**:
- **Przed**: Biały czyste tło, perfect lines, idealna jakość
- **Po**: Lekko żółtawy papier, drobny szum, lekko rozmyte, lekko przekrzywione, jakość 80% JPEG

**Wygląda jak**: Rzeczywisty skan dokumentu z biura!

### 3. **Heavy** - Ekstremalne warunki 💪

**Kiedy używać**: Edge cases, robustness testing, zdjęcia z telefonów

**Transformacje**:
```python
A.Rotate(limit=30)
# - Rotacja ±30° (bardzo krzywy dokument)

A.Perspective(scale=(0.05, 0.15))
# - Zniekształcenia perspektywiczne (zdjęcie pod kątem)

A.GaussNoise(var_limit=(50, 150))
# - Silny szum

A.MotionBlur(blur_limit=(7, 15))
# - Motion blur (ruch aparatu/telefonu)

A.ImageCompression(quality_lower=40, quality_upper=70)
# - Mocna kompresja

A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3)
# - Ekstremalne warunki oświetlenia
```

**Przykład**: Zdjęcie schematu telefonem w słabym oświetleniu, pod kątem, z drżącą ręką

**Uwaga**: Heavy może być zbyt agresywne - użyj oszczędnie, głównie do testowania czy model jest robust.

## Augmentacja w Talk electronics - praktyczny workflow

### Krok 1: Wygeneruj syntetyczne schematy
```bash
python scripts/synthetic/batch_generate.py --num-schematics 50
```
**Wynik**: 50 czystych PNG + metadata JSON

### Krok 2: Konwertuj do COCO
```bash
python scripts/synthetic/emit_annotations.py \
  --input-dir data/synthetic/annotations \
  --output data/synthetic/coco_annotations.json
```
**Wynik**: COCO JSON z 639 annotations

### Krok 3: Zastosuj augmentację
```bash
python scripts/synthetic/augment_dataset.py \
  --input data/synthetic/images_raw \
  --output data/synthetic/images_augmented \
  --annotations data/synthetic/coco_annotations.json \
  --profile scan
```
**Wynik**: 50 augmentowanych PNG + zaktualizowany COCO JSON

### Krok 4: Trenuj model
```bash
yolo task=segment mode=train \
  model=yolov8n-seg.pt \
  data=configs/synthetic_dataset.yaml \
  epochs=100
```

## Częste pytania

### Q: Czy augmentacja zmienia klasy obiektów?
**A**: NIE. Rezystor po rotacji nadal jest rezystorem. Augmentacja NIE zmienia semantyki.

### Q: Ile augmentacji na obraz?
**A**: Zależy od potrzeb:
- **Mało danych (10-50 images)**: 5-10 augmentacji per image
- **Średnio danych (50-200 images)**: 2-5 augmentacji per image
- **Dużo danych (200+ images)**: 1-2 augmentacje per image

W Talk electronics (50 images): **1 augmentacja per image** (profil "scan") = 100 total

### Q: Czy augmentacja zastąpi prawdziwe dane?
**A**: **NIE**. Augmentacja pomaga, ale:
- Syntetyczne + augmentacja ≠ prawdziwe dane
- Zawsze miej test set z **prawdziwych** niezaugmentowanych danych
- Najlepsze wyniki: **syntetyczne + augmentacja + prawdziwe**

### Q: Która augmentacja jest najlepsza?
**A**: **Zależy od danych wejściowych**:
- Rendery CAD → light
- Skany papierowe → **scan** (NASZE)
- Zdjęcia telefonem → heavy

### Q: Czy mogę łączyć profile?
**A**: TAK. Możesz:
```bash
# 50% light, 50% scan
python scripts/synthetic/augment_dataset.py --profile light --num 25
python scripts/synthetic/augment_dataset.py --profile scan --num 25
```

### Q: Co się stanie jeśli zapomnę zaktualizować anotacji?
**A**: **Katastrofa!** Model będzie uczył się na złych danych:
- Obraz obrócony, bbox nie obrócony → model uczy się błędnych lokalizacji
- Zawsze używaj bibliotek które aktualizują annotations automatycznie (albumentations, imgaug)

## Podsumowanie

**Augmentacja to**:
- ✅ Zwiększenie datasetu bez dodatkowej pracy
- ✅ Symulacja warunków rzeczywistych
- ✅ Zapobieganie overfittingowi
- ✅ Robustność modelu

**W Talk_electronic**:
- Profil **"scan"** dla schematów papierowych
- 50 raw + 50 augmented = 100 total
- albumentations automatycznie aktualizuje COCO annotations
- Gotowe do treningu YOLOv8!

**Następny krok**: Trening modelu na augmentowanych danych → mierzenie mAP → iteracja 🚀
