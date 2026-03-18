# Słownik pojęć Talk_electronic

Ten plik zbiera definicje terminów, o które prosisz podczas pracy nad projektem. Dopisuj nowe pojęcia przy każdej kolejnej prośbie, aby utrzymać wspólne zrozumienie.

## Panel Copilota w VS Code
Interfejs po lewej stronie edytora, otwierany ikoną Copilota. Pozwala na szybkie czaty i podpowiedzi kontekstowe powiązane z aktualnie otwartymi plikami, ale nie uruchamia dedykowanego agenta wykonującego wieloetapowe zadania.

## Tryb agenta („Kompiluj w trybie agenta”)
Specjalna sesja Copilota odpalana z dolnej listy modeli (np. GPT‑5.1 Codex Preview). Agent planuje pracę autonomicznie, może wykonywać wiele kroków i operować na całym repozytorium, więc lepiej zachowuje kontekst dużych zadań.

## Batch
Porcja danych przetwarzana jednocześnie podczas uczenia modelu. Zamiast aktualizować wagi po każdej pojedynczej próbce lub po całym zbiorze, model liczy gradient na ustalonej liczbie przykładów (np. 32 lub 128), co przyspiesza trening i stabilizuje uczenie przy ograniczonym zużyciu pamięci.

## `(C:\Users\robet\miniforge3\Scripts\activate)`
Polecenie Windows PowerShell uruchamiające skrypt aktywacji środowiska Miniforge. Dzięki temu kolejne polecenia korzystają z menedżera `conda` i zainstalowanych tam pakietów zamiast globalnego Pythona.

## `conda activate Talk_flask`
Przełączenie aktywnego środowiska `conda` na profil projektu Talk_electronic. W tym envie znajdują się zależności potrzebne do trenowania YOLO (PyTorch, Ultralytics, Albumentations itp.).

## `yolo task=segment mode=train`
Wywołanie CLI Ultralytics YOLO w trybie segmentacji podczas treningu. `task=segment` określa typ zadania (detekcja + maski), a `mode=train` wymusza etap uczenia zamiast walidacji czy inferencji.

## `model=yolov8s-seg.pt`
Parametr CLI wskazujący bazowy checkpoint (`.pt`) wersji *YOLOv8-small* dla segmentacji. To startowa sieć, która będzie dalej dostrajana na naszym zbiorze.

## `data=configs/yolov8_v2_moderate.yaml`
Ścieżka do pliku konfiguracyjnego datasetu. YAML zawiera lokalizacje obrazów/etykiet (train/val/test) oraz listę klas (`resistor`, `capacitor`, `inductor`, `diode`).

## `epochs=75`
Liczba pełnych przejść po zbiorze treningowym podczas szkolenia. Przy tej wartości model zobaczy każde zdjęcie 75 razy, co równoważy czas treningu i ryzyko przeuczenia.

## `batch=12`
Rozmiar batcha używany przez YOLO podczas treningu. Każda aktualizacja wag bazuje na 12 obrazach; parametr musi mieścić się w pamięci CPU/GPU.

## `imgsz=640`
Rozdzielczość wejściowa obrazów po przeskalowaniu przez YOLO (640×640 pikseli). Standardowa wartość, która zapewnia kompatybilność z pre-trenowanymi wagami i rozsądny koszt obliczeń.

## `degrees=8.0`
Skala augmentacji kątowej (±8°). YOLO losowo obraca obrazy w tym zakresie, aby zwiększyć odporność modelu na różne orientacje schematów.

## `shear=1.5`
Natężenie transformacji ścinania (shear) w procentach. Wprowadza delikatne deformacje geometryczne imitujące skany pod kątem.

## `flipud=0.0`
Prawdopodobieństwo odbicia pionowego ustawione na 0%. W schematach pionowe odbicia mogłyby mylić symbolikę, więc transformacja jest wyłączona.

## `copy_paste=0.15`
Współczynnik augmentacji *Copy-Paste*: z prawdopodobieństwem 15% fragmenty obiektów są wklejane na inne obrazy. Pomaga zwiększyć różnorodność układów elementów.

## `mixup=0.10`
Ustalona zasada pracy: po każdej nowej sesji YOLO zapisujemy krótki raport. Zawiera on (1) parametry startowe komendy `yolo ...`, (2) najważniejsze metryki końcowe (`precision`, `recall`, `mAP50`, `mAP50-95` dla pudełek i masek) wraz z porównaniem do poprzedniego runu oraz (3) komentarz, jaki wpływ te liczby mają na wykrywanie w aplikacji (np. „wyższa precyzja pudełek = mniej fałszywych symboli”). Raport trafia do `PROGRESS_LOG.md`, żebyśmy mogli szybko wrócić do historii eksperymentów.

## mAP50-95 (średnia precyzja wieloprogowa)
`mAP` to "średnia precyzja" – zgrubnie odpowiada na pytanie „jaki odsetek wykryć jest jednocześnie trafny i dokładnie położony”. Wariant `mAP50-95` liczy tę wartość dla wielu progów nakładania się obiektu (IoU 0.50, 0.55, …, 0.95) i uśrednia wynik. Dzięki temu nie wystarczy tylko lekko musnąć obiekt ramką; model musi umieć dopasować kształt bardzo dokładnie, bo wysokie progi (0.85–0.95) karzą nawet drobne odchylenia. Dla osoby nietechnicznej: wyobraź sobie położenie pinezki na symbolu – `mAP50` pozwala, by pinezka zakryła połowę elementu, a `mAP95` wymaga, żeby trafiła praktycznie idealnie. Średnia z wielu progów mówi więc, jak stabilnie i precyzyjnie YOLO lokalizuje elementy niezależnie od tego, jak surowo je ocenimy.

## Log z treningu YOLO – interpretacja kolumn
Fragment:

```
Epoch    GPU_mem   box_loss   seg_loss   cls_loss   dfl_loss  Instances       Size
 1/75       3.9G      3.839      5.065      4.164      1.947        108        640: 100% ...
	...  Class  Images  Instances  Box(P  R  mAP50  mAP50-95)  Mask(P  R  mAP50  mAP50-95)
	all         67       1025     0.0931 ...
```

- **Epoch 1/75** – numer epoki; „1/75” oznacza, że model jest w pierwszym z 75 pełnych przejść po zbiorze treningowym.
- **GPU_mem 3.9G** – ilość pamięci karty graficznej aktualnie zużywana przez proces treningu (3.9 GB VRAM). Przy RTX A2000 dostępne jest ~6 GB, więc typowy zakres zużycia to 3–5 GB; przekroczenie 5.8 GB grozi błędem OOM, a wartości <1 GB oznaczają, że batch/model jest bardzo mały.
- **box_loss** – składnik funkcji straty odpowiadający za dopasowanie ramek ograniczających (bounding boxes) do obiektów na obrazie. Na starcie epoki 1 wartości rzędu 3–5 są normalne; w stabilnym treningu schodzimy do <1.0 (docelowo 0.2–0.6). Przedział praktyczny to 0 (idealny brak błędu) do ~5 (model losowy).
- **seg_loss** – błąd części segmentacyjnej (maski pikselowe). Start zwykle 4–6, następnie spada poniżej 1.5; wartości >3 po kilkunastu epokach sugerują problem z danymi/maskami.
- **cls_loss** – strata klasyfikacyjna; mierzy poprawność przypisywania obiektu do jednej z klas (rezystor, kondensator, itd.). Zakres podobny do box_loss: pierwsze epoki 2–4, docelowo <0.5. Maks. wartości mogą sięgać ~6 przy kompletnym braku dopasowania.
- **dfl_loss** – *Distribution Focal Loss*, składnik opisujący precyzję estymacji położeń granic ramki (stosowany w YOLOv8 zamiast klasycznego IoU loss). Typowy zakres to 0.8–2.0; dobre modele spadają poniżej 0.5. Jeśli utrzymuje się powyżej 2, model ma trudność z precyzyjnym centrowaniem ramek.
- **Instances 108** – liczba przykładów (obiektów/instancji) uwzględnionych w danym batchu podczas tej iteracji.
- **Size 640** – rozdzielczość obrazu używana w batchu (po przeskalowaniu do 640×640).
- **`100% ━━━ 27/27 1.1it/s 25.2s`** – pasek postępu dla epoki: przerobiono 27 batchy na 27 zaplanowanych; prędkość 1.1 iteracji na sekundę; czas epoki 25.2 s.
- **Tabela „Class / Images / Instances / Box(...) / Mask(...)”** – statystyki walidacyjne liczone na zbiorze `val` po zakończeniu epoki:
	- **Class** – nazwa klasy, a wiersz „all” to metryki zagregowane dla wszystkich klas.
	- **Images** – liczba obrazów w walidacji (np. 67).
	- **Instances** – liczba obiektów (np. 1025 segmentów wszystkich klas).
-  - **Box(P)** – precyzja (precision) dla detekcji. Zakres 0–1 (0–100 %). W praktyce: <0.3 oznacza złe wykrycia, 0.5–0.7 to akceptowalny poziom, >0.8 bardzo dobry.
-  - **Box(R)** – czułość/rekall (recall) dla detekcji. Zakres 0–1. Wartości <0.4 sygnalizują dużą liczbę pominiętych obiektów, 0.6–0.8 to sensowny poziom, >0.8 bardzo dobry.
-  - **Box mAP50** – średnia precyzja (mean Average Precision) przy IoU 0.50. Zakres 0–1; modele praktyczne celują w 0.6–0.9, a poniżej 0.3 to zwykle początek treningu.
-  - **Box mAP50-95** – uśredniony mAP po progach IoU 0.50–0.95; zawsze niższy niż mAP50. Wyniki 0.3–0.5 są poprawne, >0.6 bardzo dobre. Zera świadczą o modelu losowym.
-  - **Mask(P)** i **Mask(R)** – analogiczne precision i recall, ale dla masek segmentacyjnych. Zakres 0–1. W praktyce trudniej przekroczyć 0.8 niż przy boxach, bo maski są bardziej wymagające.
-  - **Mask mAP50 / mAP50-95** – jakość masek przy progach IoU jak wyżej. Wyniki 0.5+ oznaczają solidne maski, 0.2–0.4 to średni poziom, <0.1 wskazuje na problemy z segmentacją.

Jeżeli w logu pojawia się więcej skrótów (np. `it/s`, `ETA`, `dT`), wszystkie odnoszą się do tempa treningu: liczba iteracji na sekundę, estymowany czas do końca oraz czas trwania epoki. Dla `it/s` typowe wartości mieszczą się między 0.5 a 3 (w zależności od batcha i sprzętu), a `ETA` maleje do 0 w miarę kończenia epoki.

## Pytania i odpowiedzi – 18 listopada 2025

**P:** Czy treningi na danych syntetycznych będziemy kontynuować?
**O:** Tak, utrzymujemy serię eksperymentów na syntetykach. Pozwalają testować zmiany w pipeline (deskew, netlista), stroić hiperparametry i mieć świeże metryki, zanim pojawią się nowe dane z anotacji.

**P:** Czy warto trenować, czekając na anotacje z prawdziwych schematów?
**O:** Warto – traktujemy aktualne treningi jako pretraining. Dzięki nim mamy punkt startowy i działający MLOps; po otrzymaniu realnych etykiet przełączymy się na fine-tuning/mieszany trening bez straty czasu.

**P:** Co się stanie z pierwszą partią annotacji z Label Studio?
**O:** Po eksporcie trafiają do `data/annotations/raw/`, przechodzą walidację (`scripts/validate_annotation_metadata.py`), konwersję do COCO/YOLO i merge z syntetykami (`merge_annotations.py`). Aktualizujemy splity, odpalamy szybkie benchmarki, a potem pełny trening i backup wag.

**P:** Jak możemy rozbudować UI aplikacji?
**O:** Najbliższe kroki to dodanie w widokach Flask podglądu masek/YOLO, listy symboli z możliwością zaznaczenia obiektów oraz historii netlist/segmentacji. W dalszej kolejności warto dołożyć mini-edytor (np. canvas do korekt) i timeline wykonań.

**P:** Jak możemy rozbudować podgląd lub automatyczne raportowanie benchmarków?
**O:** Rozbudowujemy `scripts/run_inference_benchmark.py` o zapis CSV/JSON i generację wykresów w `reports/benchmark_visualizations/`, a w aplikacji dodajemy panel diagnostyczny (np. endpoint z ostatnim wynikiem, dashboard w UI). Dodatkowo można wpiąć cron/CI, który cyklicznie odpala benchmark i publikuje log.
