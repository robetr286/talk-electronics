# Backlog: GRAPH_REPAIR - priorytety i krótkie zadania

Ten plik zawiera listę priorytetowych kroków, które należy wykonać aby poprawić i zintegrować proces naprawy szkieletów w pipeline.

1) Stabilizacja walidacji i gatingu (wysoki priorytet)
   - Dodać testy metryk (IoU, endpoints reduction, components) i scentralizowane progi akceptacji.
   - Mały PR: move run_batch_validation.py -> utils + expose gating thresholds jako konfig.
   - Cel: odrzucać naprawy, które nie spełniają minimalnych progów.

2) Integracja lokalnego patch-repair (wysoki priorytet)
   - PR: ujednolicić local_patch_repair.py -> worker w pipeline, parametryzacja (--max_dist, --min_line_ratio, --limit).
   - Dodać testy jednostkowe: sanity check działania na 3 przykładowych przypadkach.

3) Prototyp grafowy (średni priorytet)
   - Zaimplementować skeleton->graph, prosty algorytm dodawania krawędzi (heurystyczny) + walidacja binarna.
   - PR: prototyp + notebook z porównaniem wyników (IoU, endpoints) vs lokalny patch.

4) Maskowanie/ochrona tekstu i etykiet (średni priorytet)
   - Wprowadzić wykrywanie tekstu (OCR/heurystyka) i maskowanie przed naprawami.

5) Automatyczny eksperymentator i CI (niski/średni)
   - Dodać nightly job na małą listę problemowych przypadków z automatycznymi raportami (overlays, metrics)
   - Testy regresji podczas PR: sprawdzanie, że naprawy nie obniżają kluczowych metryk poniżej progu.

6) Dashboard i manual review UX (niski priorytet)
   - Udoskonalić preview.html / gallery dla szybkiego manusualnego sprawdzania propozycji napraw.

Każdy z powyższych elementów powinien być przygotowany jako osobny PR (mały, testowalny, z przetestowaną walidacją). Priorytety możesz zmienić — mogę przygotować szkice PR-ów i przyporządkować testy/regresje.
