# Plan naprawy szkieletów (GRAPH_REPAIR_SKELETON_RESOLUTION_PLAN)

Cel: opracować bezpieczny, powtarzalny proces naprawy szkieletów obwodów elektronicznych, który nie deformuje oryginalnej topologii ani nie wprowadza artefaktów (nadmiernych zlejeń lub szumów).

Podsumowanie dotychczasowych wniosków
- Globalne operacje (morphological close, OR między wariantami, agresywne thinning) doprowadziły do znacznego oddalenia wyników od oryginału w niektórych przypadkach: spodziewane połączenia zostały nadmiernie scalone lub powstał szum i artefakty.
- Walidacja porównawcza na zestawie przypadków pokazała, że wiele wcześniejszych, globalnych napraw nie poprawia topologii (endpoints) i często nie spełnia akceptowalnych kryteriów.
- Prosty, lokalny algorytm łączący końcówki (connect endpoints) z wykorzystaniem sygnalu źródłowego (binary/prepared) pokazał, że można uzyskać wysokie IoU z oryginałem i jednocześnie zmniejszyć liczbę endpoints bez nadmiernego scalania — co sugeruje, że naprawy lokalne są obiecujące.

Założenia projektowe
- Zachować topologię: nigdy nie dopuścić do agresywnego zlania struktur z opisami elementów czy z innymi liniami; preferować operacje lokalne i warunkowe.
- Pełna testowalność: każda zmiana musi przechodzić walidację ilościową (IoU z oryginałem, liczba endpoints, liczba komponentów) + manualny przegląd.
- Transparentność: generować per-obr. raporty (overlayy, summary metrics) i testy regresji.

Główne kroki proponowanego rozwiązania
1) Walidacja & Safety gates (automaty):
   - Definiować progi akceptowalności (IoU, spadek endpoints %, komponenty) i odrzucać naprawy, które je nie spełniają.
   - Uruchamiać heurystyki w trybie „proposal” i tylko przy pozytywnej walidacji zapisywać do finalnego artefaktu.

2) Podejście lokalne zamiast globalnego:
   - Lokalnie identyfikować obszary z problemami (wysoka gęstość endpoints / przerwy) i naprawiać tylko patch (np. 64×64 lub 128×128) w kontekście surowego obrazu (binary/prepared), nie globalnie.
   - Łączenie końcówek: łączyć jedynie pary, które spełniają bezpieczne warunki: krótka odległość, wysoki wskaźnik poparcia w binarnie (więcej pikseli w linii), brak kolizji z etykietami (maskowanie tekstu) i brak dużej zmiany globalnej.

3) Strategia grafowa (docelowa) — dlaczego i jak:
   - Konwersja szkieletu do grafu (węzły = junctions/endpoints, krawędzie = segmenty) pozwala na operacje w domenie grafu: wykrywanie brakujących połączeń, analizę długości/kierunku, ocenę kosztu połączenia.
   - Naprawy mogą być: (a) dodanie krótkiego krawędzi łączącej dwa endpoints (jeśli jest wspierane przez binarny obraz) albo (b) rekonstruowanie lokalnych fragmentów najpierw w grafie, potem rasteryzacja.
   - Zaletą grafu jest możliwość zachowania topologii i stosowania reguł (np. nie łączyć węzłów gdy w pobliżu są etykiety lub gdy dodanie krawędzi zmniejsza liczbę komponentów poniżej progu).

4) Maskowanie elementów i tekstu:
   - Wykrywać i maskować obszary z tekstem / etykietami (OCR / heurystyka), aby naprawy nie łączyły linii z napisami.

5) Metryki i testy regresji:
   - Dla każdego przypadku uruchamiać: IoU vs baseline, pixels difference, components, endpoints_count.
   - Dodać automatyczny test regresji: wymagane minimalne warunki (np. iou >= 0.7 OR endpoints_reduction >= X and components_drop <= Y).

6) CI / eksperymentacja:
   - Dodać etap eksperymentalny: nightly jobs na małym zbiorze problemów i porównanie wyników.

Małe proof-of-concept (kroki implementacyjne)
1. Uruchomić rozszerzoną walidację (zrobione) i zebrać przypadki, gdzie globalne metody psują topologię.
2. Implementować i testować lokalny patch‑repair w pipeline: create proposal → validate→ accept only if safety gates pass.
3. Przeprowadzić prototyp grafowy na 10 najbardziej problemowych przypadkach, porównać do lokalnych napraw.
4. Gdy grafowy prototyp będzie lepszy, wdrożyć do pipeline jako dodatkową ścieżkę (z testami regresji).

Wymagane zmiany w repo
- Nowe narzędzia: lokalny repair worker, grafowy prototyp, testy jednostkowe + metryki.
- Dodatkowe artefakty: per-case reports (overlays, metrics) + dashboard/HTML do manualnej weryfikacji.

Kolejne kroki (sugerowane teraz)
1. Skalować lokalny patch‑repair do większej próby (np. 100 przypadków) i wyciągnąć zbiorczą statystykę (robię to jeśli chcesz).
2. Zacząć prototyp grafowy (konwersja skeleton->graph) i eksperymentować z dodawaniem brakujących krawędzi pod kontrolą binarnego obrazu.

—
Ten plan jest szkicem — jeśli się zgadzasz, przygotuję konkretny backlog z priorytetami i małymi PR-ami: najpierw stabilna walidacja + lokalny repair w pipeline, potem grafowy prototyp + testy.
## Analiza problemu: przerwy w skeletonie dla linii ukośnych i niskiej rozdzielczości elementów

Data: 2025-12-06

Cel: zdiagnozować i naprawić sytuacje, w których linie ukośne (diagonalne) powstają jako seria "kropelek"/fragmentów i nie łączą się w ciągły skeleton, w odróżnieniu od linii poziomych/pionowych, które zachowują ciągłość nawet przy niskiej liczbie pikseli. Zakładamy, że sedno problemu leży w kombinacji: przygotowania obrazu (scale/prepared), parametrów skeletonizacji i warstwy wykrywania "dots" (dotted candidates) — zwłaszcza w przy małej liczbie pikseli reprezentujących pojedyncze elementy schematu.

Hipotezy (co może powodować problem):
- 1) Brak multi-scale processingu: segmenty ukośne rysowane są z mniejszej ilości pikseli, a algorytm nie ma informacji by je ujednolicić.
- 2) Przygotowanie obrazu (`prepared`) używa morfologii i progów, które lepiej służą liniom osiowym (H/V) niż ukośnym — kernel i iteracje nie są orientacyjne.
- 3) Skeletonizator (Zhang-Suen and post-processing) może usuwać kluczowe łączniki dla ukośnych 1px kropek (np. usuwanie spurious pixels, diagonal spur removal) — heurystyki zaprojektowane dla H/V nie działają dobrze dla sablonu diagonalnego.
- 4) Detect_dotted_candidates dobiera dots na podstawie gradientu i progu saturacji/value; jeśli jednopikselowy diag składa się z kropek zbyt słabym kontrastem, nie będą zakwalifikowane jako 'general_mask' -> _graph_repair_skeleton nie zadziała.

Metryki / kryteria powodzenia:
- Connectivity ratio: udział endpointów po naprawie / przed naprawą — oczekujemy <= 5% niesparowanych endpointów dla poprawnie scalonych przypadków.
- Pixel-delta: liczba dodanych pikseli w skeletonie po naprawie — małe dodatki oczekiwane; duże dodatki sygnalizują fałszywe łączenia.
- False-join rate: ręcznie zweryfikowany subset transistor-like / dense mesh — oczekujemy spadku fałszywych scalen w porównaniu do agresywnych ustawień.
- Sensitivity to scale: porównanie wyników przy 1x, 1.5x, 2x skali — czy zwiększenie rozdzielczości przygotowania (prepared) powoduje wyraźne polepszenie połączeń ukośnych?

Plan eksperymentów (priorytet / co dokładnie):

Faza A — diagnoza (sprint 1, szybkie eksperymenty) — 1–2 dni
1. Opracować harness diagnostyczny (syntetyczny + real):
   - Synthetic generator: rysuje linie w kilku orientacjach (0°, 15°, 30°, 45°, 60°, 75°, 90°) z kroplami/dot-patterns i różnymi rozmiarami elementów (small/medium/large). Opcja: z jitterem, z różnym kontrastem.
   - Real set: wyodrębnij z `data/junction_inputs` i `debug` reprezentatywne przypadki ukośnych przerw (z wcześniejszych eksperymentów).
2. Mierzyć baseline: dla każdego obrazu/syntetyka uruchomić `SkeletonEngine` i pipeline `detect_lines` z aktualnymi (konserwatywnymi) ustawieniami i zapisać metryki: liczba endpointów, liczba komponentów, pixel counts, skeleton continuity.
3. Uruchomić te same obrazy w skalowaniu (prepared scale) np. 1.0, 1.5, 2.0 i porównać czy wyższa rozdzielczość rozwiązuje problem.
4. Sprawdzić działanie `_detect_dotted_candidates` przy niskim rozmiarze elementów — czy wykrywa kropki; jeśli nie, przetestować wartości progów (saturation/value) i ich wpływ.

Faza B — eksperymenty (sprint 2, 2–3 dni)
1. Multi-scale approach: w przygotowaniu obrazu (`_prepare_image`) dodać opcję multi-scale (upscale ROI centrowane na detekcjach lub globalne 1.5x/2.0x) i wykonać skeletonization w wyższej rozdzielczości, a potem zredukować do docelowego skeletonu (aggregate results z wielu skal).
2. Orientation-aware preprocessing: testować orientacyjne morfologie (rotated structural elements) / anisotropic closing działający lepiej w kątach 45° oraz kierunkowa detekcja i łączenie.
3. Zmiana parametrów skeletonizacji / usuwania spurów — próby utrzymania ukośnych 1px łączników (np. delikatniejsze usuwanie diagonal spurs lub adaptacyjne threshold dla kątów ≠ 0/90).
4. Poprawa detect_dotted_candidates: zwiększyć czułość na niską liczbę pikseli (mniejsze kernely, drobniejsze otoczenie) lub dodać heurystykę wykrywania zorientowanych dot-strings (szereg kropek po liniach ukośnych).

Faza C — walidacja (sprint 3, 1–2 dni)
1. Uruchomić porównania na większym zbiorze (small+medium lub sample_benchmark) i zebrać metryki: connectivity, timeouts, pixel_delta, false joins.
2. Przygotować testy jednostkowe + e2e dla nowych heurystyk i regresji.
3. Przygotować inspekcyjną paczkę i krótką prezentację rezultatów + rekomendacja (konserwatywne vs agresywne vs multi-scale hybrid).

Ryzyka / uwagi:
- Multi-scale poprawia wykrywalność ale podnosi czas/zużycie pamięci i może wprowadzać więcej fałszywych łączeń — trzeba znaleźć kompromis.
- Zmiany w bibliotekach morfologicznych i skeletonizacji mogą wpływać na inne elementy pipeline — dodać testy pod kątem regresji (textual spurs, thin-lines, junction counts).

Szybki, praktyczny plan pracy (priorytety):
1. Napisać harness diagnostyczny (synthetic + real collection) [wysokie priorytet]
2. Uruchomić testy skali 1x/1.5x/2x żeby upewnić się, że problem koreluje z rozdzielczością [diagnostyka]
3. Jeśli poprawa znacząca przy 2x, zaimplementować targetowane upscaling (na ROI lub wszystkie inputy) i przetestować efekty uboczne
4. Równolegle eksperymentować z orientation-aware morphology i filterami
5. Dodać reguły w pipeline: jeżeli segment jest krótki i diagonalny, weź multi-scale ROI else run normal pipeline

Następne kroki (co mogę zrobić teraz):
- A: Utworzyć harness diagnostyczny i zestaw testów (synthetic) + uruchomić baseline (zebrać metryki)
- B: Po A uruchomić upscaling test (1.5/2.0) i porównać wyniki

Jeżeli akceptujesz plan, mogę od razu przejść do A (napisać harness i dodać testy diagnostyczne). Daj znać czy zaczynam teraz.

*** Koniec planu — przygotowane przez Copilot (tylko w repo). ***
