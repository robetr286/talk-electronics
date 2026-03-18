# Backlog (high-level)

Ten plik służy jako przegląd zadań backlogu — szczegółowe zadania i priorytety zapisujemy w GitHub Issues (źródło prawdy), a tu trzymamy przydatny zwięzły widok.

Jak używać:
- Issues = źródło prawdy. Twórz issue dla nowych zadań/refactorów i oznacz priorytet (`P0`, `P1`, `P2`, `P3`).
- Ten plik zawiera tylko wybrane pozycje wysokiego priorytetu i roadmapę „tech‑debt” do wykonania.

## Priorytety
- P0: krytyczne (bezpieczeństwo, blokujące błędy, CI fail)
- P1: ważne (modularizacja, brakujące integracje, kluczowe refactory)
- P2: umiarkowane (porządki, archiwizacja, porządki w deps)
- P3: niskie (kosmetyka, drobne optymalizacje)

---

## Obecne propozycje zadań
- [P1] Modularize OCR evaluators (`scripts/evaluate_ocr_candidates.py`) — wydzielić runnery modelu do `talk_electronic/ocr/` i dodać testy integracyjne.
- [P1] Cache model readers + GPU device flag + per-image timeout — poprawa stabilności i szybkości ewaluacji.
- [P2] Przenieść stare eksperymenty do `scripts/archive/` i dodać README w katalogu archive.
- [P2] Odróżnić `requirements.txt` (prod) vs `requirements-dev.txt` (dev/test) i skrócić instalacje CI.
- [P3] Drobne UI refactory: rozbić monolityczny `static/js/*` na mniejsze moduły i dodać README.
- [P1] Add CI check for PRs labeled `refactor` (ensure issue link, tests run).

---

## Propozycja rytuałów
- Tech‑Refactor Hour: 2h tygodniowo (np. Wtorek 10:00–12:00) — drobne PRy, cleanup, dokumentacja.
- Raz na sprint: 1–2 większe zadania refactor (przypisać do sprintu, estimate 1–4 dni).

---

## Links / References
- Issues: https://github.com/<org>/<repo>/issues
- DEV_PROGRESS.md — kronika prac i raporty


> Jeśli chcesz, mogę utworzyć przykładowe issues z powyższymi zadaniami i dodać etykietę `refactor` oraz recurring GitHub Issue przypominający o Tech‑Refactor Hour.
