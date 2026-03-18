# Symbol Detection Integration Map

This document describes how symbol detectors interact with the Flask application and where new components should plug in.

## High-Level Flow
1. **Upload** (`/upload` in `talk_electronic.routes.pdf_routes`): PDF is stored, first page rendered.
2. **Preprocessing** (`talk_electronic.routes.processing` + services in `talk_electronic/services`): produce binary masks, skeletons, and candidate segments.
3. **Symbol Detection** (`talk_electronic.routes.symbol_detection`): run wybrany detektor na renderowanej stronie PDF lub obrazie dostarczonym inline i otrzymaj `DetectionResult` w formacie JSON.
4. **Post-processing**: associate detections with netlist extraction, display overlays in the front-end, and feed confidence metrics to the diagnostic chat.

## Detector Lifecycle
- Registry implementation lives in `talk_electronic/services/symbol_detection/registry.py`.
- Detectors must inherit from `SymbolDetector` (see `base.py`) and implement `detect` + optional `warmup`/`unload`.
- Register detectors during app start-up, e.g. in `talk_electronic/__init__.py`:
  ```python
  from talk_electronic.services.symbol_detection import available_detectors, register_detector
  from talk_electronic.services.symbol_detection.noop import NoOpSymbolDetector
  from talk_electronic.services.symbol_detection.simple import SimpleThresholdDetector
  from talk_electronic.services.symbol_detection.template_matching import TemplateMatchingDetector

  if NoOpSymbolDetector.name not in available_detectors():
      register_detector(NoOpSymbolDetector.name, NoOpSymbolDetector)
  if SimpleThresholdDetector.name not in available_detectors():
      register_detector(SimpleThresholdDetector.name, SimpleThresholdDetector)
  if TemplateMatchingDetector.name not in available_detectors():
      register_detector(TemplateMatchingDetector.name, TemplateMatchingDetector)
  ```
- Store heavy weights under `models/weights/<detector_name>/` and load lazily inside `warmup`.

### Available Detectors

1. **NoOpSymbolDetector** (`noop`)
   - Baseline detector zwracający puste wyniki
   - Użycie: testowanie API bez rzeczywistej detekcji

2. **SimpleThresholdDetector** (`simple`)
   - Prosty detektor oparty na progowaniu i konturach
   - Użycie: quick proof-of-concept, debugging

3. **TemplateMatchingDetector** (`template_matching`) ✨ NEW
   - Baseline detektor wykorzystujący OpenCV template matching
   - Multi-scale search (skale: 0.5, 0.75, 1.0, 1.25, 1.5)
   - Non-maximum suppression (NMS) z IoU threshold
   - Szablony: 40 PNG (5 kategorii × 8 orientacji)
   - Kategorie: resistor, capacitor, inductor, diode, transistor
   - Konfiguracja: `threshold=0.7`, `nms_threshold=0.3`
   - Szablony w: `data/templates/<category>/<symbol>_<angle>deg.png`
   - Użycie: baseline do benchmarków przed wdrożeniem deep learning

## API Surface
- **Lista detektorów**: `GET /api/symbols/detectors`
  - Zwraca `{ "detectors": [{"name": "noop"}, ...], "count": 2 }`.
- **Uruchomienie detekcji**: `POST /api/symbols/detect`
  - Pola wejściowe:
    ```json
    {
      "detector": "simple",
      "imageUrl": "/uploads/..." ,
      "imageData": "data:image/png;base64,...",
      "storeHistory": true
    }
    ```
    `imageUrl` oraz `imageData` są opcjonalne – należy dostarczyć przynajmniej jedno źródło. Parametr `storeHistory` zapisze wynik do `ProcessingHistoryStore`.
  - Odpowiedź:
    ```json
    {
      "detector": {"name": "simple", "version": "1"},
      "count": 3,
      "detections": [...],
      "summary": {"latencyMs": 12.4, "rawOutput": {...}},
      "source": {"source": "inline", "imageShape": [768, 1024, 3]},
      "historyEntry": {...}
    }
    ```
- **Front-end**: moduł `static/js/symbolDetection.js` udostępnia UI na zakładce „Detekcja symboli”: pobiera listę detektorów, obsługuje wybór źródła (bieżąca strona PDF lub plik) i renderuje podgląd z obrysami.

## Data Contracts
- `DetectionResult` → JSON:
  ```json
  {
    "detector": {"name": "simple", "version": "1"},
    "count": 3,
    "detections": [
      {
        "id": "component-0001",
        "label": "component",
        "score": 0.78,
        "bbox": [120.0, 84.0, 42.0, 38.0],
        "metadata": {"area": 1600.0, "aspect_ratio": 1.1}
      }
    ],
    "summary": {"latencyMs": 12.4, "rawOutput": {"components": 6, "emitted": 3}},
    "source": {"source": "inline", "imageShape": [768, 1024, 3]},
    "historyEntry": {
      "id": "symbols-...",
      "url": "/uploads/processed/symbol-detections/...json"
    }
  }
  ```
- Netlist pipeline będzie w przyszłości korzystać z detekcji do poprawy klasyfikacji komponentów; rekomendowane jest dodawanie w `metadata` pól `node_hint` oraz cech opisujących typ symbolu.

## Operational Considerations
- Maintain a singleton detector instance per process; reuse `DetectorRegistry.create` outputs and keep handles in `current_app.extensions`.
- Provide `scripts/warmup_detectors.py` to pre-load weights and verify availability (future task).
- Log detector latency and number of detections via `app.logger` for observability; aggregate metrics in diagnostics dashboard.
- When shipping new detectors, add regression tests in `tests/test_symbol_detection_*.py` using lightweight fixtures.
