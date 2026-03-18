# Proces Treningu Modelu AI - Wyjaśnienie dla Laika

## 🎯 Cel Projektu

Tworzymy "elektroniczne oko" - sztuczną inteligencję, która potrafi rozpoznawać komponenty elektroniczne (rezystory, kondensatory, cewki, diody) na zdjęciach schematów elektronicznych.

---

## 📚 Krok 1: Generowanie Danych Treningowych

**Co robimy?**
Tworzymy sztuczne schematy elektroniczne z komponentami - podobnie jak nauczyciel przygotowuje zestawy ćwiczeń dla ucznia.

**Jak to działa?**

1. **Generator schematów** (`batch_generate.py`) - program który:
   - Rysuje komponenty elektroniczne (rezystory, kondensatory, cewki, diody)
   - Umieszcza je losowo na białym tle
   - Zapisuje obrazy PNG (np. `schematic_001.png`)
   - Dla każdego obrazu tworzy "ściągawkę" (plik JSON) mówiącą gdzie dokładnie jest każdy komponent

2. **Przykład:**
   ```
   Obraz: schematic_042.png
   Ściągawka:
   - Rezystor na pozycji (100, 150), szerokość 40px, wysokość 20px
   - Kondensator na pozycji (300, 200), szerokość 30px, wysokość 25px
   - Dioda na pozycji (500, 180), szerokość 35px, wysokość 35px
   ```

3. **Ile danych potrzebujemy?**
   - **Batch 1+2:** 200 schematów (pierwsza wersja)
   - **Batch 3:** Kolejne 200 schematów (rozszerzenie datasetu)
   - **Razem:** 400 schematów z 6227 komponentami

**Dlaczego to ważne?**
Im więcej przykładów, tym lepiej AI się uczy - jak uczeń który przećwiczył setki zadań matematycznych.

---

## 📊 Krok 2: Konwersja do Formatu COCO

**Co robimy?**
Przekształcamy "ściągawki" do standardowego formatu zrozumiałego dla programów uczących AI.

**Jak to działa?**

1. **Skrypt konwersji** (`emit_annotations.py`):
   - Czyta wszystkie 200 plików JSON (po jednym dla każdego schematu)
   - Łączy je w jeden wielki plik `coco_batch3.json`
   - Dodaje metadane (nazwy klas, statystyki, etc.)

2. **Format COCO** to jak "słownik" dla AI:
   ```json
   {
     "obrazy": [
       {"id": 1, "nazwa": "schematic_001.png", "szerokość": 800, "wysokość": 600}
     ],
     "anotacje": [
       {"id": 1, "obraz_id": 1, "kategoria": "rezystor", "pozycja": [100, 150, 40, 20]}
     ],
     "kategorie": [
       {"id": 1, "nazwa": "resistor"},
       {"id": 2, "nazwa": "capacitor"}
     ]
   }
   ```

**Dlaczego to ważne?**
Wszystkie biblioteki uczenia maszynowego rozumieją format COCO - to jak międzynarodowy standard.

---

## 🔀 Krok 3: Łączenie Zbiorów Danych (Merge)

**Co robimy?**
Łączymy starsze i nowsze dane w jeden wielki zbiór treningowy.

**Problem który napotkaliśmy:**
- Batch 1: pliki `schematic_001-150.png`
- Batch 3: też pliki `schematic_001-200.png` ❌ **KOLIZJA!**

**Rozwiązanie:**
1. **Przenumerowanie** (`renumber_batch3.py`):
   - Zmieniamy nazwy: `schematic_001.png` → `schematic_251.png`
   - Zmieniamy nazwy: `schematic_200.png` → `schematic_450.png`
   - Aktualizujemy wszystkie odniesienia w JSON

2. **Deduplikacja kategorii** (`deduplicate_categories.py`):
   - Problem: Po merge mieliśmy 8 kategorii (4 + 4 duplikaty)
   - Rozwiązanie: Zmergowaliśmy duplikaty do 4 unikalnych klas

**Wynik:**
- **Dataset v2.0:** `coco_v2_400_fixed.json`
- 400 obrazów (schematic_001-150 + 251-450)
- 6227 anotacji
- 4 klasy idealnie zbalansowane (po ~25% każda)

---

## ✂️ Krok 4: Podział na Train/Val/Test

**Co robimy?**
Dzielimy dane na 3 części - jak nauczyciel dzieli materiał na lekcje, kartkówki i egzamin końcowy.

**Skrypt:** `split_dataset.py`

**Podział:**
```
400 schematów
├── TRAIN (280 schematów - 70%)  ← Tutaj AI się uczy
├── VAL (60 schematów - 15%)     ← Tutaj sprawdzamy czy dobrze się uczy
└── TEST (60 schematów - 15%)    ← Ostateczny egzamin (nieużywane podczas treningu!)
```

**Dlaczego 3 części?**

1. **TRAIN (uczenie):**
   - AI widzi te obrazy podczas treningu
   - Uczy się rozpoznawać wzorce
   - Jak uczeń rozwiązujący zadania domowe

2. **VAL (walidacja):**
   - AI NIE widzi tych obrazów podczas uczenia
   - Sprawdzamy co kilka minut czy AI nie "kuje na blachę"
   - Jeśli AI zgaduje tylko to co widziała - nie nauczyła się naprawdę!
   - Jak kartkówka niezapowiedziana

3. **TEST (egzamin):**
   - AI NIGDY nie widzi tych obrazów
   - Używamy tylko na samym końcu do finalnej oceny
   - Najbardziej uczciwy sprawdzian
   - Jak matura - jednorazowa, ostateczna ocena

**Stratyfikacja:**
Upewniamy się że w każdej części jest proporcjonalnie tyle samo każdej klasy (rezystorów, kondensatorów, etc.). To jak zapewnienie że egzamin sprawdza WSZYSTKIE umiejętności, nie tylko jedną.

---

## 🧠 Krok 5: Architektura Modelu - YOLOv8-seg

**Co to jest "model"?**
To jak "mózg" AI - struktura neuronów która przetwarza obraz i mówi "tu jest rezystor, tam kondensator".

**YOLOv8-seg (nano) - Specyfikacja:**

```
Wielkość: 3.26 miliona parametrów
├── 151 warstw (layers)
├── Rozmiar pliku: ~6.5 MB
└── Szybkość: ~50 obrazów/sekundę na CPU
```

**Struktura (uproszczona):**

1. **Warstwy wejściowe (Conv layers 0-9):**
   - Przetwarzają obraz 640×640 pikseli
   - Wykrywają podstawowe wzorce (krawędzie, linie, kształty)
   - Jak oko które najpierw widzi kontury

2. **Warstwy środkowe (C2f blocks):**
   - Łączą proste wzorce w bardziej złożone
   - Rozpoznają "to wygląda jak prostokąt z paskami = rezystor"
   - Jak mózg który rozpoznaje obiekty

3. **Warstwy wyjściowe (Segment head):**
   - Dla każdego piksela mówią: "to jest rezystor" lub "to jest tło"
   - Tworzą precyzyjną maskę konturu komponentu
   - 4 klasy: resistor, capacitor, inductor, diode

**WAŻNE:** YOLOv8 to **pretrained model** - został już wstępnie wytrenowany na 80 klasach obiektów (samochody, ludzie, zwierzęta). My tylko "douczamy" go do rozpoznawania komponentów elektronicznych!

---

## 🏋️ Krok 6: Trening (Fine-tuning)

**Co robimy?**
"Douczamy" model YOLOv8 do rozpoznawania NASZYCH komponentów.

### Trening Baseline (pierwszy)

**Parametry:**
```yaml
Model: yolov8n-seg.pt (pretrained)
Dataset: 200 obrazów (140 train / 30 val / 30 test)
Epochs: 50 (50 przejść przez cały dataset)
Batch size: 16 (16 obrazów naraz)
Learning rate: 0.01 → 0.0001 (maleje z czasem)
Augmentacje (standardowe):
  - Rotacja: ±7 stopni
  - Odbicie: poziome 50%
  - Skalowanie: 0.5-1.5x
```

**Jak wygląda jedna epoka?**

1. AI bierze 16 obrazów z train
2. Próbuje rozpoznać komponenty
3. Porównuje swoje odpowiedzi ze "ściągawką"
4. Oblicza błąd (jak bardzo się pomyliła)
5. Poprawia swoje "neurony" żeby następnym razem było lepiej
6. Powtarza dla kolejnych 16 obrazów
7. Po przejściu całego train → sprawdza się na VAL

**Monitorowanie:**
Co epokę program zapisuje:
```csv
epoch, precision, recall, mAP@0.5, mAP@0.5-95
1,     0.523,     0.418,  0.392,    0.198
10,    0.821,     0.701,  0.748,    0.551
50,    0.855,     0.749,  0.804,    0.619  ← FINAL
```

**Wyniki Baseline:**
- ✅ **Precision: 85.5%** - gdy AI mówi "to rezystor", w 85.5% ma rację
- ❌ **Recall: 74.9%** - AI znajduje tylko 75% wszystkich komponentów (PROBLEM!)
- ✅ **mAP@0.5: 80.4%** - ogólna jakość bardzo dobra

**Czas treningu:** ~1.4 godziny (50 epok × ~100 sekund/epoka)

---

### Trening Heavy Augmentations (drugi)

**Dlaczego drugi trening?**
Recall 74.9% oznacza że AI **pomija co 4. komponent**. To za dużo!

**Hipoteza:**
AI widziała za mało wariantów komponentów (różne rotacje, perspektywy). Jak uczeń który ćwiczył tylko proste zadania i nie radzi sobie ze złożonymi.

**Rozwiązanie: HEAVY AUGMENTATIONS**

Augmentacje = sztuczne "przeróbki" obrazów podczas treningu:

```yaml
# BASELINE vs HEAVY AUG
Rotacja:        ±7°  →  ±15°     (większe obroty)
Shear:          0°   →  ±5°      (deformacje perspektywiczne)
Odbicie pionowe: 0%  →  50%      (góra-dół)
Mosaic:         włączony         (łączy 4 obrazy w jeden)
```

**Przykład augmentacji:**
```
Oryginalny obraz → AI widzi podczas treningu:
- Obrócony o 12°
- Odbity pionowo
- Zdeformowany (shear)
- Przeskalowany 0.7x
- Z większą jasnością
```

**Efekt:**
Z 200 fizycznych obrazów, AI "widzi" tysiące wariantów! To jak uczeń który przećwiczył zadanie we wszystkich możliwych formach.

**Cel:** Recall 74.9% → 80-85%

**Status:** Trening w toku (~1.5h)

---

## 📈 Krok 7: Analiza Wyników

**Co sprawdzamy?**

### 1. Metryki Globalne

**Precision (Precyzja):**
```
Precision = Prawidłowe wykrycia / Wszystkie wykrycia AI

Przykład: AI pokazała 100 "rezystorów"
- 85 to naprawdę rezystory ✅
- 15 to pomyłki ❌
Precision = 85/100 = 85%
```

**Recall (Kompletność):**
```
Recall = Prawidłowe wykrycia / Wszystkie komponenty w rzeczywistości

Przykład: W obrazie jest 100 rezystorów
- AI znalazła 75 ✅
- 25 pominęła ❌
Recall = 75/100 = 75%
```

**mAP (mean Average Precision):**
- Średnia precyzja dla wszystkich klas i progów
- mAP@0.5 = precyzja gdy wymagamy 50% pokrycia
- mAP@0.5-95 = średnia dla progów 50-95% (surowe!)

### 2. Analiza Per-Klasa

**Baseline Results:**
```
Klasa       | Recall | Problem
------------|--------|----------------------------------
Diode       | 87.3%  | ✅ Najlepszy (charakterystyczny trójkąt)
Resistor    | 76.2%  | ⚠️ Średni
Inductor    | 67.1%  | ❌ Słaby (spirala mylona z innymi)
Capacitor   | 68.8%  | ❌ Najgorszy (2 proste linie)
```

**Dlaczego kondensatory najgorzej?**
1. Prosty kształt (||) - mało charakterystyczny
2. Małe rozmiary (~30×25px)
3. Podobny do innych elementów gdy obrócony
4. Brak kontekstu (brak linii połączeń)

### 3. Wizualizacja Błędów

Program tworzy obrazy pokazujące:
- **Zielone:** prawidłowo wykryte
- **Czerwone:** pominięte (false negatives)
- **Żółte:** fałszywe alarmy (false positives)

Zapisane w: `runs/segment/baseline_200_final/val_batch*.jpg`

---

## 🔧 Krok 8: Iteracyjne Usprawnienia

**Strategia "trial and error":**

### Plan Eksperymentów:

1. ✅ **Baseline (zrobione):**
   - 200 obrazów, standardowe augmentacje
   - Wynik: Recall 74.9%

2. 🔄 **Heavy Augmentations (w toku):**
   - Te same 200 obrazów, mocniejsze augmentacje
   - Oczekiwany wynik: Recall 80-85%

3. 📋 **Więcej danych (zaplanowane):**
   - 400 obrazów (200+200)
   - Oczekiwany wynik: Recall +2-5%

4. 📋 **Większy model (przyszłość):**
   - YOLOv8s-seg (11M parametrów) zamiast nano (3M)
   - Oczekiwany wynik: Recall +3-7%

5. 📋 **Connection lines (przyszłość - długoterminowo):**
   - Dodać linie połączeń między komponentami
   - Kontekst pomoże rozróżnić podobne kształty
   - Oczekiwany wynik: Recall +5-10%

**Proces iteracji:**
```
Trening → Wyniki → Analiza błędów → Hipoteza → Zmiana → Trening → ...
```

---

## 💾 Krok 9: Zapisywanie Modeli

**Co zapisujemy po każdym treningu?**

### Struktura katalogów:
```
runs/segment/
├── baseline_200_final/          ← Pierwszy trening
│   ├── weights/
│   │   ├── best.pt              ← Najlepszy model (epoka z najwyższym mAP)
│   │   └── last.pt              ← Ostatni model (epoka 50)
│   ├── results.csv              ← Metryki każdej epoki
│   ├── val_batch0_pred.jpg      ← Wizualizacje predykcji
│   └── args.yaml                ← Parametry treningu
│
└── heavy_aug_200/               ← Drugi trening (w toku)
    ├── weights/
    │   ├── best.pt
    │   └── last.pt
    └── ...
```

### Zawartość pliku .pt (model):

```
best.pt (~6.5 MB):
├── Architektura: YOLOv8n-seg (151 warstw)
├── Parametry: 3,264,396 wartości (wagi neuronów)
├── Metadane: nazwy klas, rozmiar obrazu, etc.
└── Trening info: epoch, mAP, optimizer state
```

---

## 🎓 Odpowiedź na Pytania

### Pytanie 1: Czy model jest w jednym pliku?

**TAK** - model to pojedynczy plik `.pt` (PyTorch format):

```
yolov8n-seg.pt  (~6.5 MB)
├── Cała sieć neuronowa (151 warstw)
├── Wszystkie wagi i biasy (3.26M parametrów)
├── Konfiguracja (które klasy rozpoznaje)
└── Historia (z którego treningu pochodzi)
```

### Pytanie 2: Czy "udoskonalamy" ten sam plik przez kolejne treningi?

**TAK I NIE** - zależy jak podejdziemy:

#### Scenariusz A: Nowy trening od zera (to co robimy teraz)
```
yolov8n-seg.pt (pretrained od Ultralytics)
    ↓ TRENING 1 (baseline)
runs/segment/baseline_200_final/weights/best.pt
    ↓
    | (oddzielnie)
    ↓ TRENING 2 (heavy aug) - zaczynamy od YOLOv8 pretrained ponownie!
runs/segment/heavy_aug_200/weights/best.pt
```

**Efekt:** Dwa niezależne modele, każdy wytrenowany osobno.

#### Scenariusz B: Kontynuacja treningu (możliwe w przyszłości)
```
yolov8n-seg.pt (pretrained)
    ↓ TRENING 1
baseline_best.pt
    ↓ resume=True
    ↓ TRENING 2 (dołącz 200 nowych obrazów)
improved_best.pt
    ↓ resume=True
    ↓ TRENING 3 (jeszcze mocniejsze augmentacje)
final_best.pt
```

**Efekt:** Jeden model ewoluujący w czasie, "pamięta" poprzednie treningi.

#### Co robimy MY (obecnie)?

**Każdy trening od nowa:**
- Zaczynamy od czystego `yolov8n-seg.pt`
- Douczamy na naszych danych
- Zapisujemy jako nowy plik

**Dlaczego?**
1. **Porównywalność:** możemy sprawdzić "augmentacje vs więcej danych vs większy model"
2. **Bezpieczeństwo:** jeśli coś pójdzie źle, mamy stare wersje
3. **Eksperymenty:** łatwiej testować różne pomysły równolegle

#### W Przyszłości (produkcja):

**Transfer learning + fine-tuning:**
```
Krok 1: Wytrenuj dobry model bazowy (np. na 400 obrazach)
Krok 2: Gdy zbierzesz 100 nowych obrazów → doucz model (resume)
Krok 3: Gdy znajdziesz błędy → dodaj więcej przykładów → doucz
```

---

## 📊 Podsumowanie Procesu

### Cały pipeline w pigułce:

```
1. GENEROWANIE (batch_generate.py)
   200 schematów + JSON metadata
   ↓
2. KONWERSJA (emit_annotations.py)
   200 JSON → coco_batch3.json
   ↓
3. MERGE (merge_annotations.py + deduplicate)
   200 + 200 = 400 obrazów w coco_v2_400_fixed.json
   ↓
4. SPLIT (split_dataset.py)
   400 → 280 train / 60 val / 60 test
   ↓
5. TRENING (yolo train)
   YOLOv8n-seg + dane → model.pt
   ↓
6. WALIDACJA (automatyczna co epokę)
   Sprawdzenie na VAL set
   ↓
7. ANALIZA (results.csv, visualizations)
   Metryki, wykresy, błędy
   ↓
8. ITERACJA (jeśli wyniki słabe)
   Zmiany → powrót do kroku 5
```

### Czasy wykonania:

```
Generowanie 200 schematów:     ~30 minut
Konwersja + merge + split:     ~2 minuty
Trening 50 epok:                ~1.5 godziny (CPU)
Analiza wyników:                ~10 minut
─────────────────────────────────────────
TOTAL (pełna iteracja):         ~2.5 godziny
```

### Wyniki dotychczas:

```
✅ Dataset v1.0:    200 obrazów, 3680 anotacji
✅ Baseline model:  mAP 80.4%, Recall 74.9%
✅ Dataset v2.0:    400 obrazów, 6227 anotacji
🔄 Heavy aug test:  w toku (~1.5h), cel: Recall 80-85%
```

---

## 🚀 Następne Kroki

1. **Poczekaj ~1.5h** na wyniki heavy augmentations
2. **Porównaj:** Recall baseline vs heavy aug
3. **Jeśli sukces (Recall 80%+):**
   - Trenuj na v2.0 (400 obrazów) z heavy aug
   - Oczekiwany wynik: Recall 85%+
4. **Jeśli brak poprawy:**
   - Spróbuj większego modelu (YOLOv8s-seg)
   - Lub dodaj connection lines

---

## 🎯 Kluczowe Wnioski

### Jak działa uczenie AI (w skrócie):

1. **Dane** - Im więcej przykładów, tym lepiej
2. **Augmentacje** - Sztuczna różnorodność danych
3. **Architektura** - Większy model = większa pojemność
4. **Iteracje** - Trening → Analiza → Poprawa → Powtórz
5. **Cierpliwość** - Każda iteracja to ~2-3 godziny

### Model to:

- ✅ Jeden plik `.pt` (~6.5 MB)
- ✅ Zawiera całą sieć neuronową
- ✅ Można go zapisywać, kopiować, udoskonalać
- ✅ Każdy trening tworzy NOWY plik (chyba że resume=True)

### Sukces zależy od:

1. **Jakość danych:** Precyzyjne anotacje
2. **Ilość danych:** Minimum 200, optymalnie 1000+
3. **Różnorodność:** Augmentacje, różne scenariusze
4. **Architektura:** Model musi być odpowiednio duży
5. **Cierpliwość:** Iteracyjne usprawnienia

---

**Data utworzenia:** 14 listopada 2025
**Autor:** GitHub Copilot + Robert
**Status projektu:** Eksperyment 2/5 - Heavy Augmentations (w toku)
