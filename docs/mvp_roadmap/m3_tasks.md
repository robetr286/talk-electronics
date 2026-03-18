### M3 — Symbol detection (feature/m3-symbol-detection)

Cel: dostarczyć prosty, reprodukowalny pipeline detekcji symboli (YOLOv8‑seg/prototype) z inferencją i UI overlay, żeby uzyskać działającą ścieżkę E2E od obrazu → detekcje → netlist.

Podzadania (mikro-kroki):
1) Dataset (Priorytet: REAL images)
  - zebrać **min. 30 realnych** przykładowych schematów (główne źródła: zeskanowane dokumenty, exporty PDF, zdjęcia) — traktujemy je priorytetowo
  - przygotować walidacyjny subset ~20 realnych obrazów (różne przypadki: skan, foto, różne rozdzielczości)
  - syntetyczne obrazy dodajemy jedynie jako uzupełnienie (do ~50 total) — zastosować augmentacje: 'scan', 'heavy' tylko jeśli potrzeba skali
  - dodać krótkie zasady anonimizacji (usuń metadane, maskuj poufne pola) i sprawdź licencje / prawa do zdjęć

2) Quick prototyping (Copilot)
  - przygotować training config (yolov8n-seg) na subset
  - uruchomić 1–3 epoch prototypu dla szybkiego baseline
  - zapisać artifact (weights) i baseline metrics (mAP, IoU)

3) Inference + API
  - dodać endpoint REST /inference/symbols (POST image -> JSON detections)
  - fallback CPU/GPU handling

4) UI overlay
  - prosty overlay box/mask z legendą i checkboxem do włączenia/wyłączenia

5) Tests + E2E
  - dodać unit tests dla inference endpoint
  - dodać prosty Playwright smoke check (upload -> show detections)

Oszacowanie czasu: 2 osoby × 4h/dzień:
- dzień 1 (dataset + augmentacje)
- dzień 2 (train prototyp + inference wiring)
- dzień 3 (UI overlay + tests)

Zależności: dataset, CI runner, miejsce na artefakty (runs/weights/)
