# Talk electronics — Electronic Schematic Analyzer

Talk electronics is a Flask web application for analyzing electronic schematics from PDF files. Features include PDF upload, image processing, AI symbol recognition, netlist generation, and diagnostic chat.

## Features
- PDF upload and conversion to images
- Image preprocessing (grayscale, binarization, noise reduction, deskewing)
- Interactive image editing with canvas (crop, erase)
- AI-powered symbol detection (Ultralytics YOLOv8 segmentation on PyTorch)
- Powiązanie wyników detekcji z generatorem netlist (przekazywanie `symbols` / `symbolHistoryId` do `/api/segment/netlist`)
- Edytor stref ignorowanych (rect/poly/brush) z lokalnym podglądem i REST API `/api/ignore-regions`
- Netlist generation
- Łączenie schematów: formularz konektorów krawędzi + panel statusu w netliście (automatyczne filtrowanie po `historyId`)
- Diagnostic chat with AI

## Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Run the app: `python app.py` (or `flask --app app run`)
3. Execute automated checks: `pytest`
4. Launch the VS Code task **Run Flask dev server** (Ctrl+Shift+B) for a one-click server startup.
5. Open http://127.0.0.1:5000/
6. Generate benchmark samples: `python scripts/extract_benchmark_samples.py --help`
7. Opcjonalny benchmark detektora: `python scripts/run_inference_benchmark.py --list`

## Usage

### Detekcja symboli na bieżącym fragmencie
1. W zakładce **Przygotowanie obrazu** wczytaj stronę PDF lub lokalny plik i wykonaj potrzebne kroki (kadrowanie, binaryzacja, retusz).
2. Gdy podgląd w panelu po prawej pokazuje oczyszczony fragment, przejdź do zakładki **Detekcja symboli**.
3. W sekcji źródła wybierz opcję odpowiadającą bieżącemu widokowi (`Aktualny fragment` lub wpis z listy historii).
4. Wybierz detektor (np. `yolov8`) oraz parametry progów, a następnie zaznacz checkbox **Zapisz wynik w historii** – dzięki temu rezultat trafi do wspólnej historii i będzie dostępny dla netlisty oraz diagnostyki.
5. Kliknij **Uruchom detekcję**; po zakończeniu wyniki pojawią się w tabeli oraz na podglądzie jako nakładka symboli.
6. Aby ponownie użyć wyniku (np. w segmencie netlisty), wybierz go z historii w prawym panelu lub wskaż `symbolHistoryId` w panelu netlisty.

### Wysyłanie obrazów inline (data-URL)

- Endpoint `/api/segment/lines` akceptuje obrazy przekazane jako **data-URL** (np. `data:image/png;base64,...`). Serwer dekoduje i wczytuje obraz po stronie backendu (OpenCV), co jest przydatne do testów E2E lub gdy klient chce przesłać obraz bez zapisywania go do `uploads/`.
- Przykład payloadu:
  ```json
  {
    "imageUrl": "data:image/png;base64,<...>",
    "roi": {"x":10,"y":10,"width":50,"height":50}
  }
  ```
  Odpowiedź ma standardowy format wyników segmentacji z polami `result` i `metadata`.

  Szczegóły i dodatkowe przykłady znajdziesz w `docs/DATA_URL_IMAGES.md`.


### Oznaczanie stref ignorowanych
1. Załaduj fragment w zakładce **Przygotowanie obrazu** (np. `data/sample_benchmark/triangle_demo_p01_r0_c0.png`).
2. Przejdź do zakładki **Strefy ignorowane** i kliknij **Załaduj z kadrowania**, aby osadzić bieżący obraz w canvasie (`ignoreCanvas`).
3. Wybierz tryb rysowania (Prostokąt, Wielokąt lub Pędzel), narysuj obszary i obserwuj podgląd JSON w panelu „Zapis (JSON)”.
4. Kliknij **Zapisz**, aby utrwalić wynik w `localStorage` oraz (opcjonalnie) wysłać payload do `/api/ignore-regions` – endpoint wspiera token `IGNORE_REGIONS_TOKEN` i przechowuje maski w `uploads/ignore-regions/`.
5. W razie potrzeby użyj **Cofnij** lub **Wczytaj** – historia zapisów (po prawej) umożliwia QA szybkie porównywanie masek.
6. Fixture Label Studio + maska PNG znajduje się w `data/annotations/fixtures/ignore_zones_labelstudio/` (opis importu w README w tym katalogu). QA może załadować `ignore_zones_fixture.json`, a następnie pobrać `static/fixtures/ignore-zones/demo_mask.png`, by zsynchronizować wynik z API.

### Łączenie schematów i podgląd netlisty
1. Przejdź do zakładki **Łączenie schematów** i uzupełnij formularz konektora (edgeId A/B/C/D + numer strony, opcjonalnie nazwa sieci, sheetId, notatka).
2. W polu **History ID** wpisz identyfikator fragmentu segmentacji (pojawia się w historii segmentacji) – dzięki temu wpis zostanie automatycznie powiązany z netlistą.
3. Po zapisaniu konektora lista w tej samej karcie pozwala edytować/usuwać wpisy, a przycisk **Przepisz bieżącą stronę** pobiera numer strony z aktywnego PDF.
4. W zakładce **Segmentacja linii → Netlista** pojawił się panel „Konektory krawędzi”: po wygenerowaniu netlisty backend dorzuca sekcję `metadata.edgeConnectors`, a UI pokazuje liczbę dopasowań, strony oraz tabelę szczegółów.
5. Jeśli netlista została wygenerowana wcześniej, a konektory dopiero co zmieniono, użyj przycisku **Odśwież** w panelu netlisty – front pobiera `/api/edge-connectors?includePayload=1` i filtruje wyniki po bieżącym `historyId`.

### Eksport SPICE z netlisty
1. W panelu **Segmentacja linii → Netlista** wygeneruj netlistę (wymagane odcinki linii).
2. Kliknij **Eksportuj do SPICE** – UI wyśle netlistę i przypisania komponentów do `/api/segment/netlist/spice`.
3. Po sukcesie zobaczysz podgląd decka `.cir` i link **Pobierz plik .cir** (zapisywany w historii gdy `Zapisz w historii` jest włączone).
4. Szczegóły payloadu, mapowania symboli i przykładowy deck RC: [docs/SPICE_EXPORT.md](docs/SPICE_EXPORT.md).

## Project Structure
- `app.py`: Lightweight entry point using the application factory
- `talk_electronic/`: Flask blueprints, services, and configuration helpers
- `templates/`: HTML templates
- `static/js/`: Modular front-end code for PDF preview and crop tools
- `static/fixtures/ignore-zones/`: Artefakty testowe (maski) dla QA i importów Label Studio
- `uploads/`: Uploaded files
- `models/`: Documentation and scripts for managing external model weights (see `models/README.md`)
- `tests/`: Pytest-based regression and integration checks
- `scripts/tools/validate_workflow_yaml.py`: Proste narzędzie do parsowania i podglądu kluczy top-level w `.github/workflows/preflight.yml` (lub innym wskazanym pliku YAML).

## Model Weights
- Store large binary artifacts under `models/weights/` or `models/checkpoints/`.
- Keep only lightweight configuration and documentation in git; weights themselves are ignored.
- Document the source, checksum, and conversion commands in `models/README.md` to ensure reproducibility.

### YOLOv8 detector configuration

- Default weights are resolved in the following order: `TALK_ELECTRONIC_YOLO_WEIGHTS` (env), `weights/train6_best.pt`, `weights/best.pt`, `weights/yolov8s-seg.pt`, `runs/segment/train6/weights/best.pt`.
- Override the inference device with `TALK_ELECTRONIC_YOLO_DEVICE` (e.g. `cpu`, `cuda:0`).
- The detector is lazy-loaded; GPU memory is allocated only after the first `/api/symbols/detect` call using `detector="yolov8"`.

### Benchmark i monitoring YOLOv8

- `scripts/run_inference_benchmark.py --list` wypisuje wszystkie zarejestrowane detektory (`noop`, `simple`, `template`, `yolov8`).
- Przykład testu wydajności z własnym katalogiem próbek:
   ```bash
   python scripts/run_inference_benchmark.py yolov8 --image-dir data/sample_benchmark --warmup 1 --runs 5
   ```
- Skrypt automatycznie rejestruje detektory i wykonuje rozgrzewkę, dzięki czemu pomiary można logować do raportów (`reports/benchmark_baseline.md`).

### Process monitoring & watchdog

Long-running workers and validation jobs should be executed via the watchdog wrapper to prevent hung jobs and to improve CI reliability. See `docs/PROCESS_MONITORING.md` for policy, examples, default timeouts and guidance for CI integration.

### Powiązanie detekcji symboli z netlistą

- Endpoint `/api/segment/netlist` przyjmuje teraz dodatkowe pola:
   - `"symbols"`: bezpośredni wynik `/api/symbols/detect` (detector, summary, detections).
   - `"symbolHistoryId"`: identyfikator wpisu historii zwrócony przez `symbol_detection.detect_symbols` gdy `storeHistory=true`.
- Dane trafiają do `netlist.metadata.symbols`, co ułatwia dalszą analizę (dopasowanie komponentów, integrację z SPICE).
- Przykład payloadu:
   ```json
   {
      "lines": { ... },
      "symbolHistoryId": "symbols-0f3c..."
   }
   ```

## Documentation

### Core Documentation
- `docs/annotation_guidelines.md`: dataset scope, annotation schema, split policy, QA checklist.
- `docs/annotation_tools.md`: Label Studio configuration and export workflow.
- `docs/integration/symbol_detection.md`: architecture notes for wiring detectors into inference routes.

### **🆕 Annotation Strategy (WAŻNE!)**
**Przed rozpoczęciem anotacji przeczytaj:**
1. **`docs/ANNOTATION_WORKFLOW_QUICKSTART.md`** - Quick start guide for new workflow
2. **`docs/ROTATED_BBOX_STRATEGY.md`** - Complete strategy for rotated rectangles + polygons
3. **`docs/ANNOTATION_DECISION_TREE.md`** - Decision tree: when to use rectangle vs polygon
4. **`docs/MYTH_BUSTING_MIXED_FORMATS.md`** - Why mixing formats is GOOD (not bad!)
5. **`docs/VISUALIZATION_ANNOTATION_PIPELINE.md`** - Visual explanation of the pipeline

**TL;DR**: Use rotated rectangles (80-90%) + polygons (10-20% for edge cases). This is industry standard!

### Data & Benchmarks
- `data/sample_benchmark/README.md`: workflow for maintaining benchmark PNG snippets and metadata.
- `data/sample_benchmark/sources.md`: curated list of licensed assets for generating benchmark tiles.
- `reports/benchmark_baseline.md`: template for logging detector latency results.
- `docs/annotation_schema.json`: JSON Schema consumed by `scripts/validate_annotations.py --schema`.

## Tests

- Backend/unit: `pytest`
- E2E (Playwright): `npm install` (jednorazowo), następnie `npm run test:e2e:smoke` – zestaw obejmuje m.in. scenariusz `tests/e2e/ignore_zones.spec.js` (rysowanie, zapis i cofanie stref ignorowanych).

### E2E tests — uruchamianie lokalne (Playwright) 🔧

- Zainstaluj zależności Node i Playwright (raz):
  - `npm install`
  - `npx playwright install`
- Uruchom lokalnie dev server (Flask) w środowisku `talk_flask` (zalecane):
  - `conda activate talk_flask; python -m flask --app app run --debug`
  - lub skorzystaj z VS Code taska **Run Flask dev server** (Ctrl+Shift+B) — wygodne do szybkiego startu.
- Poczekaj, aż serwer będzie dostępny pod `http://127.0.0.1:5000` (możesz użyć `npx wait-on http://127.0.0.1:5000`).
- Uruchom smoke suite:
  - `npm run test:e2e:smoke`
- Uruchom pełny zestaw E2E (wszystkie testy `tests/e2e/*.spec.js`):
  - `npm run test:e2e:full`
- Uruchom pojedynczy test (przydatne do debugowania):
  - `npx playwright test tests/e2e/edge_connectors.spec.js -g "shrink slider updates preview immediately"`
- Jeśli widzisz `ERR_CONNECTION_REFUSED`, upewnij się, że dev server jest uruchomiony i nasłuchuje na `127.0.0.1:5000`. To najczęstsza przyczyna lokalnych niepowodzeń E2E.

**CI note:** GitHub Actions uruchamia dev server w tle i używa `npx wait-on` aby poczekać na dostępność serwisu przed uruchomieniem testów (zob. `.github/workflows/playwright-e2e.yml`).

### Debugging flaków E2E (Playwright) 🔎

- Zbieranie artefaktów lokalnie:
  - Uruchom test(y) z zachowaniem trace/screenshot przy ponownym uruchomieniu:
    `npx playwright test --retries=1 --trace on-first-retry`
  - Wyświetl trace interaktywnie (po uruchomieniu powyższego):
    `npx playwright show-trace tests/e2e/artifacts/<test-folder>/trace.zip`
  - W przypadku niepowodzenia znajdziesz automatycznie zapisane `screenshots/` i `trace.zip` w `tests/e2e/artifacts` dzięki `playwright.config.js`.
- Debugowanie jednego testu (przydatne przy flaky):
  - `npx playwright test tests/e2e/edge_connectors.spec.js -g "shrink slider updates preview immediately" --retries=1 --trace on-first-retry`
- Debugowanie w CI:
  - CI już uploaduje `playwright-report` oraz `test-results/**` i `flask.log` jako artefakty; gdy testy są niestabilne, pobierz artefakty z zakładki *Artifacts* workflow i otwórz trace przy użyciu `npx playwright show-trace`.

- Tip: jeśli chcesz stale śledzić flaky tests, uruchom `npx playwright test --reporter=list --retries=1` lokalnie i dodaj `--trace on-first-retry` tylko dla podejrzanych testów — to ogranicza rozmiar artefaktów.

- (Opcjonalnie) Zainstaluj pre-push hook, aby uruchamiać smoke przed każdym pushem (Windows PowerShell):
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/hooks/install-pre-push.ps1`
  - Aby automatycznie uruchamiać dev server w tle bez interakcji podczas pre-push, włącz auto-start:
    - Podczas instalacji: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/hooks/install-pre-push.ps1 -AutoStart`
    - Lub ręcznie: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/enable-auto-start.ps1 -Enable`
    - Gdy auto-start jest włączony, hook spróbuje uruchomić serwer w tle (bez pytania) przed uruchomieniem smoke tests.

Debugging overlay (helper)
- Dla szybkiej lokalnej diagnozy problemów z overlay/UI dostępny jest helper: `scripts/debug_accept_playwright.js`.
- Jak użyć:
  1. Uruchom dev server (Flask): `C:/Users/DELL/miniconda3/envs/talk_flask/python.exe -m flask --app app run --debug`.
  2. Uruchom: `npm run debug:accept` — skrypt uruchomi Playwright, sprawdzi widoczność `#acceptWarning`, spróbuje kliknąć przycisk i zweryfikuje, czy `#appContent` się ujawnia; wypisze też błędy strony/konsoli i informacje o requestach.
- Uwaga: skrypt jest przeznaczony do użytku lokalnego (nie uruchamiaj go w CI automatycznie); dodaliśmy alias `debug:accept` w `package.json`.

Jeśli chcesz, mogę dodać dodatkową sekcję z instrukcjami uruchamiania testów w CI (GitHub Actions) albo dodać krótką instrukcję debugowania flaków (trace/screenshot).
- Merge do `main` wymaga zielonego checku CI: `E2E Smoke tests (Playwright)` (status required, strict up-to-date).

### Test prerequisites / Notes

- Some tests (PDF rendering/export) require PyMuPDF (`fitz`) — if you see collection errors about `fitz`, install it with:
   ```bash
   pip install pymupdf
   ```
- Playwright E2E tests require Node.js and Playwright dependencies. To set up locally:
   ```bash
   npm install
   npx playwright install
   npm run test:e2e:smoke
   ```

If you want me to run E2E smoke tests in this environment I can try, but it may require Node/npm/Playwright to be installed and configured in the container/host.

### Rytuał post-train (szybka wizualizacja na real test)
- Po każdym treningu YOLO uruchom krótki predict na realnych próbkach testowych i zapisz do `runs/predict_real/test_real` (wizualny sanity check).
- Zapisz w `reports/` krótkie metryki (mAP/P/R) oraz ścieżkę do artefaktów (`runs/.../results.csv`, `labels.jpg`, `best.pt`).
- Jeśli val/test mają mało reali, odnotuj to w logu (DEV_PROGRESS) i potraktuj wyniki jako orientacyjne.
- W razie błędów API sprawdź `GET /healthz` (status, roi_metrics) przed ponownym uruchomieniem.
- Dodaj do logu krótką checklistę: ścieżka do wag (`best.pt`), log CSV (`results.csv`), sample wizualizacje (`labels.jpg`, `runs/predict_real/test_real`), metryki P/R/mAP oraz decyzja co dalej (np. rerun, więcej reali, zmiana augmentacji).
- Checklista (skrót): (1) predict na realach i zapis do `runs/predict_real/test_real`; (2) skopiuj metryki z `results.csv` i mini wizualizacje do krótkiego wpisu w `reports/*.md`; (3) w DEV_PROGRESS zanotuj czy val/test są wiarygodne oraz decyzję (keep/redo/więcej reali); (4) sprawdź `/healthz` jeśli trening lub predict zwraca błąd.

### Katalogi runs/ i reports/ — szybkie wskazówki
- `runs/…/train`: surowe logi i wagi z treningów (YOLO) — kluczowe pliki: `results.csv`, `labels.jpg`, `weights/best.pt`.
- `runs/predict_real/test_real`: obowiązkowe wizualizacje po każdym treningu na realnych próbkach; używamy do sanity check.
- `runs/segment/val*` / `runs/segment/test*`: walidacje lub testy inference; trzymaj krótkie README w podkatalogu gdy dodajesz nowe runy.
- `reports/*.md`: streszczenia eksperymentów/treningów; linkuj do powiązanych runów i wypisz decyzję (keep/redo/augment). Krótkie podsumowanie wrzucaj też do DEV_PROGRESS.

## Synthetic Data Pipeline

Pipeline do generowania syntetycznych schematów z automatycznymi anotacjami COCO.

### Workflow

1. **Generuj schemat** (wymaga KiCad API):
   ```bash
   python scripts/synthetic/generate_schematic.py --output schema.pdf --seed 42 --components 15
   ```

2. **Eksportuj do PNG** (300 DPI):
   ```bash
   python scripts/synthetic/export_png.py --input schema.pdf --output data/synthetic/images_raw/schema.png --dpi 300
   ```

3. **Wygeneruj anotacje COCO**:
   ```bash
   python scripts/synthetic/emit_annotations.py --metadata schema.json --image schema.png --output annotations.json
   ```

4. **Zastosuj augmentacje** (wymaga `albumentations`):
   ```bash
   python scripts/synthetic/augment_dataset.py --input data/synthetic/images_raw/ \
       --output data/synthetic/images_augmented/ --annotations annotations.json --profile scan
   ```

Szczegóły: `scripts/synthetic/README.md`

#### Profile augmentacji / szum / rotacja / grubość linii
- Profile `light`/`scan`/`heavy` w [scripts/synthetic/augment_dataset.py](scripts/synthetic/augment_dataset.py#L74-L152) dodają szum, blur, rotację (±5° lub ±10°) i dropout; używaj `--profile scan` jako domyślnego dla realistycznych skanów.
- Jeśli potrzebujesz większej zmienności grubości linii, w [scripts/synthetic/generate_schematic.py](scripts/synthetic/generate_schematic.py#L105-L154) możesz zmienić szerokość linii (argument `width` w wywołaniach `draw.line` / `draw.rectangle`) lub wylosować ją w zakresie 1–3 px przed rysowaniem komponentu.

#### Raport liczebności klas przy eksporcie (COCO → YOLO)
- Eksporter [scripts/export_coco_to_yolo_split.py](scripts/export_coco_to_yolo_split.py) zapisuje `class_report.json` z liczebnością klas per split oraz ostrzeżeniami, gdy `val`/`test` są małe.
- Przykład: `python scripts/export_coco_to_yolo_split.py --input data/synthetic/coco_annotations.json --output data/yolo_dataset/synthetic_split --search-dirs data/synthetic/images_raw data/synthetic/images_augmented --synthetic-prefix synthetic_`
- Raport sprawdź przed treningiem; jeśli `val`/`test` ma <3 obrazów lub brakuje klas, dopisz realne anotacje albo zwiększ pulę obrazów.
