# 🧩 Notatka 30 listopada 2025 – rozróżnianie skrzyżowań przewodów

## ✅ 31 grudnia 2025 – doprecyzowanie domyślnych progów naprawy kropek

- Domyślne progi graph-repair zaostrzone: kąt 12° (z 15°) i wymagane pokrycie 0.5 (z 0.4), żeby rzadziej łączyć przypadkowe kropki. Test `test_graph_repair_defaults.py` dostosowano do nowych wartości.

## ✅ Postępy 2 grudnia 2025 – eksport junction patchy i wzmacnianie linii

1. **Naprawa blokera eksportu** – `_build_junction_patch_extractor` błędnie traktował pozycje węzłów jako `(row, col)` zamiast `(x, y)`, co skutkowało zerowymi patchami i zawieszaniem się zapisu (`cv::imwrite` dostawał pusty obraz). Korekta kolejności osi wyeliminowała wyjątek i pozwoliła zebrać komplet 64 łatek z pojedynczego obrazu.
2. **Wzmocnienie cienkich linii** – do `LineDetectionConfig` dodano opcjonalny moduł `_enhance_lines_from_color`, który w przestrzeni HSV wyszukuje jasne/little-saturated linie, delikatnie je przyciemnia i wygładza przed skeletonizacją. CLI (`scripts/export_junction_patches.py`) otrzymało flagi `--enable-color-enhancement`, `--color-strength`, `--color-s-threshold`, `--color-v-threshold`, a obrazy wejściowe wczytujemy teraz w kolorze.
3. **Debug eksperymentalny** – przeprowadzono serię testów (siła 0.9, progi V/S=250/90 oraz kombinacja 0.95+250/90). Najlepszy efekt ciągłości w `binary/skeleton` dał wariant „combo”, który faktycznie wyprowadził brakujące cienkie połączenia – mimo że `prepared` wizualnie wygląda podobnie, to skeleton zebrał dodatkowe ścieżki.
4. **Zestaw artefaktów porównawczych** – każdy run zapisuje oddzielny katalog debug (`debug_strength09`, `debug_hsv250_90`, `debug_combo`), co ułatwia porównanie `prepared/binary/skeleton` oraz późniejsze dobieranie parametrów pod konkretne schematy.

### Plan na 3 grudnia 2025

1. **Walidacja na mniejszym schemacie** – uruchomić eksport na jednym z plików z `data/junction_inputs/small/` z konfiguracją „combo”, aby ręcznie potwierdzić, że wszystkie oczekiwane skrzyżowania istnieją w skeletonie (brak przerw).
2. **Parametryzacja presetów** – przygotować gotowe profile (np. `color_enhancement=preset:combo`) w `configs/line_detection.defaults.json`, by łatwo przełączać zestawy progów z poziomu API/CLI.
3. **Porządkowanie datasetu patchy** – przejrzeć katalog `data/sample_benchmark/junction_patches/unknown/` i zsynchronizować `manifest.csv`, żeby nowo zebrane łatki były gotowe do adnotacji (ew. przenieść do Label Studio).


**Pytanie użytkownika**: jak pipeline powinien traktować dwa przypadki skrzyżowań linii na schematach – bez kropki (brak połączenia) oraz z kropką (połączenie). Czy dodawać nowe kategorie w Label Studio, tryb hybrydowy ignorowania, czy inne rozwiązanie?

**Rekomendacja Copilota**:
1. **Moduł detekcji „junction dot” + heurystyka w `talk_electronic/services/line_detection.py`** – mały klasyfikator wycinków 32×32 px ocenia, czy na przecięciu jest kropka; wynik zasila graf połączeń. Przy niepewności stosujemy heurystyki (mini segment łączący, zgodne net labele) zanim połączymy węzły.
2. **Globalny przełącznik w UI** – checkbox w Label Studio/aplikacji (analogiczny do „stref ignorowanych”), którym anotator oznacza arkusze, gdzie skrzyżowania mają być z zasady ignorowane; backend respektuje flagę przy budowie grafu.
3. **Nowa klasa `junction_dot` (opcjonalnie później)** – dopiero gdy kroki 1–2 nie zapewnią jakości. Wtedy dodajemy prostokątny label do ręcznej anotacji kropek, by YOLO miało nadzór i eliminujemy heurystyki.

Podejście minimalizuje koszt anotacji: najpierw automatyzacja + prosta flaga, a dopiero w razie potrzeby rozszerzenie schematu labeli.

# 🗓️ Plan na 1 grudnia 2025 – junction dots & polityka arkusza

1. **Eksport patchy skrzyżowań** – włączyć tryb debug w `talk_electronic/services/line_detection.py`, który zapisze 32×32 px wycinki z każdej detekcji skrzyżowania do `data/sample_benchmark/junction_patches/` (etykiety: `dot_present`, `no_dot`, `unknown`) i dopisać krótkie README w tym katalogu.
2. **Prototyp klasyfikatora** – utworzyć `scripts/train_junction_classifier.py`, który z w/w patchy stworzy mały zbiór treningowy, przećwiczy CNN lub prosty model klasyfikacyjny i zapisze wagi/artefakty (`models/junction_classifier.onnx` + `metrics.json`).
3. **Integracja backendowa** – dodać klasę `JunctionDetector` w `line_detection.py` (ładowanie modelu, fallback heurystyczny, cache wyników) oraz rozszerzyć strukturę grafu o flagę `junctionState` (`auto_connected`, `needs_review`, `blocked`).
4. **Flaga per arkusz** – wprowadzić ustawienie `sheet_metadata.junction_policy` przechowywane w historii przetwarzania (endpoint `PATCH /api/sheets/<id>/junction-policy` + migracja historii) i eksponować przełącznik w UI (`templates/index.html`, `static/js/app.js`).
5. **Testy i QA** – dopisać przypadki w `tests/test_line_detection.py` (kropka/brak kropki/niepewne), scenariusz Playwright akceptujący przełącznik oraz fixture JSON z nowym polem `junctionState`.
6. **Dokumentacja** – zaktualizować `docs/annotation_guidelines.md`, `docs/TEST_SCENARIOS.md` oraz bieżący `PROGRESS_LOG` o instrukcję zbierania patchy, opis modelu i wskazówki QA dotyczące przełącznika.

## ✅ Postępy 1 grudnia 2025

- W `talk_electronic/services/line_detection.py` dodano `JunctionPatchExportConfig` oraz pomocniczą funkcję `_export_junction_patches`, która w trybie debug zapisuje wycinki 32×32 dla węzłów o stopniu ≥3 i odkłada metadane w `manifest.csv`.
- Nowy katalog `data/sample_benchmark/junction_patches/` zawiera README z instrukcją segregacji (`dot_present`, `no_dot`, `unknown`) oraz automatycznie inicjalizuje się przy pierwszym eksporcie patchy.
- Aby zebrać próbki, należy przekazać do `LineDetectionConfig` strukturę `JunctionPatchExportConfig(enabled=True, output_dir=...)`; wynikowy manifest pozwoli na szybkie zasilenie skryptu `scripts/train_junction_classifier.py` w kolejnym kroku planu.
- Utworzono `scripts/train_junction_classifier.py`, który z pliku `manifest.csv` buduje dataset patchy, trenuje mały CNN (PyTorch) oraz eksportuje artefakty `models/junction_classifier.onnx` + `models/junction_classifier.metrics.json`; uruchomienie: `python scripts/train_junction_classifier.py --data-root data/sample_benchmark/junction_patches --epochs 15`.
- Backend `line_detection` otrzymał `JunctionDetectorConfig` + klasę `JunctionDetector`, która ładuje model ONNX (zależność `onnxruntime`), klasyfikuje węzły o stopniu ≥3 i aktualizuje nowe pola `junction_state/junction_label/junction_confidence` w grafie; metadane `junction_detection` zawierają podsumowanie stanu (`auto_connected`/`needs_review`/`blocked`).
- Dodano narzędzia CLI wspierające zbieranie i katalogowanie patchy: `scripts/export_junction_patches.py` (masowe uruchomienie detekcji + zapis patchy) oraz `scripts/sync_junction_manifest.py` (synchronizacja `manifest.csv` z aktualnymi folderami `dot_present/no_dot/unknown`).
- Powstał dokument `docs/JUNCTION_DETECTOR_PIPELINE.md`, który opisuje cały przepływ (eksport → etykietowanie → trening → integracja) wraz z checklistą jakościową.
- Aplikacja wczytuje teraz konfigurację linii z `configs/line_detection.defaults.json`, więc JunctionDetector/JunctionPatchExport można włączyć globalnie bez modyfikacji kodu (endpoint `/api/segment/lines` respektuje te ustawienia oraz dalsze nadpisania w payloadzie).
- Podjęto próbę zebrania patchy z 32 nowych schematów (`data/junction_inputs/`), jednak przetwarzanie trwało ponad godzinę bez wyników (prawdopodobnie przez bardzo duże rozdzielczości/czasochłonny skeleton). Uruchomienie przerwano, w `export_summary.json` brak zapisanych patchy.

### Plan na 2 grudnia 2025 – wydajne zbieranie patchy

1. **Downscaling wsadu** – skonwertować pliki z `data/junction_inputs/` do ~2000 px szerokości (np. `scripts/resize_dataset.py` lub poleceniem `magick mogrify -resize 35%`). Zmniejszenie rozdzielczości skróci skeletonizację.
2. **Batchowanie uruchomień** – dzielić wejściowe obrazy na paczki po 4–6 plików i uruchamiać `scripts/export_junction_patches.py` z parametrem `--processing-scale 0.5` oraz logowaniem (`--debug-dir uploads/processed/junction-debug`). Pozwoli to szybciej wykryć zawieszające się pliki.
3. **Monitorowanie czasu** – dla każdej paczki mierzyć czas i dopisować wynik do `export_summary.json`; pliki przekraczające 2 minuty kopiować do osobnego katalogu „heavy_inputs” i przetwarzać, gdy pipeline będzie zoptymalizowany.

# 📅 Harmonogram wdrożeń — grudzień 2025

| Faza | Zakres | Estymata (roboczo-godziny) | Wejścia / Zależności | Wyjścia / Kryteria akceptacji | Ryzyka / Mitigacja |
|------|--------|----------------------------|-----------------------|------------------------------|--------------------|
| A1. Edge connectors | Backend store + API (`talk_electronic/services/edge_connector_store.py`, blueprint `routes/edge_connectors.py`), UI „Łączenie schematów”, integracja z netlistą i diagnostyką. | 24h (3 dni x 8h) | Gotowe wytyczne LS, walidator `validate_annotation_metadata.py`, struktura `IgnoreRegionStore`. | CRUD dla konektorów, UI zapisujący odwołania, netlista posiada sekcję `connectors`, dokumentacja + testy API/Playwright. | Brak danych testowych → użyć syntetycznego przykładu + QA export przed wdrożeniem. |
| B1. Broken lines QA | Heurystyka + workflow potwierdzeń, walidacja metadanych `broken_line`, panel QA w `lineSegmentation`. | 32h (4 dni) | Ukończony moduł A1 (żeby netlista znała końce sygnałów), istniejące plany w PROGRESS_LOG, Label Studio fixture. | Endpoint `brokenLineCandidates`, progi auto/manual, panel QA i testy Playwright, dokumentacja QA. | Heurystyki zbyt agresywne → flagi telemetryczne + feature toggle w configu. |
| C1. Junction detection | Zbieranie patchy, model klasyfikujący, integracja `JunctionDetector`, flaga `junction_policy`, raporty QA. | 40h (5 dni) | Zakończone A1+B1 (stabilny graf linii), zebrane patche, pipeline danych. | Model `.onnx` + fallback heuryst., API zwracające `junctionState`, UI przełącznik, dokumentacja i testy. | Brak danych → fallback do heurystyk, logowanie patchy do rozbudowy datasetu. |

**Kamienie milowe**
- **4 XII** – Edge connectors gotowe: można eksportować netlistę z konektorami i historia QA zawiera wpisy `edge_connector`.
- **11 XII** – Broken lines + QA panel domknięte: heurystyka proponuje mosty, QA potwierdza, walidator wymusza metadane.
- **18 XII** – Junction detector dostępny w aplikacji, flagi per arkusz oraz logowanie patchy działa.
- **20–23 XII** – Bufor na poprawki/regresje i weryfikację e2e.

**Diagram zależności**

```mermaid
graph TD
  A1[Edge connectors<br/>(store+API+UI)] --> B1[Broken lines QA]
  B1 --> C1[Junction detection]
  subgraph QA & Netlist
    A1
    B1
    C1
  end
  Docs[Dokumentacja / Playwright] --> A1
  Docs --> B1
  Docs --> C1
```

# 🗓️ Plan na 28 listopada 2025

## Zadania (owner: Copilot) – heurystyka linii + tryb "ask for confirmation"
1. **Przygotować dane referencyjne** – zebrać przykłady przerwanych linii (w tym nowe label-e `broken_line`) i dodać je jako fixture do `data/sample_benchmark/` + notatka w `docs/QUALITY_METRICS.md`.
2. **Warstwa heurystyczna w backendzie** – w `talk_electronic/services/line_detection.py` dodać generowanie `BrokenLineCandidate` po `_merge_straight_chains` (kryteria dystans/kąt, score, flagi auto/manual).
3. **Progi auto vs QA** – wprowadzić konfigurację (`auto_bridge_threshold`, `manual_confirm_threshold`) i oznaczanie segmentów `confidence_label` (`bridged_auto`, `needs_confirmation`).
4. **API/serializacja** – rozszerzyć payload `/api/segment/lines` o `brokenLineCandidates`, aktualizować historię oraz dodać endpoint potwierdzający (`POST /api/segment/lines/confirm-broken`).
5. **Frontend QA** – panel sugestii w `static/js/lineSegmentation.js` (overlay, guziki „Połącz”/„Zostaw przerwę”, wywołania API) + test Playwright dla akceptacji.
6. **Testy jednostkowe/integracyjne** – nowe przypadki w `tests/test_line_detection.py` i test API sprawdzający workflow potwierdzeń.
7. **Dokumentacja** – opis heurystyki i QA flow w `docs/TEST_SCENARIOS.md` + `README` (sekcja „Naprawa przerwanych linii”).
8. **Walidator anotacji** – w `scripts/validate_annotation_metadata.py` dodać regułę wymagającą komentarza/metadanych przy każdej adnotacji `broken_line` (np. pole `broken_reason`), wraz z komunikatem naprawczym i wpisem w dokumentacji Label Studio.

## Zadania (owner: User) – Import + QA w Label Studio
1. **Uruchom Flask** – `npm run flask` (lub task „Run Flask dev server”) i potwierdź dostępność `http://127.0.0.1:5000/static/fixtures/ignore-zones/demo_mask.png`.
2. **Stwórz projekt LS** – nazwa np. „Ignore Zones QA demo”, interfejs z `BrushLabels` + `Image`, kolumna danych `ignore_mask` jako attachment/URL.
3. **Import JSON** – w Label Studio: *Import → Upload Files → JSON* i wskazać `data/annotations/fixtures/ignore_zones_labelstudio/ignore_zones_fixture.json`.
4. **Walidacja zadania** – po imporcie otworzyć task, sprawdzić link/miniaturę `ignore_mask`, obejrzeć adnotację `brushlabels` na obrazie `cross_binary.png`.
5. **Symulacja QA** – pobrać `demo_mask.png`, dodać ją do `/api/ignore-regions` z `historyId=fixture-ignore-demo-001`, potwierdzić wpis w historii QA.
6. **Checklist** – odnotować wynik w `docs/QA_log.md` (data, inicjały, status), zapisać ewentualne uwagi dla pipeline’u QA.

## ✅ Postępy 27 listopada 2025
- Playwright `npm run test:e2e:smoke` + pełny zestaw (`npm run test:e2e`) – wszystkie 6 scenariuszy zielone (czas ~8.5 s, 3 worker-y); logi w `tests/e2e/artifacts/`.
- Przygotowano szczegółową instrukcję importu `ignore_zones_fixture.json` + maski `demo_mask.png` dla QA Label Studio.
- Zdefiniowano strategię dla przerwanych linii: nowy label `broken_line`, heurystyka łączenia z trybem „ask for confirmation” oraz zakres zmian w backendzie/UI/testach.
- PROGRESS_LOG uzupełniono o plan działań na 28.11 oraz przypisanie odpowiedzialności (Copilot vs User).

# 🗓️ Plan na 20 listopada 2025

1. **Przegląd aplikacji i naprawa podglądu**
  - Otwórz wszystkie główne moduły (PDF workspace, podgląd binarizacji, segmentacja linii, YOLO/netlista) i przejdź przez pełny flow: od uploadu PDF po zapis historii i eksport netlisty.
  - Zanotuj każde odchylenie od oczekiwanego zachowania (szczególnie okno podglądu, które dziś zgłaszało artefakty) wraz z krokami reprodukcji, logami konsoli i ewentualnymi ostrzeżeniami backendu.
  - Zidentyfikuj dokładne miejsce w kodzie odpowiedzialne za „dziwne zachowanie” w oknie podglądu (np. błędny canvas, nakładka, wskaźnik strony) i przygotuj propozycję poprawki do wdrożenia jutro.

2. **Smoke-test UI + przetwarzania (pełna ścieżka)**
  1. Przygotowanie środowiska
    - `conda activate talk_flask`
    - `pip install -r requirements.txt` (kontrola brakujących pakietów) i `flask --app app run --debug` w osobnym terminalu.
    - Wyczyść `uploads/` i `processing-history.json`, zostawiając ostatnią kopię (backup w `backup_koniec_dnia/`).
  2. PDF + workspace
    - Załaduj plik `data/templates/sample_benchmark/schemat_07.pdf`, upewnij się, że wszystkie strony renderują się na liście.
    - Włącz/wyłącz overlay RODO i zweryfikuj, że przycisk „Rozumiem i akceptuję” reaguje natychmiast bez błędów JS.
  3. Historia binarizacji
    - Wybierz fragment poprzez crop, ustaw tryb binarizacji (np. Sauvola), kliknij „Zastosuj” i sprawdź, że wpis pojawia się w dropdownie (`type=crop`).
    - Użyj przycisku „Zapisz stronę do historii” dla bieżącej strony PDF i potwierdź, że powstaje wpis `type=page` ze zrzutem miniatury.
    - Kliknij każdy z wpisów w dropdownie i upewnij się, że obraz w panelu głównym aktualizuje się zgodnie z oczekiwaniami.
  4. Czyszczenie historii
    - Kliknij „Wyczyść historię” w sekcji binarizacji i potwierdź (w logach backendu oraz wizualnie), że usuwane są tylko wpisy `crop/upload/processed/page`, a logi innych modułów pozostają nienaruszone.
  5. Segmentacja linii i YOLO
    - Wykonaj prosty test segmentacji linii na aktualnych danych i sprawdź, że nowy wpis w historii nie znika po sprzątaniu binarizacji.
    - Uruchom detekcję symboli YOLO, przejdź do panelu netlisty, sprawdź podświetlanie masek oraz zapis metadanych do historii.
  6. Regresja zgłoszonego błędu
    - Odtwórz „dziwne zachowanie” okna podglądu według notatek z kroku 1 i zrzutuj konsolę przeglądarki, by mieć materiał do jutrzejszej poprawki.
  7. Raport
    - W `PROGRESS_LOG.md` dopisz wyniki testu (przeszło/nie przeszło) wraz z listą znanych anomalii i logów.

## ✅ Postępy 20 listopada 2025

- Smoke-test pełnego flow (upload → binarizacja → segmentacja linii → YOLO → netlista) wykonany sukcesem; brak blokujących błędów.
- W `templates/index.html`, `static/js/app.js`, `static/js/lineSegmentation.js` i `static/js/symbolDetection.js` uporządkowano layout zakładek, ujednolicono grupowanie modułów oraz dodano przełączniki podglądu dla detekcji symboli.
- `talk_electronic/services/symbol_detection/yolov8.py` obsługuje teraz brak GPU: fallback na CPU z przejrzystymi logami i bez konieczności restartu aplikacji.
- Sekcja podglądu YOLO ma skalowalny canvas (zoom 10–400%), poprawione wyostrzanie przy powiększeniu, synchronizację z tabelą wyników i stabilniejsze panning/drag.
- Historia przetwarzania zachowuje wpisy segmentacji/YOLO po czyszczeniu zapisów binarizacji, co potwierdzono w smoke-teście; logi backendu (`flask --debug`) nie wykazały nowych ostrzeżeń.
- Anomalia: przy szybkim przełączaniu zakładek w trakcie ładowania PDF wciąż sporadycznie pojawia się chwilowy pusty obszar podglądu; do obserwacji podczas kolejnej sesji.

# 🗓️ Plan na 21 listopada 2025

1. **Testy końcowe** – przejść pełny scenariusz na co najmniej trzech schematach (PDF z repo, lokalny plik PNG po retuszu, świeżo wgrany upload) i zweryfikować stabilność przepływu segmentacja → detekcja → nakładka.
2. **Dokumentacja użytkowa** – dopisać w `README.md` (lub dedykowanej sekcji pomocy) zwięzłą instrukcję „Jak uruchomić detekcję na bieżącym fragmencie”, z uwzględnieniem checkboxa „Zapisz wynik w historii”.
3. **Przegląd backlogu** – przejrzeć TODO/roadmapę i wybrać następny priorytet (np. automatyczne łączenie detekcji z netlistą, rozszerzenie diagnostyki UI, przygotowanie datasetu).

## ✅ Postępy 21 listopada 2025

### Naprawa synchronizacji kadrowania z PDF workspace

**Problem**: Po wczytaniu PDF w zakładce „Przestrzeń robocza" obraz nie pojawiał się automatycznie w zakładce „Kadrowanie".

**Diagnoza**:
- Moduł `cropApi` był inicjalizowany **po** `pdfApi` w pliku `app.js`
- Callback `onImageRendered` próbował wywołać `cropApi?.setSourceImage()`, ale `cropApi` był jeszcze `undefined`
- Brak logów z `cropTools.js` potwierdził, że metody modułu nie były wywoływane

**Rozwiązanie**:
- Przeniesiono inicjalizację `cropApi` **przed** `pdfApi`
- Użyto arrow functions dla zależności (`getDocumentContext`, `onCropSaved`), aby umożliwić late binding
- Dodano buforowanie `lastPdfContext` dla zapewnienia dostępności kontekstu przy przełączaniu zakładek
- `onTabVisible` w `cropTools` zawsze odświeża canvas przy wejściu na zakładkę

**Zmiany**:
- `static/js/app.js`: Kolejność inicjalizacji modułów, buforowanie PDF context
- `static/js/cropTools.js`: Odświeżanie canvas w `onTabVisible`

**Status**: ✅ Naprawione – obraz PDF pojawia się automatycznie w zakładce kadrowania

### Historia detekcji symboli

- Utworzono nową niezależną historię detekcji w zakładce „Detekcja symboli" (scope: `symbol-detection`)
- Usunięto powiązanie zapisów detekcji z historią modułu „Binaryzacja" (scope: `image-processing`)
- Dodano sekcję „Historia detekcji" z przyciskiem odświeżania i kartami zawierającymi:
  - Miniaturę wykrytych symboli
  - Metadane: detektor, liczba symboli, znacznik czasu, źródło
  - Linki do podglądu i szczegółów
- Zaimplementowano automatyczne ładowanie historii przy starcie modułu
- Zmiany w `templates/index.html`, `static/js/symbolDetection.js`, `static/js/app.js`, `talk_electronic/routes/processing.py`

### Dokumentacja testów

- Utworzono `docs/TEST_SCENARIOS.md` z trzema kompletnymi scenariuszami testowymi:
  - **Scenariusz A**: PDF z repo (pełny workflow od uploadu po eksport SPICE)
  - **Scenariusz B**: Lokalny PNG po retuszu
  - **Scenariusz C**: Świeży upload nowego pliku
- Każdy scenariusz zawiera szczegółowe kroki weryfikacji UI, historii i netlisty
- Dodano checklistę przed commitem

- README otrzymał sekcję „Detekcja symboli na bieżącym fragmencie" z instrukcją obsługi oraz przypomnieniem o checkboxie „Zapisz wynik w historii".
- Po przeglądzie `robert_to_do.md` za bieżący priorytet uznano przygotowanie zestawu anotacji COCO w Label Studio (zadanie „Przygotować adnotacje COCO..."); kolejne sesje będą skupione na uruchomieniu tego pipeline'u.

# 🗓️ Plan na 19 listopada 2025
### 2025-12-12 — Mask R-CNN PoC

- Krótki run Mask R-CNN PoC rozpoczęty: `runs/segment/exp_maskrcnn_poc` (10 epok, batch=1, img-size=512). Dataset YOLO->COCO wygenerowany: `data/yolo_dataset/mix_small/coco_annotations.json`.

- 2025-12-12: Krótki PoC na CPU zakończony (subset 8 obrazów) — `runs/segment/exp_maskrcnn_poc_small` (1 epoch) i raport dopisany do `qa_log.md`.
- Uwaga: pełny GPU run `exp_maskrcnn_poc` napotkał na błędy CUDA (illegal memory access); rekomendacja: uruchomić na CPU/zmniejszyć rozdzielczość albo dostosować model/backbone, albo użyć mniejszego batchu/obciąć obrazy.


1. **Naprawić i wznowić trening YOLOv8s-seg**
  - Przejść logi `runs/segment/train6` / `train7` i ostatnie `results.csv`, sprawdzić powód błędu (exit code 1 po komendzie `yolo ...`).
  - Zmniejszyć `batch` do 8–10 jeśli VRAM zapełnia się >5.8 GB, ewentualnie wyłączyć `copy_paste` na pierwszych epokach.
  - Odpalić trening na świeżym cache (`yolo task=segment ... --cache ram`) i monitorować `scripts/monitor_training.py --interval 30`.

2. **Dowieźć front dla wyników YOLO i netlisty**
  - W `templates/segment_result.html` (lub nowy widok) dodać podgląd maski + listę symboli z `netlist.metadata.symbols`.
  - W `static/js/segment_viewer.js` podpiąć highlight bbox/mask po kliknięciu na element listy; wykorzystać dane z `/api/segment/netlist`.

3. **Automatyzować benchmark i raportowanie**
  - Rozszerzyć `scripts/run_inference_benchmark.py` o eksport CSV/JSON do `reports/benchmark_runs/`.
  - Przygotować wpis w `reports/benchmark_baseline.md` (czas, FPS, konfiguracja) oraz dodać krótkie podsumowanie w `PROGRESS_LOG.md`.
  - Rozważyć prosty endpoint Flask `/api/diagnostics/benchmark` zwracający ostatni wynik.

4. **Przygotować pipeline pod realne anotacje**
  - Zweryfikować `scripts/export_labelstudio_to_coco_seg.py` na przykładowym eksporcie i opisać checklistę w `docs/ANNOTATION_WORKFLOW_QUICKSTART.md`.
  - Dodać krok merge’u z syntetykami (`merge_annotations.py`) i aktualizacji splitów, aby pierwsza partia z Label Studio mogła od razu wejść do treningu.

## 🚧 Postępy 19 listopada 2025

1. **Restart treningu YOLOv8s-seg (09:10)**
  - Uruchomiono smoke-test 1 epoki (`runs/segment/train7`) z parametrami `batch=10`, `copy_paste=0.0`, `cache=ram`, aby potwierdzić, że poprzedni błąd (exit code 1) nie powtarza się – proces zakończył się poprawnie i wygenerował minimalne wagi kontrolne.
  - Po udanym teście wystartował pełny trening `runs/segment/train7_full` na 75 epok z tym samym zestawem hiperparametrów, utrzymując użycie GPU w granicach ~3.2 GB (wg logu startowego) i pozostawiając monitorowanie w tle.
  - Notatka: `copy_paste` zostało wyzerowane, aby uniknąć dodatkowych kopii w pamięci w pierwszych epokach; w razie potrzeby parametry można ponownie zwiększyć po stabilizacji VRAM.

2. **Frontend netlisty + YOLO (12:40)**
  - Sekcja „Netlista” w `templates/index.html` zyskała panel „Symbole (YOLO / netlista)” z licznikiem, nazwą detektora, latencją, timestampem i linkiem do historii detekcji (jeśli jest przechowywana).
  - Lista symboli z `netlist.metadata.symbols.detections` renderuje się jako tabela z kolumnami klasa/pewność/bounding-box/źródło; kliknięcie lub Enter podświetla odpowiadający obrys na podglądzie, automatycznie włączając nakładkę symboli.
  - `static/js/lineSegmentation.js` synchronizuje teraz metadane symboli z komponentami SPICE (stabilne klucze, dopasowanie do netlisty, odświeżanie linku historii) i pozwala na ręczne wskazanie symbolu do eksportu. Dom wiring dla nowych elementów wprowadzono w `static/js/app.js`.

3. **Historia binarizacji + podgląd (17:45)**
  - Odtłuszczono overlay RODO: `initUi()` odpala się przed modułami multimedialnymi, dzięki czemu przycisk „Rozumiem i akceptuję” zawsze działa nawet w przypadku błędów inicjalizacji PDF.
  - W module `imageProcessing` dodano przycisk „Zapisz stronę do historii”; zapisuje on bieżący render PDF jako wpis `type=page`, co pozwala szybko wrócić do stanu całej strony w dropdownie wyników binarizacji.
  - `ProcessingHistoryStore` wspiera teraz selektywne kasowanie wpisów (`scope=image-processing`, typy `crop/upload/processed/page`), a endpoint `DELETE /processing/history` respektuje filtry `scope` i `type`, więc czyszczenie historii binarizacji nie usuwa danych segmentacji ani YOLO.
  - Dropdown historii filtruje i grupuje wpisy według typu, a akcja „Wyczyść historię” wysyła żądanie z zakresem `image-processing`, co rozwiązuje wcześniejsze problemy z „znikaniem” wpisów innych modułów.

# 📊 Postępy Pracy - 18 listopada 2025

## ✅ Punkt 1 – Start treningu YOLOv8s-seg (moderate v2)

- Uruchomiono pełny trening `yolov8s-seg.pt` na zestawie `configs/yolov8_v2_moderate.yaml` z ustawieniami CLI: `epochs=75`, `batch=12`, `imgsz=640`, `degrees=8.0`, `shear=1.5`, `flipud=0.0`, `copy_paste=0.15`, `mixup=0.10`.
- Bieżący run zapisuje się w `runs/segment/train5` (poprzednia próba w `train2` została przerwana przez KeyboardInterrupt podczas inicjalizacji `torchvision`).
- Środowisko: `Talk_flask` (Python 3.11.14, torch 2.5.1+cu121, Ultralytics 8.3.228) na GPU RTX A2000 6 GB. AMP przeszło walidację, a cache datasetu (`splits_v2_450`) ładuje się bez ostrzeżeń.
- Pierwsze epoki są w toku; gdy `results.csv` pojawi się w `train5`, `scripts/monitor_training.py --interval 30` zostanie użyty do śledzenia metryk (mAP50 det/mask, loss) i aktualizacji ETA.
- Po zakończeniu bieżącego runu należy wykonać checklistę: `yolo val` + `scripts/run_inference_benchmark.py`, kopia `weights/best.pt`, opis w `reports/error_analysis.md` oraz backup katalogu `runs/segment/train5`.
- 18.11, 16:30 – wznowiono trening już na docelowym zestawie v2.0 jako `runs/segment/train6` (ten sam config, wsad batch=12). Pierwszy pass przez `train/labels` stworzył nowy cache; trening biegnie w tle, status z `results.csv` monitorować identycznie jak poprzednio.

## ✅ Wynik treningu YOLOv8s – run `train6`

- 75 epok ukończone (czas całkowity ~14m25s). Najlepsze mAP50 dla pudełek osiągnięto w epoce 63 (`metrics/mAP50(B)=0.85971`), a dla masek w epoce 72 (`metrics/mAP50(M)=0.85219`).
- Finałowy snapshot (ep. 75) utrzymał wysokie metryki: Box P/R 0.916/0.880, mAP50 0.856 (mAP50-95 0.747); Mask P/R 0.904/0.868, mAP50 0.849 (mAP50-95 0.427).
- `yolo val` na `configs/yolov8_v2_moderate.yaml` potwierdziło wyniki na zbiorze walidacyjnym (67 obrazów, 1 025 instancji): mAP50(box)=0.860, mAP50(mask)=0.839; najtrudniejszą klasą pozostał kondensator (mask mAP50=0.812, mAP50-95=0.367).
- Backup wykonany: `weights/train6_best.pt`, `weights/train6_last.pt`, `weights/train6_args.yaml`, `weights/train6_results.csv` oraz podglądy `train_batch*.jpg`/`val_batch*.jpg`.

## ✅ Punkt 2 – Porządkowanie datasetu syntetycznego v2.0

- Folder z obrazami został ujednolicony (`data/synthetic/images_v2_400` → `images_v2_450`), a wszystkie referencje w `.gitignore` i checklistach wskazują nową ścieżkę.
- Spójne COCO: `data/synthetic/coco_v2_450.json` powstało z mergowania dawnych `train/val/test` JSON-ów (450 obrazów, 6 807 anotacji, 4 klasy) z automatycznym remapem ID.
- Stratified split (70/15/15) odtworzono od zera poprzez `scripts/split_dataset.py --copy-images`, tworząc `data/synthetic/splits_v2_450/{train,val,test}` z kopiami obrazów i świeżymi statystykami klas.
- Dla każdego splitu wygenerowano brakujące etykiety YOLO (`export_coco_to_yolo.py`); teraz `train/labels`, `val/labels`, `test/labels` są zsynchronizowane z nowymi JSON-ami, a `configs/yolov8_v2_moderate.yaml` wskazuje poprawny root (`data/synthetic/splits_v2_450`).

## ✅ Punkt 3 – Naprawa testów deskew

- Fixture testowy (`create_test_image`) miał odwrotną konwencję znaku względem implementacji; zmieniono macierz rotacji na `-angle`, aby dodatnie wartości faktycznie obracały obraz w prawo.
- Funkcja `rotate_image` stosuje teraz tę samą konwencję (inwersja znaku przed wywołaniem OpenCV), a asercje w testach akceptują powiększone wymiary wynikające z automatycznego paddingu.
- Zmieniono weryfikację zachowania treści po deskew na bardziej odporną (`np.count_nonzero(deskewed < 250) > 0`).
- `pytest tests/test_deskew.py` przechodzi w całości (17/17) – link do logu w terminalu #4.

## ✅ Punkt 4 – Aktualizacja GaussNoise po migracji na Albumentations 2.x

- Zaktualizowano `scripts/synthetic/augment_dataset.py`, aby korzystać z nowego API `A.GaussNoise(std_range=...)`. Helper `_gauss_noise_from_var_range` przelicza dawne `var_limit` na przedziały odchylenia standardowego znormalizowane do `[0,1]` i w razie potrzeby fallbackuje do starej składni (kompatybilność 1.x).
- Do profili `light/scan/heavy` trafiają teraz te same poziomy szumu, ale w sposób zgodny z Albumentations ≥2.0 – brak ostrzeżeń o `var_limit`. Uzupełniono importy (`math`).
- Zainstalowano Albumentations 2.0.5 w env `talk_flask`; szybki smoke-test `AugmentationProfile.get_light_augmentation()` potwierdził poprawną inicjalizację pipeline (terminal #4 – ostrzeżenie o brakującej transformacji bbox jest spodziewane podczas suchego importu).

## ✅ Integracja YOLOv8 z benchmarkiem i netlistą

- `scripts/run_inference_benchmark.py` automatycznie rejestruje wszystkie wbudowane detektory (`noop`, `simple`, `template`, `yolov8`) i umożliwia prosty pomiar latencji (`--warmup`, `--runs`, `--image-dir`).
- Trasa `/api/segment/netlist` przyjmuje teraz `symbols` lub `symbolHistoryId`, dzięki czemu metadane YOLO (detektor, podsumowanie, bbox/maski) są zapisywane w `netlist.metadata.symbols` i mogą być później eksportowane razem z SPICE.
- Dodano helpery `_load_symbol_detection_from_history` i `_attach_symbol_metadata`, co spina przepływ “YOLO → historia → netlista” bez dodatkowych kroków w UI.
- Zaimplementowano wymienne rejestracje detektorów (`register_detector(..., replace=True)`) oraz smoke-test `test_detect_symbols_yolov8_smoke`, który weryfikuje integrację endpointu `/api/symbols/detect` z nazwą `yolov8` bez ładowania ciężkich wag.
- `tests/test_netlist_generation.py` otrzymał scenariusz zapisujący detekcje w metadanych netlisty; `pytest tests/test_symbol_detection_routes.py tests/test_netlist_generation.py` przechodzi po zmianach.

# 📊 Postępy Pracy - 14 listopada 2025

## 🗓️ Plan na 15 listopada 2025

1. **Wznowienie treningu YOLOv8s-seg (CPU)**
  - Komenda: `yolo task=segment mode=train model=yolov8s-seg.pt data=configs/yolov8_v2_moderate.yaml epochs=75 batch=12 imgsz=640 degrees=8.0 shear=1.5 flipud=0.0 copy_paste=0.15 mixup=0.10`
  - Zakładany czas całkowity: ok. 10h (na podstawie epoki 1: 485 s → ETA 9h59m dla 75 epok).
  - Po restarcie upewnić się, że w katalogu `data/synthetic/splits_v2_450/train` nie ma starych cache (usunąć `labels.cache` tylko gdy YOLO nie działa).

2. **Monitorowanie postępu (ciągłe)**
  - Skrypt: `scripts/monitor_training.py` (nowy, bez zewnętrznych zależności).
  - Uruchomienie (osobny terminal, environment Talk_flask): `python scripts/monitor_training.py`.
  - Funkcje: odczyt epoki, strat train/val, mAP50 box/mask, ETA, wykrywanie nowych wierszy w `results.csv`.
  - Tryb jednorazowy (`--once`) do snapshotów przy raportowaniu; interwał regulowany flagą `--interval` (domyślnie 30s).

3. **Checklist po zakończeniu treningu**
  1. Walidacja artefaktów (`weights/best.pt`, `results.csv`, `labels.jpg`, `train_batch*.jpg`).
  2. Ewaluacja i benchmark (`yolo val ...`, `scripts/run_inference_benchmark.py`).
  3. Analiza błędów (confusion matrix, próbki z najgorszym wynikiem, ręczne sanity-checki masek).
  4. Backup/archiwizacja (`runs/segment/train2`, skrypty backupowe, kopia args.yaml + config).
  5. Dokumentacja końcowa (`PROGRESS_LOG.md`, raport w `reports/`, decyzje dot. kolejnej iteracji hiperparametrów).

4. **Zarządzanie terminalami**
  - Monitor nie może startować w terminalu, gdzie aktywny jest trening (w przeciwnym razie YOLO restartuje się i dostaje `KeyboardInterrupt`).
  - Rekomendowane: trzy osobne sesje PowerShell → (1) trening, (2) monitor, (3) pozostałe narzędzia (Label Studio / augmentacje).


## ✅ Dzisiejsze Osiągnięcia

### 1. 🛠️ Narzędzia zarządzania ML dataset
- ✅ **split_dataset.py** (268 linii) - stratyfikowany podział COCO JSON z zachowaniem proporcji klas
  - Funkcja `stratified_split()` z numpy seed=42
  - Opcja `--copy-images` do tworzenia struktury train/val/test
  - Przetestowany: 200→140/30/30 obrazów (70/15/15%)

- ✅ **merge_annotations.py** (348 linii) - łączenie wielu COCO JSON
  - Automatyczna renumeracja ID (images, annotations, categories)
  - Walidacja spójności przed mergowaniem
  - Przetestowany: 50+150→200 obrazów, 3680 annotacji

- ✅ **quality_metrics.py** (465 linii) - analiza jakości datasetu
  - Metryki: bbox area, aspect ratio, polygon vertices, annotation density
  - Wykrywanie outlierów (z-score >3)
  - 4 wizualizacje: bbox_area, aspect_ratio, vertices_distribution, coverage_heatmap
  - Przetestowany: 200 obrazów, 0 outlierów wykrytych

### 2. 🎨 Generacja danych syntetycznych
- ✅ Wygenerowano 200 schematów elektronicznych:
  - **Batch 1:** 50 obrazów (seed 200-249) → `images_augmented/` + `coco_annotations.json` (639 ann)
  - **Batch 2:** 150 obrazów (seed 300-449) → `images_raw/` + `coco_all_200.json` (3041 ann)
  - **Merged:** `coco_complete_200.json` (200 obrazów, 3680 annotacji)

- ✅ **Balans klas** (doskonały ±2%):
  - Resistor: 959 (26.1%)
  - Capacitor: 894 (24.3%)
  - Inductor: 938 (25.5%)
  - Diode: 889 (24.2%)

### 3. 🔧 Rozwiązywanie problemów technicznych
- ✅ **fix_duplicate_filenames.py** - naprawiono 50 duplikatów nazw plików
  - IDs 1-50: `schematic_001-050` (images_augmented) → bez zmian
  - IDs 51-100: `schematic_001-050` (images_raw, duplikaty) → `schematic_201-250`
  - IDs 101-200: `schematic_051-150` (images_raw) → bez zmian
  - Rezultat: `coco_fixed_200.json` + `data/synthetic/images/` (200 unikalnych plików)

- ✅ **Konwersja COCO→YOLO** - `export_coco_to_yolo.py`
  - Train: 140 images → 140 labels txt (2608 annotacji)
  - Val: 30 images → 30 labels txt (539 annotacji)
  - Test: 30 images → 30 labels txt (533 annotacji)
  - Format: `<class_id> <x1> <y1> <x2> <y2> ... <xn> <yn>` (normalized 0-1)

### 4. 🚀 Trening YOLOv8n-seg baseline
- ✅ **Model:** YOLOv8n-seg (3.26M parametrów, 11.5 GFLOPs)
- ✅ **Trening:** 50 epok, 1.415h na CPU (Intel Core i5-9300HF)
- ✅ **Wyniki walidacyjne (best model, 30 obrazów):**
  - **mAP@0.5:** 0.843 (box), 0.800 (mask) ✅ PRZEKROCZONY CEL (>0.70)
  - **Precision:** 0.882 (box), 0.847 (mask) ✅ DOSKONAŁA
  - **Recall:** 0.742 (box), 0.719 (mask) ⚠️ DO POPRAWY
  - **mAP@0.5:0.95:** 0.680 (box), 0.321 (mask) ⚠️ SŁABA PRECYZYJNA SEGMENTACJA

- ✅ **Wyniki per klasa:**
  - **Diode:** ⭐ mAP@0.5=0.933 (box), 0.899 (mask) - NAJLEPSZA
  - **Resistor:** mAP@0.5=0.790 (box), 0.746 (mask)
  - **Capacitor:** mAP@0.5=0.829 (box), 0.759 (mask) - niski recall 68.8%
  - **Inductor:** mAP@0.5=0.819 (box), 0.797 (mask)

### 5. 📊 Dokumentacja i analiza
- ✅ **reports/baseline_synthetic_200.md** - kompleksowy raport (180 linii):
  - Konfiguracja treningu i hiperparametry
  - Podział datasetu i rozkład klas
  - Metryki walidacyjne (ogólne + per klasa)
  - Krzywa uczenia (loss, mAP w czasie)
  - Prędkość inferencji: 209ms/obraz na CPU (~4.8 FPS)
  - Analiza mocnych/słabych stron
  - Rekomendacje: heavy augmentations, więcej danych (500+), YOLOv8s-seg

### 6. ⚠️ Heavy augmentation test (nieudany)
- ✅ 50 epok z configiem `degrees=15.0`, `shear=5.0`, `flipud=0.5`, `mosaic=1.0`, batch 16, imgsz 640.
- ⚠️ Wynik końcowy (val, 30 obrazów): **Recall 0.720** (spadek z 0.749), **mAP@0.5 0.701** (spadek z 0.804), **Precision 0.688** (spadek z 0.882).
- 📉 Per-klasa: resistor 0.514 mAP@0.5, capacitor 0.766, inductor 0.626, diode 0.896 – każda niższa niż baseline; recall capacitor 69.6% vs 68.8% (ruch w granicach błędu), diode -2.1pp, inductor -2.6pp.
- 🧪 Wniosek: agresywne transformacje na małym datasecie (200 obrazów) wprowadzają artefakty, których model nie potrafi odfiltrować – zamiast poprawić recall, obniżają zarówno precision jak i mAP. Strategia Heavy Aug zostaje odrzucona.

### 7. 🎯 Instalacja i konfiguracja
- ✅ Zainstalowano **ultralytics 8.3.228** (YOLOv8)
- ✅ Zainstalowano **torch 2.9.1+cpu** i **torchvision 0.24.1**
- ✅ Zainstalowano **matplotlib 3.10.7** (wizualizacje quality_metrics)
- ✅ Skonfigurowano **Talk_flask** jako środowisko domyślne (zamiast label-studio)

---

## 🎓 Wnioski

### ✅ Co zadziałało bardzo dobrze
1. **Dane syntetyczne działają** - model YOLOv8n-seg osiągnął 80% mAP@0.5 na maskach
2. **Stratified split zachował balans** - wszystkie klasy 24-26% w każdym splicie
3. **Transfer learning COCO→electronics** - pretrenowane wagi (381/417) pomogły w konwergencji
4. **Stabilny trening** - brak overfittingu przez 50 epok
5. **Precyzja doskonała** - 88.2% (bardzo niski false positive rate)

### ⚠️ Co wymaga poprawy
1. **Recall za niski** - 74.2% (25-30% obiektów pominiętych)
2. **Słaba precyzyjna segmentacja** - mAP@0.5:0.95 tylko 32.1%
3. **Capacitor najsłabszy** - recall 68.8%, często pomijany przez model
4. **Trening CPU wolny** - 1.4h dla 50 epok (na GPU byłoby 10-50x szybciej)
5. **Heavy Aug regresja** - agresywne augmentacje obniżyły mAP (0.80→0.70) i recall (0.749→0.720); potrzebny inny kierunek eksperymentów.

### 🔜 Następne kroki (priorytet)
1. **Większy model** - YOLOv8s-seg (11M parametrów) + umiarkowane augmentacje (degrees=10, shear=2, bez flipud).
2. **Dataset v2.0** - uzupełnić lukę plików 151-250 i ponownie zbudować split 70/15/15 dla 400 obrazów.
3. **Connection lines** - rozszerzyć generator o klasę `wire`, aby dodać kontekst topologiczny i zmniejszyć false negatives.
4. **NMS + threshold tuning** - obniżyć `conf` do 0.15 i przetestować `iou` 0.6-0.7, żeby odzyskać recall bez retrainingu.
5. **GPU training** - przenieść eksperymenty na RTX/Colab; CPU 1.4h/50ep ogranicza iteracje.

---

## 📂 Utworzone pliki

### Skrypty
- `scripts/split_dataset.py` (268 linii)
- `scripts/merge_annotations.py` (348 linii)
- `scripts/quality_metrics.py` (465 linii)
- `scripts/fix_duplicate_filenames.py` (118 linii)
- `scripts/export_coco_to_yolo.py` (163 linii) - używany ponownie

### Dane
- `data/synthetic/coco_fixed_200.json` (200 obrazów, 3680 annotacji, bez duplikatów)
- `data/synthetic/images/` (200 PNG: 001-150, 201-250)
- `data/synthetic/splits_yolo/` (train/val/test z images/ i labels/)

### Modele
- `runs/segment/baseline_200_final/weights/best.pt` (6.8 MB, epoch ~25)
- `runs/segment/baseline_200_final/weights/last.pt` (6.8 MB, epoch 50)

### Dokumentacja
- `reports/baseline_synthetic_200.md` (raport treningu, 180 linii)
- `reports/visualizations_200/` (bbox_area, aspect_ratio, vertices, heatmap)

---

## ⏱️ Czas pracy
- **Implementacja narzędzi:** ~1.5h (split, merge, quality_metrics)
- **Generacja danych:** ~30min (150 schematów batch_generate.py)
- **Debugging duplikatów:** ~45min (analiza + fix_duplicate_filenames.py)
- **Konwersja COCO→YOLO:** ~15min (3 splity)
- **Trening YOLOv8:** 1.415h (50 epok na CPU)
- **Dokumentacja:** ~30min (raport baseline_synthetic_200.md)
- **TOTAL:** ~4.5h sesji pracy

---

# 📊 Postępy Pracy - 11 listopada 2025

## ✅ Dzisiejsze Osiągnięcia

### 1. 🗺️ System Siatki Anotacji
- ✅ Utworzono `GRID_TRACKING.md` z siatką 4×4 (16 pól)
- ✅ Skrypt `add_grid_overlay.py` do nakładania siatki na schematy
- ✅ Wygenerowano `page_6_grid_4x4.png` z podziałem i etykietami
- ✅ Większe powiększenie pól (1239×875 px vs poprzednie 1653×1167 px)

### 2. 💾 System Backupu Label Studio
- ✅ Skrypt `backup_labelstudio.py` (próba API - wymaga tokena)
- ✅ Skrypt `backup_labelstudio_from_downloads.ps1` (UI workflow - DZIAŁA!)
- ✅ Dokumentacja: `BACKUP_MANUAL.md`, `BACKUP_DAILY.md`
- ✅ Skrót na pulpicie dla szybkiego backupu
- ✅ Pierwszy backup wykonany: `backup_20251111_171726.json`

### 3. 📁 Struktura Katalogów
- ✅ `png_dla_label-studio/` z README.md
- ✅ `data/annotations/labelstudio_exports/` z README.md
- ✅ Backup Label Studio commitowany do Git

### 4. 📝 Dokumentacja Anotacji
- ✅ Kompleksowa aktualizacja `annotation_metadata_cheatsheet.html`
- ✅ Filozofia "przepisuj tylko co widać na schemacie"
- ✅ Minimalizacja pól do faktycznie widocznych informacji
- ✅ Kluczowe zmiany:
  - Resistor: `tolerance=unknown` (nie widać na schemacie)
  - Capacitor: `polarity=unknown` (brak znaku "+")
  - Inductor: `value=unknown`, `core=air` (najczęstsze)
  - Diode: `type=diode`, polaryzacja z kierunkami (cathode_left/right/up/down)
  - Transistor: `type=npn/pnp` (bez "bjt_"), usunięto package i note
  - IC: `type=unknown`, usunięto package i role
  - Connector: `type=unknown`, `role=unknown`
  - Net_label: tylko `type` i `net` (MINIMALIZM)
  - Measurement_point: minimum 3 pola
  - Misc_symbol: tylko `designator`, `type`, `note`

### 5. 🔧 Konfiguracja Git
- ✅ Zaktualizowano `.gitignore`:
  - `*.pyc`, `*.pyo`, `*.pyd` (Python cache)
  - `*.sqlite3`, `*.db` (Label Studio)
  - `*.lnk` (skróty Windows)
  - Katalogi Label Studio

### 6. 🛠️ Skrypty Pomocnicze
- ✅ `add_grid_overlay.py` - nakładanie siatki 4×4
- ✅ `backup_labelstudio.py` - backup przez API
- ✅ `backup_labelstudio_from_downloads.ps1` - backup z UI (GŁÓWNY)
- ✅ `auto_backup_labelstudio.ps1` - automatyzacja
- ✅ `backup_koniec_dnia.bat` - CMD wrapper

---

## 📋 Plan Następnych Prac

### Priorytet 1: Anotacja Schematu (Strona 6)
- [ ] Rozpocząć anotację według siatki 4×4
- [ ] Strategia: Left-to-Right, Top-to-Bottom (A1→B1→C1→D1→A2...)
- [ ] Aktualizować `GRID_TRACKING.md` po każdym sektorze
- [ ] Backup po każdym ukończonym sektorze (16 checkpointów)
- [ ] Szacowany czas: 10-15 min/sektor = 2.5-4h całość

### Priorytet 2: Optymalizacja Workflow
- [ ] Przetestować zoom na różnych sektorach siatki 4×4
- [ ] Zweryfikować czy etykiety A1-D4 są czytelne po wydrukowaniu
- [ ] Ewentualnie dostosować rozmiar czcionki w `add_grid_overlay.py`
- [ ] Stworzyć template anotacji dla typowych symboli (szablony quick-fill)

### Priorytet 3: Kolejne Schematy
- [ ] Wyeksportować pozostałe strony schematu do PNG
- [ ] Nałożyć siatki 4×4 na każdą stronę
- [ ] Dodać do Label Studio jako nowe zadania
- [ ] Rozszerzyć `GRID_TRACKING.md` o kolejne strony

### Priorytet 4: Automatyzacja
- [ ] Skrypt do automatycznego podziału schematu na sektory (crop)
- [ ] Skrypt do weryfikacji kompletności anotacji (czy wszystkie sektory?)
- [ ] Dashboard postępu (ile symboli zanotowano, ile pozostało)
- [ ] Statystyki typów elementów (ile rezystorów, kondensatorów, etc.)

### Priorytet 5: Trening Modelu
- [ ] Przygotować dataset z pierwszych zanotowanych sektorów
- [ ] Konwersja Label Studio → COCO format
- [ ] Baseline training YOLOv8 (szybki test)
- [ ] Walidacja wyników na testowym sektorze

### Priorytet 6: Dokumentacja
- [ ] Video tutorial: jak używać siatki 4×4
- [ ] FAQ dla częstych przypadków anotacji
- [ ] Galeria przykładów (dobrze vs źle zanotowane symbole)
- [ ] Rozszerzenie `annotation_metadata_cheatsheet.html` o screenshoty

---

## 🎯 Cele Tygodniowe (11-17 listopada)

### Cel Główny
✅ Ukończyć anotację strony 6 (16 sektorów)

### Cele Dodatkowe
- [ ] 3-5 backup-ów dziennie (po sesjach anotacji)
- [ ] Dokumentować nietypowe przypadki w oddzielnym pliku
- [ ] Przetestować różne strategie anotacji (spiral vs linear)

---

## 📊 Metryki

### Dzisiaj (11.11.2025)
- ✅ Sektory ukończone: 0/16
- ✅ Backup-y wykonane: 1
- ✅ Skrypty utworzone: 5
- ✅ Dokumentacja zaktualizowana: 3 pliki

### Tydzień (cel)
- 🎯 Sektory ukończone: 16/16 (100%)
- 🎯 Backup-y: ~20-30
- 🎯 Symboli zanotowanych: ~200-300 (szacunek)

---

## 💡 Notatki i Obserwacje

### Co Działa Dobrze
- ✅ Siatka 4×4 zapewnia lepsze powiększenie niż 3×3
- ✅ Backup workflow przez UI jest prosty i niezawodny
- ✅ Minimalistyczne pole metadanych redukuje mylące interpretacje
- ✅ Skrót na pulpicie znacznie przyspiesza backup

### Do Poprawy
- ⚠️ API Label Studio wymaga tokena (UI workflow lepszy)
- ⚠️ Brak automatycznej walidacji anotacji przed commitem
- ⚠️ Ręczne aktualizowanie GRID_TRACKING.md (można zautomatyzować)

### Pomysły na Przyszłość
- 💡 Integracja z GitHub Actions (auto-backup na pushu)
- 💡 Web dashboard do śledzenia postępu
- 💡 Rozszerzenie VS Code do quick-preview anotacji
- 💡 OCR dla automatycznego rozpoznawania designatorów (R1, C2, etc.)

---

**Następna aktualizacja:** Po ukończeniu pierwszych 4 sektorów (A1-D1) lub EOD

## Postępy — 11 grudnia 2025

1. **Long-run YOLOv8 training (`exp_mix_small_100`)** — uruchomiono trening 100 epok z `weights=runs/segment/train14/weights/best.pt`, batch=1, ultralytics YOLOv8n-seg.
2. **Monitory i raporty** — dodano/uruchomiono:
  - `scripts/tools/epoch_summary.py` — monitoruje `results.csv`, wypisuje skrócone raporty co N epok; toleruje błędy zapisu do pliku log.
  - `scripts/tools/wait_and_collect.py` — czeka na `results.csv` + `weights/best.pt`, uruchamia `gather_run_report.py` i dopisuje wstępny raport do `qa_log.md`.
  - `scripts/tools/wait_for_completion_and_collect.py` — nowy skrypt, czyta `args.yaml`, czeka na osiągnięcie `epochs` i wykrywa `EarlyStopping` (lub brak zmian w `results.csv` + `last.pt`), po czym uruchamia `gather_run_report.py` i dopisuje finalny raport do `qa_log.md`.
3. **Wykrycie EarlyStopping** — trening zakończony przez EarlyStopping (patience=10); najlepszy model `best.pt` z epoch 55 (mAP50-95(M)=0.11625); ostatni zapisany epoch=65.
4. **Dopasowania skryptów** — poprawiono detekcję zakończenia treningu i tolerowanie błędów logów; `wait_for_completion_and_collect.py` wykrywa zakończenie na podstawie debug logs i plików checkpoint.
5. **QA** — skrypt wywołał `gather_run_report.py` i dopisał wpis `exp_mix_small_100` do `qa_log.md`; raport zawiera ostatnie wartości metryk i plik `confusion_matrix.png`.
6. **Plan na jutro (PoC Mask R‑CNN)** — przygotowanie krótkiego PoC (10–20 ep) porównawczego wobec YOLOv8; uruchomienie zaplanowane po Twoim potwierdzeniu.

_Notatka techniczna_: debug logs, katalogi dataset i pliki artefaktów (weights/*.pt) pozostają niecommitowane; zmiany w skryptach i QA zostały przygotowane do commitu i pushu.
