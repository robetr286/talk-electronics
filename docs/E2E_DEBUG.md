# E2E Debug Guide — Playwright & CI

Krótki, praktyczny przewodnik krok‑po‑kroku jak diagnozować niepowodzenia testów E2E (Playwright) i co robić z zebranymi artefaktami.

## 🔎 Kiedy użyć
- Test E2E w CI zakończył się niepowodzeniem (failure) lub obserwujesz flaki lokalnie.
- Chcesz szybko zebrać kontekst (trace, screenshoty, logi) i odtworzyć problem lokalnie.

## 🧰 Zbieranie artefaktów (CI)
1. Pobierz artefakty z runu GitHub Actions (Artifacts):
   - Z interfejsu GitHub: otwórz run → zakładka **Artifacts** → ściągnij `playwright-report` / `tests/e2e/artifacts` / `flask.log`.
   - Lub użyj `gh` CLI: `gh run download <run-id> --name e2e-artifacts`.
2. Sprawdź krótkie logi od razu (ostatnie 200 linii): `tail -n 200 flask.log` — często dają szybki hint.

## 🧭 Analiza Playwright trace i screenshotów
- Otwórz trace interaktywnie:
  - `npx playwright show-trace path/to/trace.zip`
  - Przejrzyj kroki (snapshots, network, console errors, stack traces).
- Screenshots: znajdziesz je w `tests/e2e/artifacts/<test>/screenshots/` — porównaj z oczekiwanym UI.
- Gdy widzisz overlay/alert blokujący przepływ, zanotuj selector i ewentualną sekwencję kliknięć, które przywracają stan.

## 🔁 Reprodukcja lokalna (szybkie kroki)
1. Włącz środowisko:
   - `conda activate talk_flask` (lub twoje dev env)
2. Uruchom dev server:
   - `python -m flask --app app run --debug` lub użyj VS Code taska **Run Flask dev server**
   - Możesz też czekać na gotowość: `npx wait-on http://127.0.0.1:5000`
3. Uruchom pojedynczy test z trace-on-first-retry:
   - `npx playwright test tests/e2e/<spec>.spec.js -g "<grep-or-test-name>" --retries=1 --trace on-first-retry`
4. Odtwórz problem, otwórz trace i debuguj.

## 🧾 Co załączyć do Issue (jeśli problem powtarzalny)
- Krótkie podsumowanie: który test/flow, kiedy (run id), krótka reprodukcja krok‑po‑kroku.
- Załącz artefakty: `trace.zip`, screenshoty, `flask.log` (ostatnie ~500 linii) i link do runu GitHub Actions.
- Wskazówki: czy problem występuje lokalnie (tak/nie), które testy trzeba uruchomić aby odtworzyć.

## 🛠 Przydatne komendy
- `npx playwright show-trace path/to/trace.zip`
- `npx playwright test tests/e2e/<spec>.spec.js -g "<grep>" --retries=1 --trace on-first-retry`
- `tail -n 200 flask.log`
- `gh run download <run-id> --name e2e-artifacts`
- `npx wait-on http://127.0.0.1:5000` (czekanie na lokalny serwer)

## 🧭 Polityka powiadomień (krótko)
- Dobry kompromis: powiadamiaj tylko przy pierwszym nieudanym runie + po N=3 kolejnych porażkach lub użyj reguły "first failure after success" — zmniejsza szum alertów.
- Powiadomienie powinno zawierać: link do runu, krótki fragment logu (ostatnie 200 linii) i instrukcję szybkiego debugu (link do tego pliku).

## ✅ Rekomendacje operacyjne
- Ustaw `trace: retain-on-failure` i `screenshot: only-on-failure` w `playwright.config.js` (mamy to już skonfigurowane).
- W workflow CI: uploaduj artefakty (`playwright-report`, `tests/e2e/artifacts`, `flask.log`) w kroku `if: always()` — to już robimy w E2E jobie.
- Rozważ implementację prostego kroku `if: failure()` wysyłającego notyfikację Slack (mini‑payload: run link + last lines of flask.log).

---

Jeśli chcesz, mogę teraz:
- dodać przykładowy krok Slack do `.github/workflows/playwright-e2e.yml`, albo
- stworzyć szablon Issue (`.github/ISSUE_TEMPLATE/e2e-flaky.md`) z listą pól do wypełnienia.

Wybierz jedną opcję, a ja to dodam. ✨
