# QA Log — Pytania i Odpowiedzi

Ten plik będzie zapisem pytań i odpowiedzi, które pojawiają się podczas pracy nad projektem — przydatne do dokumentacji, przeglądów i uczenia modeli.

## 2025-11-23 — Dodanie Playwright do CI — pytanie i odpowiedź

Q: *"Zanim zrobisz ten punkt, to wytłumacz na czym to polega - 'Dodać Playwright testy do CI (GitHub Actions) — wtedy będą wykonywane automatycznie.'"*

A: Playwright to narzędzie, które pozwala automatycznie sterować przeglądarką (np. Chrome), żeby symulować zachowanie prawdziwego użytkownika: otwieranie stron, klikanie przycisków, wgrywanie plików i sprawdzanie czy UI reaguje poprawnie.

- Co robi „dodać Playwright do CI (GitHub Actions)”? (w prostych słowach):
	- CI (Continuous Integration) to proces który automatycznie uruchamia zadania po każdym pushu do repozytorium.
	- Dodanie Playwright do CI oznacza: za każdym razem gdy ktoś zrobi push/merge, GitHub sam uruchomi Playwright i sprawdzi czy interfejs działa tak jak powinien.
	- Dzięki temu: błędy wykrywane są wcześniej, zanim trafią na produkcję; zespół dostaje szybkie informacje czy coś się zepsuło.

- Dlaczego warto to zrobić:
	- Automatyczne testy UI wyłapują problemy, które nie pojawiają się w testach jednostkowych.
	- Oszczędność czasu: każdy deweloper nie musi ręcznie testować UI.
	- Większa pewność, że nowe zmiany nie zepsują podstawowych scenariuszy.

Jeżeli chcesz, mogę od razu dodać realny Playwright test, instrukcję instalacji i zintegrować to z GitHub Actions tak, żeby testy uruchamiały się automatycznie przy każdym pushu.

### 2025-11-23 — Prośba: Najpierw instrukcje

Q: "Najpierw instukcje"

## 2025-11-23 — Co zrobiliśmy (wersja dla nietechnicznych)

Zrobiliśmy trzy rzeczy, żeby lepiej chronić aplikację i szybciej wykrywać błędy:

- Dodaliśmy automatyczne testy, które uruchamiają przeglądarkę i sprawdzają podstawowy przepływ: wgrywanie rysunku, przetworzenie (binaryzacja), wysłanie wyniku do edycji (retouch) i otwarcie go w zakładce do ręcznej korekty.
- Zapewniliśmy, że te testy będą uruchamiane automatycznie przez system CI (GitHub Actions) przy każdym pushu lub pull‑requeście do głównej gałęzi — dzięki temu, jeśli coś się zepsuje, zespół od razu otrzyma informację.
- Dopisaliśmy dokumentację i „poradnik” z krokami jak uruchomić testy lokalnie i jak działają w CI.

Dlaczego to ma znaczenie dla osób nietechnicznych:

- Dzięki temu szybciej wykrywamy, gdy jakiś ważny element interfejsu przestaje działać — na przykład gdy przycisk do „Załaduj wynik z binaryzacji” przestaje ładować obraz.
- Testy uruchamiane automatycznie oznaczają mniejszą liczbę niespodziewanych błędów na środowisku produkcyjnym i krótszy czas potrzebny deweloperom na naprawę.
- Dokumentacja pomaga każdemu w zespole (nie tylko programistom) zrozumieć, co zostało zrobione i jak sprawdzić, że wszystko działa.

Jeżeli chcesz — mogę dodać jeszcze krótki ekranowy filmik pokazujący cały przepływ, żeby osoby nietechniczne mogły zobaczyć działanie na żywo.

A: Dodałem plik `docs/PLAYWRIGHT_CI_INSTRUCTIONS.md` z praktycznymi, krok‑po‑kroku instrukcjami jak zainstalować Playwright lokalnie, jak uruchomić testy i jak zintegrować Playwright z GitHub Actions (CI). Plik zawiera przykładowy YAML workflow do uruchomienia Playwright w CI i wskazówki dla deweloperów (Windows / PowerShell).

### 2025-12-04 — Co zrobimy teraz (tłumaczenie/wyjaśnienie dla nietechnicznych) — Graph-based repair

Obraz `skeleton_repaired.png` pokazuje, że linia pozioma została połączona i wygląda ciągle, ale na dwóch liniach skośnych wciąż widać przerwy — czyli tam algorytm jeszcze nie dopasował połączeń.

W prostych słowach: nasz system może teraz łączyć przerwy w liniach „inteligentnie” (na poziomie struktury linii), ale trzeba znaleźć właściwe ustawienia żeby łączył jedynie te przerwy, które rzeczywiście są częścią tej samej linii, a nie łączył przypadkowych elementów (np. tekstu).

Kolejne kroki, które proponujemy i co one znaczą (bez technicznego żargonu):

- Uruchomić serię testów (sweep) na kilku reprezentatywnych obrazach, zmieniając parametry, które decydują jak łatwo system zgadza się łączyć przerwy (np. jak daleko mogą być punkty, jak bardzo muszą być „w jednej linii” i ile przerwań można połączyć jednocześnie). Chcemy zobaczyć: ile w każdym ustawieniu zostanie dodanych połączeń, ile pikseli „doklei” się do szkieletu i czy pojawiają się złe połączenia.
- Dodać test jednostkowy (automatyczny test): stworzymy małe, kontrolowane obrazy z celowymi przerwami i sprawdzimy, czy naprawa grafowa łączy je gdy powinna — oraz że nie łączy elementów niezwiązanych. To chroni nas przed przypadkowymi regresjami.
- Dalsze dopracowanie (opcjonalne): na podstawie wyników testów wybierzemy bardziej konserwatywne ustawienia albo drobne reguły pozwalające unikać łączenia w obszarach tekstu/znaczników.

Po dodaniu tych kroków będę generować i zapisywać obrazy szkieletu (skeleton) po każdym przetworzeniu, żebyś mógł/a od razu zobaczyć efekt zmian.

— zapisano automatycznie przez system 2025-12-04

### 2025-12-04 — Uruchomiony bezpieczny sweep z paskiem postępu

Dodałem nowy runner `scripts/run_graph_repair_sweep_progress.py` który:

- wykonuje zadania równolegle (domyślnie do 4 workerów),
- ma per-obraz timeout (domyślnie 35s),
- zapisuje wyniki po każdej iteracji do `debug/graph_repair_sweep_progress/sweep_progress_summary.json`,
### 2025-12-04 — iterative follow-up: conservative defaults & early bailout

- Changed the graph-repair defaults in `talk_electronic/services/line_detection.py` to conservative values: angle_threshold=12.0, overlap_fraction=0.5, max_joins_per_image=10 and added `dotted_line_graph_repair_max_nodes=500` (early bailout when skeleton graph is too large).
- Added unit tests ensuring defaults are fixed and introducing bailout behavior tests: `tests/test_graph_repair_defaults.py`, `tests/test_graph_repair_bailout.py`, `tests/test_graph_repair_bailout_many.py`.
- Ran a focussed followup mini-sweep (6 images) under the new defaults. Most images show 0 pixel delta (no aggressive repairs), only one case produced a moderate change (pixel_delta=87). Results and debug artifacts are in `debug/graph_repair_followup/` (see `mini_sweep_summary.json` and `followup_pixel_delta.txt`).

These changes aim to reduce false-positive merges and avoid long-running repair passes; they keep the graph-repair enabled but conservative by default and add an early bailout to avoid timeouts on very complex skeletons.

- pokazuje wyraźny pasek postępu w formie: "done/total (XX%) — elapsed XXs — ETA XmYs".

Przeprowadziłem krótki demo-run ograniczony do 3 obrazów (zmienna środowiskowa SWEEP_LIMIT=3) — wynik: `debug/graph_repair_sweep_progress/sweep_progress_summary.json`.

Pełny, rozszerzony sweep (ma dużo zadań) można uruchomić bez limitu; runner jest przerywalny i wznowi się od miejsca gdzie został przerwany (poprzez zapis JSON). Przy dłuższych przebiegach zalecam wykorzystywać 2–4 workerów i monitorować użycie CPU/RAM.

### 2025-12-04 — Wyniki krótkiego demo (`run_graph_repair_sweep_progress`) i obserwacje

Przeprowadziłem demo-run ograniczony do 3 obrazów (24 zadań). Wyniki agregacji:

- total_tasks: 24
- timeouts: 19 (większość zadań przekroczyła limit 35s)
- avg_elapsed_s: 34.17s (średni czas zadań, ale sporo zadań trwało nieco dłużej -> timeout)
- pixel_delta_counted: 6 (dla 6 zadań udało się policzyć różnicę pikseli między skeleton i skeleton_repaired)
- avg_pixel_delta: 344.33 (średnia liczba pikseli dodanych przez naprawę tam, gdzie było to zmierzalne)

Wniosek: domyślny timeout 35s jest za krótki — dużo zadań wykonało się blisko tego limitu i zostało przerwanych. Proponuję ustawić dłuższy timeout (np. 90–120s) przy uruchomieniu pełnego sweepu, oraz ewentualnie zmniejszyć liczbę workerów do 1–2 na maszynach z ograniczonym CPU.

### 2025-12-04 — Plan uruchomienia pełnego sweepu (dla nietechnicznych)

Zamierzamy przetestować naprawę grafową (graph-repair) na większym zestawie obrazów, żeby zrozumieć jak parametry wpływają na wynik i ile fałszywych połączeń się pojawia.

Prosty opis procesu (wersja dla osoby nietechnicznej):

- Krok 1: Skrypt bierze jeden obrazek i próbuje naprawić przerwy w liniach tam, gdzie wygląda to jak kropkowane połączenie.
- Krok 2: Po przetworzeniu zapisujemy kilka pomocniczych obrazków — jak wygląda wejście po przygotowaniu, jak wygląda wykryty szkielet (skeleton) oraz jak wygląda ten sam szkielet po naprawie (skeleton_repaired). Dzięki temu możemy szybko porównać "przed" i "po".
- Krok 3: Powtarzamy to dla wielu obrazów i różnych ustawień (np. jak ostre mają być kryteria łączenia). Wszystko zapisujemy w katalogu debug i w pliku JSON, więc możesz oglądać wyniki i porównywać ustawienia.

Dlaczego parametry są ważne:

- timeout (czas pracy na jeden obraz) — jeśli za krótki, skrypt przerwie zadanie zanim skończy; przy naszych obrazach ustawiłem 120 sekund, żeby uniknąć przerwań.
- workers — liczba zadań uruchamianych równolegle. Na twoim Dell OptiPlex 7060 (i5‑8500, 32GB RAM) ustawiamy bezpiecznie 4 workerów — to wykorzysta rdzenie CPU równolegle, przy zachowaniu stabilności.

Co zobaczysz po pełnym przebiegu:

- Plik JSON z raportem (ile czasu zajęło każde zadanie, czy wystąpiły timeouts itd.).
- Dla wybranych zadań: `skeleton.png` i `skeleton_repaired.png` do porównania wizualnego.

— zapisano automatycznie przez system 2025-12-04


## 2025-11-28 — Łączenie stron schematu

Q: *"O co chodzi z funkcją 'Łączenie stron schematu' i gdzie trafiają dane z tego procesu?"*

A: Funkcja „Łączenie stron schematu” pozwala oznaczać konektory krawędziowe na multi-stronicowych schematach. Adnotacje powstają w Label Studio (nowa etykieta `edge_connector`), trafiają do naszego importera i są zapisywane w serwisie Flask jako osobny store (analogiczny do ignore regions). Frontend dostaje dedykowaną zakładkę, która umożliwia rysowanie poligonów konektorów, dopisywanie metadanych (np. nazwa sieci, numer pina) oraz dwustronną synchronizację z API. Te dane są później używane w generatorze netlist do łączenia sygnałów między arkuszami oraz w module diagnostycznego czatu jako kontekst pytań o ciągłość sygnału.

## 2025-11-28 — Plan i kolejność wdrożenia edge connectorów

Q: *"Jaki jest szczegółowy plan wdrożenia funkcji 'Łączenie schematów' (edge connectors)?"*

A: Kolejność prac:

- Model i dokumentacja: odświeżyć `docs/annotation_guidelines.md`, `annotation_schema.json` oraz szablony Label Studio o kategorię `edge_connector`.
- Serwis backendowy: dodać `EdgeConnectorStore` wzorowany na `IgnoreRegionStore`, zapisywany w `uploads/edge_connectors/*`, rejestrowany w `app.py`.
- Blueprint API: utworzyć `talk_electronic/routes/edge_connectors.py` (GET/POST/PATCH/DELETE plus kontrola tokenów) i zabezpieczyć testami API.
- Frontend: przygotować zakładkę „Łączenie schematów” w `templates/viewer.html`, moduł JS obsługujący rysowanie poligonów oraz synchronizację z API i drobne style w `static/css/app.css`.
- Integracje downstream: rozszerzyć `talk_electronic/services/netlist_builder.py` o włączanie konektorów do netlist i przekazać te dane do serwisu czatu diagnostycznego.
- Walidatory i skrypty: zaktualizować importery i testy (`scripts/annotation_auto_loader.py`, `tests/test_annotation_validator.py`) tak, by rozpoznawały obowiązkowe konektory.
- QA: dodać scenariusze Playwright (dodanie konektora) i uruchomić `pytest` na nowych testach jednostkowych.
