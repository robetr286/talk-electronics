# MVP Backlog — projekt Talk_electronic

Zapisany backlog zadań do doprowadzenia projektu do etapu MVP. Zawiera priorytety, krótkie opisy i estymaty czasowe.

Data: 24 listopada 2025

## Wyjaśnienie priorytetów
- High: krytyczne do działania MVP
- Medium: ważne dla stabilności i jakości, ale nie blokuje minimalnego workflow
- Low: usprawnienia i opcjonalne funkcje

---

## High — core MVP (priorytet 1)
1) Zamknąć podstawowy pipeline funkcjonalny (Core MVP)
   - Opis: upload PDF/PNG → ekstrakcja obrazu → detekcja symboli → generowanie netlisty → retusz → zapis i historia.
   - Estymata: 1–2 tygodnie (całość rozbita na mniejsze zadania w backlogu)

2) Zdefiniować core E2E scenariusze i kryteria akceptacji (E2E Acceptance Criteria)
   - Opis: spisać 4–6 krytycznych scenariuszy E2E dla smoke i full; ustalić co uznajemy za "pass". Wynik: plik `docs/E2E_ACCEPTANCE.md`.
   - Estymata: 2 dni

3) Dokończyć backend upload i parsowanie PDF/PNG
   - Estymata: 3 dni

4) Dopracować przetwarzanie obrazu (OpenCV / PyMuPDF)
   - Estymata: 3 dni

5) Integracja detekcji symboli i eksport netlisty
   - Estymata: 4 dni

6) Retusz i zapis wyników + historia
   - Estymata: 2 dni

---

### P1 — Krytyczne poprawki detekcji i przepływów (wynik zgłoszonych bugów i obserwacji)
Opis: Na podstawie Twoich testów w aplikacji zidentyfikowaliśmy szereg problemów, które blokują praktyczne użycie MVP. Poniżej szczegółowe zadania do wykonania jutro — każde zadanie zawiera krótkie kryteria akceptacji i estymatę.

P1.1 — Poprawa rozpoznawania linii (przewodów / węzłów)
- Problem: model nie radzi sobie z rozpoznawaniem linii/przewodów — rozpoznaje np. opisy tekstowe jako końcówki, a węzły są słabo wykrywane.
- Działania:
    - zebrać przykłady błędnych klasyfikacji i dodać anotacje (przykłady z PDF i PNG),
    - dopracować postprocessing (morfologia, progi, łączenie segmentów),
    - dodać reguły odfiltrowania tekstów/etykiet jako końcówek,
    - dodać unit/integration tests i E2E test case dla przypadków węzłów.
- Kryteria akceptacji: recall przewodów wzrasta do X (cel do ustalenia; proponowane minimum 70% na zestawie walidacyjnym), false positives dla tekstów < 10%.
- Estymata: 4 dni

P1.2 — Poprawa rozpoznawania symboli (rezystory, kondensatory, diody)
- Problem: z 20 podstawowych symboli dobrze rozpoznaje zwykle 0–1 element; generalnie bardzo niski wskaźnik precyzji/recall.
- Działania:
    - skonsolidować zbiór treningowy i walidacyjny, dodać brakujące przykłady (różne formaty: PDF, PNG grayscale, PNG binary),
    - dodać augmentacje specyficzne (skala, blur, kontrast, binarization variations),
    - retrain model / finetune, walidacja na zbiorze realnych przykładów,
    - przygotować benchmark (raport wyników na 20-klasowym zbiorze testowym).
- Kryteria akceptacji: F1 per class dla podstawowych 20 symboli >= 0.6 (proponowane); per-class improvements i raport porównawczy przed/po.
- Estymata: 5 dni

P1.3 — Porównać skuteczność wejść (PDF / PNG grayscale / PNG binary)
- Problem: nie wiemy, który wejściowy format daje lepsze wyniki detekcji w rzeczywistej aplikacji.
- Działania:
    - przygotować eksperyment porównawczy (te same obrazy w 3 formatach), mierzyć detekcję symboli i linii,
    - zebrać metryki (precision/recall/F1) i raport, na tej podstawie zaproponować rekomendowany flow detekcji (aplikacja powinna sugerować najskuteczniejszy format i/lub wykonywać automatyczną konwersję).
- Kryteria akceptacji: jasny raport z rekomendacją (np. preferuj binary dla linii, grayscale dla symboli) + test E2E, który potwierdza rekomendację.
- Estymata: 2 dni

P1.4 — Naprawić przekazywanie obrazu między zakładkami (detekcja → segmentacja linii)
- Problem: po wykryciu symboli w zakładce Detekcja nie jest ten sam obraz dostępny w Segmentacji linii — brak "przekazania" bieżącego dokumentu/fragmentu.
- Działania:
    - wyśledzić stan/flow (frontend): ensure current image/fragment = shared buffer między zakładkami,
    - dodać integracyjny E2E test: wykryj na stronie PDF → przejdź do Segmentacji linii → sprawdź czy widoczny/operacyjny jest ten sam obraz,
    - dodać transfer/metadane tak aby obraz/transformacje przenoszone były jednoznacznie.
- Kryteria akceptacji: E2E test przechodzi — Segmentacja linii operuje na tym samym obrazie, co Detekcja.
- Estymata: 1–2 dni

P1.5 — Naprawa błędu HTTP 500 oraz błędów segmentacji
- Problem: po kliknięciu 'wykryj na bieżącym fragmencie' pojawia się 500; przy segmentacji z automatycznego retuszu pojawia się 'błąd segmentacji - sprawdź konsolę'.
- Działania:
    - sprawdzić backend logs i stack trace dla HTTP 500; poprawić błąd i dodać obsługę błędów (komunikaty użytkownika),
    - zweryfikować przyczyny błędu segmentacji na obrazie z automatycznego retuszu (format/rozmiar/depth), dodać walidację wejścia i lepszy user feedback,
    - dodać testy odpornościowe (niepoprawne formaty, niekompletne payloady).
- Kryteria akceptacji: brak 500 dla normalnych przypadków; przy błędzie widoczne sensowne komunikaty; E2E z reprodukcją problemu przechodzi.
- Estymata: 2 dni

P1.6 — Zmniejszyć false positives (teksty jako końcówki) i poprawić rozróżnianie węzłów
- Problem: model fałszywie klasyfikuje tekst/etykiety jako końcówki przewodów oraz słabo rozpoznaje węzły istotne/nieistotne.
- Działania:
    - dodać filtrację tekstu (OCR step) lub rule-based postprocessing by usuwać krótkie etykiety/napisy z detekcji końcówek,
    - dodać anotacje węzłów i rozróżnienie, retrain i walidację,
    - zaktualizować metryki (per-class) i dodać testy regresji.
- Kryteria akceptacji: false positives z tekstu < 10%; węzły istotne wykrywane z recall >= 0.7.
- Estymata: 3 dni

---

Te zadania zapisuję jako priorytetowe do wykonania jutro. Po zatwierdzeniu zaczynam od P1.1 i P1.4 (szybkie debugi UI + analiza danych dla linii), a następnie idziemy dalej według kolejności.

---

## Medium — stabilność i testy
7) Utworzyć i znormalizować smoke E2E (3–5 testów szybkie/ważne)
   - Estymata: 2 dni

8) Pokrycie testami jednostkowymi i integracyjnymi (krytyczne moduły)
   - Estymata: 5 dni

9) Stabilizacja pełnych E2E (flaky fixes)
   - Estymata: 5 dni

10) CI: smoke na PR + full nightly + artefakty (reports/trace)
    - Estymata: 3 dni

---

## Low / Important — dalsze prace
11) Audit datasetu i plan poprawy modeli
    - Estymata: 3 dni

12) Retrain i integracja modelu
    - Estymata: 5 dni

13) Dockerize + staging deployment
    - Estymata: 3 dni

14) Monitoring, logi i telemetria (podstawy)
    - Estymata: 3 dni

15) Dokumentacja: quickstart, architektura, runbook QA
    - Estymata: 3 dni

16) Bezpieczeństwo i polityka prywatności
    - Estymata: 3 dni

17) Developer UX: Husky + onboarding (opcjonalne)
    - Estymata: 1–2 dni

18) Plan wydania MVP i feedback loop
    - Estymata: 2 dni

---

## Proponowany pierwszy sprint (2 tygodnie)
- Cele priorytetowe:
  - Dokończyć core pipeline (zadania 1,3,4),
  - Ustalić E2E acceptance criteria (zadanie 2),
  - Stworzyć minimalny zestaw smoke E2E (zadanie 7) — 3 testy.

## Kogo obejmuje:
- Przeznaczony dla pojedynczego developera (typowe tempo i estymaty przy pracy bez dużego zespołu). Jeśli dołączy więcej osób, rozbić zadania równolegle.

---

Jeśli chcesz, mogę teraz:
- A) utworzyć plik `docs/E2E_ACCEPTANCE.md` z dokładnymi scenariuszami (pierwsze zadanie),
- B) od razu wdrożyć Husky (krok optionalny) i dodać pre-push/pre-commit (przydatne, jeżeli planujesz rozszerzać zespół),
- C) przełączyć się na implementację punktu 1 (backend upload/parsowanie) — wybierz.
