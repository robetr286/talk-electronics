Cel: katalog z przykładami schematów używanymi jako fixtures do testów P1: poprawa rozpoznawania linii.

Struktura katalogu (zalecana):

- tests/fixtures/p1_line_examples/raw/
  - w tym oryginalne obrazy (PDF/PNG/JPG). Nazwy plików: <id>_<short-desc>.<ext> (np. 001_scan1.png).
- tests/fixtures/p1_line_examples/annotations/
  - odpowiadające pliki anotacji (opcjonalnie). Nazwa taka sama jak obraz: <id>_<short-desc>.json
  - format anotacji: prosty JSON z polami: {"image":"<filename>", "annotations": [ ... ]}
- tests/fixtures/p1_line_examples/meta.json (opcjonalnie)
  - zawiera meta-dane kolekcji: autor, źródło, licencja, anonymization=true/false, comments.

Zasady i najlepsze praktyki:
- Nie dodawaj prywatnych/chronionych danych. Przed dodaniem usuń lub zasłoń dane wrażliwe.
- Jeżeli pliki są duże (> 5 MB) — rozważ zmniejszenie rozdzielczości (przykład: 150–300 DPI) lub dodanie tylko wycinków (crop) zamiast pełnych PDF-ów.
- Zachowuj rozszerzenia: PDF/PNG/JPG. Dla PDF możesz dodać plik jako <id>_page1.pdf lub wyodrębnić PNG per strona.
- Nazewnictwo: id trzycyfrowe z prefixem (np. 001_…), ułatwia porządkowanie i parametryzację testów.
- Dodaj plik anotacji dla przykładów, które mają poprawne ground-truth — ułatwia metryki.

Kopiowanie lokalne (PowerShell przykład):
- Stwórz katalogi (jeżeli nie istnieją):
    New-Item -ItemType Directory -Force -Path tests\fixtures\p1_line_examples\raw
    New-Item -ItemType Directory -Force -Path tests\fixtures\p1_line_examples\annotations

- Skopiowanie pliku (przykład):
    Copy-Item -Path C:\scans\schemat1.png -Destination tests\fixtures\p1_line_examples\raw\001_schemat1.png

Jak dodać commit:
- Dodaj tylko niepoufne i małe pliki. Jeżeli musisz dodać większe zasoby, rozważ przechowanie poza repo (np. server S3) i zamieść skrypt pobierający je do tests/fixtures podczas CI.

Jeżeli chcesz, mogę teraz:
- dodać przykładowe pliki ".gitkeep" lub README dopracowany w repo,
- przygotować skrypt walidujący (scripts/validate_fixtures.py),
- albo podać szczegółowe polecenia PowerShell, które skopiują grupę plików i nadadzą im poprawne nazwy.
