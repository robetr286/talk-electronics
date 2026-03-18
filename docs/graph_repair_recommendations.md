# Graph‑repair — rekomendacje i podsumowanie (2025-12-04)

Krótki raport z eksperymentów graph‑repair przeprowadzonych 2025‑12‑04 oraz rekomendacje dalszych kroków.

## Co zrobiliśmy
- Wdrożono graph‑based skeleton repair i testowalny pipeline (skrypty eksperymentalne + runner progress/aggregation).
- Uruchomiono pełny sweep (small + medium) eksperymentalnych kombinacji parametrów — wyniki w `debug/graph_repair_sweep_progress/`.
- Na podstawie analizy wyników wprowadzono konserwatywne domyślne parametry, by zminimalizować false‑positives:
  - `dotted_line_graph_repair_angle_threshold = 12.0`
  - `dotted_line_graph_repair_overlap_fraction = 0.5`
  - `dotted_line_graph_repair_max_joins_per_image = 10`
  - Dodano `dotted_line_graph_repair_max_nodes = 500` (early bailout dla zbyt złożonych grafów)
- Dodano testy jednostkowe które zabezpieczają nowe domyślne wartości i zachowanie bailout:
  - `tests/test_graph_repair_defaults.py`
  - `tests/test_graph_repair_bailout.py`
  - `tests/test_graph_repair_bailout_many.py`
- Przygotowano pakiet inspekcyjny i mini‑sweep followup (artefakty w `debug/graph_repair_inspection/` i `debug/graph_repair_followup/`).

## Najważniejsze obserwacje
- Sweep wykazał, że agresywne ustawienia (np. angle=30, overlap=0.6, max_joins=50) często generują duże pixel_delta (często >500) — ryzyko false‑positives.
- Wiele timeoutów zdarzało się na obrazach z dużym rozmiarem lub bardzo skomplikowanym skeletonem (stąd early bailout i max_nodes).
- Mini‑sweep z nowymi domyślnymi pokazał, że większość przypadków nie wymagała napraw (pixel_delta = 0), co sugeruje, że domyślne ustawienia są konserwatywne i bezpieczne.

## Rekomendowane następne kroki (zrobimy jutro)
1. Uruchomić porównawczy pełny sweep (old aggressive defaults vs nowe konserwatywne) i porównać statystyki (timeouts, avg elapsed, pixel_delta).
2. Dodać kolejne testy regresyjne (syntetyczne i rzeczywiste przypadki z tranzytorami i gęstymi siatkami).
3. Przygotować paczkę wizualną z reprezentatywnymi przypadkami (zip) i przeprowadzić ręczną kontrolę (team review).

## Lokalizacje artefaktów
- Pełny sweep (agresywny/eksperymentalny): `debug/graph_repair_sweep_progress/`
- Pakiet inspekcyjny (index): `debug/graph_repair_inspection/index.html`
- Mini followup sweep (nowe domyślne): `debug/graph_repair_followup/`

Jeżeli chcesz, jutro uruchomię porównawczy przebieg i przygotuję raport CSV/JSON z porównaniem przed/po oraz przykładową paczką wizualną.
