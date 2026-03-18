# Playwright + CI — instrukcje krok po kroku (dla nie‑technicznego użytkownika)

To krótkie, praktyczne instrukcje jak uruchomić testy Playwright lokalnie oraz jak zintegrować je z GitHub Actions (CI), aby były uruchamiane automatycznie przy każdym pushu.

## 1. Co to jest Playwright i dlaczego go używamy?
- Playwright to narzędzie które automatycznie steruje przeglądarką (Chrome, Firefox, WebKit). Pozwala na symulowanie pracy użytkownika: otwieranie strony, klikanie przycisków, wgrywanie plików itp.
- Daje to pewność, że cały interaktywny przepływ (UI + backend) działa jak trzeba.

---

## 2. Uruchomienie Playwright lokalnie (Windows / PowerShell)
1. Zainstaluj Node.js (wersja LTS) z https://nodejs.org/. Po instalacji otwórz PowerShell.
2. W katalogu projektu zainicjuj npm (jeśli jeszcze nie ma package.json):

```powershell
npm init -y
```

3. Zainstaluj Playwright i przeglądarki:

```powershell
npm i -D @playwright/test
npx playwright install
```

4. Uruchom serwer aplikacji (w osobnym terminalu) np. wirtualne środowisko Pythona:

```powershell
conda activate talk_flask
flask --app app run --debug
# lub: python -m app
```

5. Uruchom testy Playwright:

```powershell
npx playwright test
```

- Testy uruchomią się w trybie headless (bez widocznej przeglądarki).
- Możesz uruchomić w trybie GUI (debug) poleceniem:

```powershell
npx playwright test --headed --debug
```

---

## 3. Integracja Playwright z GitHub Actions (CI)
Chcemy, aby testy Playwright uruchamiały się automatycznie przy każdym pushu do repo. W pliku `.github/workflows/playwright.yml` umieszczamy workflow, który:
- instaluje zależności (Node + Playwright, oraz Python i wymagane biblioteki),
- uruchamia aplikację (Flask) w tle,
- uruchamia Playwright — testy automatycznie sprawdzą UI.

Przykładowy workflow (gotowy do wklejenia):

```yaml
name: Playwright UI tests

on:
  push:
  pull_request:

jobs:
  test-e2e:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install Python deps
        run: |
          python -m pip install -r requirements.txt

      - name: Install Node deps
        run: |
          npm ci
          # Install Playwright browsers. We avoid --with-deps so CI stays lightweight.
          # Use `--with-deps` only if your CI needs system-level helpers (ffmpeg, extra libs).
          npx playwright install

      - name: Start Flask app
        run: |
          python -m pip install -e .
          flask --app app run --port 5000 &
        env:
          FLASK_ENV: development

      - name: Wait for port 5000
        uses: jakejarvis/wait-action@v0.2.0
        with:
          timeout: 30
          port: 5000

      - name: Run Playwright tests
        run: |
          npx playwright test --forbid-only
```

Run strategy (recommended):

- Smoke tests (fast, critical flows) run on push / PR to give quick feedback — a small subset of tests.
- Full suite runs nightly (or on-demand) to validate end-to-end functionality without blocking PRs.

CI behavior:
- Instaluje zależności (Python + Node + Playwright browsers),
- Uruchamia serwer (Flask) i czeka aż pod portem 5000 będzie dostępny,
- Uruchamia Playwright tests — smoke on PR/push, full on schedule; jeśli któryś test nie przejdzie, CI zgłosi błąd (pull request będzie wiedział, że coś popsuto).

---

## 4. Rekomendacje i dobre praktyki
- Uruchamiaj Playwright w trybie headless w CI (szybsze), ale miej też debugowe testy lokalnie.
- Testy E2E powinny być niezależne i szybkie (testuj kluczowe scenariusze), nie chciej przetestować wszystkiego full-stack w pojedynczym teście.
- Dodaj retry lub rozsądne timeouty dla kroków zależnych od sieci.

---

## 5. Co zrobię dalej (jeżeli chcesz)
- Mogę dodać plik `.github/workflows/playwright.yml` z powyższą konfiguracją i zintegrować uruchamianie E2E w CI.
- Mogę też przygotować bardziej rozbudowane scenariusze testowe (upload → binaryzacja → send-to-retouch → załaduj w retuszu) oraz instrukcję jak uruchamiać Playwright lokalnie krok po kroku.
