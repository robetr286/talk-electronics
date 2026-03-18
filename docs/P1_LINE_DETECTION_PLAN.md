# P1.1 — Plan diagnozy i naprawy rozpoznawania linii (przewodów / węzłów)

Status: in-progress

Źródło: zgłoszenia i obserwacje użytkownika (25 listopada 2025) — aplikacja bardzo słabo wykrywa przewody/linie i myli tekst z końcówkami; węzły nie są odróżniane.

Cele krótkoterminowe (dziś):
- zebrać przykładowe, błędne przypadki (PDF/PNG grayscale/PNG binary) i umieścić je w katalogu testowym,
- powtórnie przeanalizować aktualny pipeline segmentacji linii (preprocessing, model, postprocessing),
- zaproponować i zaimplementować szybkie poprawki postprocessingowe (morfologia, filtry, heurystyki) jako POC,
- przygotować minimalne testy regresji (unit + integration) dla postprocessingu linii.

Zadania i kroki:
1) Reprodukcja — przygotować zestaw przykładów
   - zebrać 15–30 przypadków, w tym: PDF strony z rysunkiem, PNG grayscale, PNG binarne, przykłady z labelami/tekstem blisko linii.
   - zapis każdego przykładu w `tests/fixtures/p1_line_examples/` (plik README opisujący źródło i oczekiwany wynik).

2) Analiza pipeline (jak działa teraz)
   - sprawdzić preprocessing: czy obrazy są skalowane, binarizowane, jakie progi stosowane,
   - sprawdzić model: wejściowy rozmiar, augmentation w czasie inferencji,
   - sprawdzić postprocessing: jak segmenty łączone, czy wykrywany jest tekst (OCR) i czy wpływa na klasyfikację końcówek.

3) Szybkie poprawki (POC)
   - dodać filtrację etykiet/tekstów: uruchomić OCR (tesseract/OPt) i wykluczyć kratki krótkich napisów z klasyfikacji końcówek,
   - zmodyfikować postprocessing: erozja/dylatacja, połączenie konturów, usuwanie krótkich segmentów, heurystyka łączenia zbliżonych linii,
   - dodać thresholding geometryczny (minimalna długość segmentu, kąty łączenia),
   - napisać testy jednostkowe dla postprocessingu (wejście: syntetyczne segmenty; oczekiwane: scalone, odfiltrowane).

4) Metryki i kryteria akceptacji
   - prowizoryczny benchmark na zebranym zbiorze: precision/recall/lokalne F1 dla segmentów/przewodów,
   - minimalne kryteria: recall (przewodów) >= 0.7 OR redukcja false positives (tekst) o >= 50% względem baseline (w zależności od wyników),
   - ujawnienie szczegółowego raportu po POC (przed retrainem modelu).

5) Dalsze kroki po POC
   - jeśli POC daje poprawę → uzupełnić treningowe dane i retrain modelu (wyższa skuteczność),
   - zintegrować rozwiązanie i dodać E2E smoke test automatycznie uruchamiany w CI (przy push/PR).

Materiały/testy dodane przez mnie dziś (miejsce):
- dodać pliki przykładowe do `tests/fixtures/p1_line_examples/` (jeśli dostarczasz pliki, wkleję je tam),
- utworzyć unit test placeholder `tests/unit/test_line_postprocessing.py` (szablon).

Plan komunikacji: codzienny krótkie raporty — co zostało zrobione i jakie wyniki metryk.

---

Jeżeli potwierdzasz, zaczynam od utworzenia folderu `tests/fixtures/p1_line_examples/` i szablonu testu — potem zbiorę przykłady i uruchomię POC postprocessing.
