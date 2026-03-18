## Zbieranie i przygotowanie danych — realne schematy (instrukcja)

Cel: zebrać co najmniej 30 realnych schematów (skany / eksporty PDF / zdjęcia) i przygotować walidacyjny podzbiór ~20 obrazów, gotowy do annotacji i treningu.

Kroki (przyjazne dla zespołu):
1) Gromadzenie obrazów
   - lokalizacja docelowa: `data/real/` (stwórz katalog jeśli nie ma)
   - nazewnictwo: `real_YYYYMMDD_source_001.png` (np. real_20251209_scan_acme_001.png)
   - zbierz metadane: source, author, licencja/zgoda, krótki opis (CSV lub YAML per obraz)

2) Anonimizacja
   - jeżeli obraz zawiera wrażliwe fragmenty (numery seryjne, adresy) -> zamaskować (prostokąt/blur)
   - usunąć metadane EXIF

3) Walidacja / curation
   - wybierz 20 obrazów różnorodnych (rozmiary, typy, artefakty skanu) -> umieść w `data/real/val/`

4) Anotacja
   - przygotować Label Studio config (mask/bbox/segmentation) lub bezpośrednio JSON COCO
   - priorytet: oznacz symbol (klasa) i bbox/segmentation dla symboli kluczowych (resistor, capacitor, inductor, diode, junction)

5) Suplementacja syntetyczna (opcjonalna)
   - dopiero gdy realnych przykładów będzie < 40, uzupełnić z gen syntetycznych + augmentacje: 'scan', 'heavy'

6) Automatyczny check
   - zapisz proste sanity-check script `scripts/dataset/validate_real.py`, który sprawdzi brak EXIF, rozmiary, liczbę plików.

Sugerowany workflow (Ty / Copilot):
- Ty: zebrać obrazy, potwierdzić licencje i anonimowość oraz dobrać walidacyjny subset.
- Copilot: przygotować foldery, sanity-check script, Label Studio config (jeśli chcemy annotować tam), wykonać pipeline konwersji do COCO (jeśli potrzeba).
