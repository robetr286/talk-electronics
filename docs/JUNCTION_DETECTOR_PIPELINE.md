# Junction Detector Pipeline

Ten dokument opisuje kompletną ścieżkę przygotowania modelu junction (kropki na skrzyżowaniach linii) wraz z integracją w backendzie.

## 1. Zbieranie patchy (export)

1. Aktywuj środowisko: `conda activate talk_flask`.
2. Uruchom skrypt eksportujący dla wybranego katalogu z arkuszami:
   ```bash
   python scripts/export_junction_patches.py data/sample_benchmark --limit-per-image 64 --processing-scale 0.75
   ```
3. Po zakończeniu sprawdź raport `data/sample_benchmark/junction_patches/export_summary.json` oraz `manifest.csv`.

Parametry `--limit-per-image` i `--processing-scale` pomagają kontrolować liczbę patchy i czas działania.

## 2. Ręczne etykietowanie patchy

1. Sprawdź folder `data/sample_benchmark/junction_patches/unknown/` i przenieś pliki do `dot_present/` lub `no_dot/`.
2. Po reorganizacji dopasuj manifest do struktur katalogów:
   ```bash
   python scripts/sync_junction_manifest.py --data-root data/sample_benchmark/junction_patches --backup
   ```
3. Manifest zawiera kolumny `filename,label,node_id,...`. Skrypt zachowa brakujące wiersze i utworzy kopię zapasową, jeśli podano `--backup`.

## 3. Trening modelu

1. Upewnij się, że `junction_patches/manifest.csv` ma co najmniej kilkadziesiąt przykładów w każdej klasie.
2. Uruchom trening:
   ```bash
   python scripts/train_junction_classifier.py \
       --data-root data/sample_benchmark/junction_patches \
       --epochs 20 \
       --batch-size 64 \
       --val-split 0.2
   ```
3. Po treningu otrzymasz:
   - `models/junction_classifier.onnx`
   - `models/junction_classifier.metrics.json` (dokładność, strata, metadane uruchomienia)
4. Jeśli dataset jest mały, zmniejsz `--val-split` lub zwiększ liczbę epok dopiero po zebraniu większej próbki.

## 4. Integracja w backendzie

1. (Opcja globalna) Zaktualizuj `configs/line_detection.defaults.json`, aby `junction_detector.enabled`/`junction_patch_export.enabled` przyjęły właściwe wartości; plik jest wczytywany przy starcie aplikacji.
2. (Opcja per-request) W konfiguracji detekcji linii ustaw:
   ```python
   from talk_electronic.services.line_detection import (
       LineDetectionConfig,
       JunctionDetectorConfig,
   )

   config = LineDetectionConfig(
       junction_detector=JunctionDetectorConfig(
           enabled=True,
           model_path=Path("models/junction_classifier.onnx"),
           threshold_dot_present=0.6,
           threshold_no_dot=0.6,
       ),
   )
   ```
3. Uruchom `/api/segment/lines` i sprawdź w odpowiedzi:
   - pole `metadata.junction_detection`
   - atrybuty `junction_state`, `junction_label`, `junction_confidence` w sekcji `nodes`
4. Stany węzłów: `auto_connected` (kropka potwierdzona), `blocked` (brak kropki), `needs_review` (niepewne). Dla węzłów o niższej liczbie krawędzi ustawiane jest `not_applicable`.

## 5. Checklista przed wdrożeniem

- [ ] `export_summary.json` pokazuje ≥200 patchy łącznie.
- [ ] Udział klas (`dot_present`, `no_dot`) jest zbliżony – maks. 60/40.
- [ ] `val_acc` w `models/junction_classifier.metrics.json` ≥ 0.85.
- [ ] Backend loguje `metadata.junction_detection.available=True` (oznacza załadowany model).
- [ ] W UI zaplanowano ekspozycję `junction_state` i flagi `junction_policy` (zob. plan z 1.12.2025).

Po spełnieniu powyższych punktów JunctionDetector można włączyć domyślnie w środowisku QA. Dokument aktualizuj wraz z kolejnymi iteracjami modelu/heurystyk.
