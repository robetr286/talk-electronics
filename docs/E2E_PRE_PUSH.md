# Pre-push E2E — opis i tłumaczenie / Pre-push E2E — description & translation

> CI: manual monitoring run triggered 2026-01-11 (test push)

Poniższy dokument wyjaśnia, co się wydarzy jeśli skonfigurujesz lokalny pre-push hook uruchamiający szybki zestaw E2E (smoke) przed wypchnięciem zmian do zdalnego repo.

Wersja PL (szybkie, jasne instrukcje)
- Cel: odpalać lokalnie krótki zestaw testów E2E (smoke) przed wykonaniem `git push`, aby wychwycić najszybsze, krytyczne regresje i uniknąć push-owania błędnego kodu do zdalnego repo.
- Co się stanie (przykładowy pre-push):
  1. Hook uruchomi skrypt `npm run test:e2e:smoke`.
  2. Jeśli testy przejdą → push zostaje wykonany normalnie.
  3. Jeśli testy zakończą się porażką → hook przerwie push i wyświetli informacje o błędzie; możesz poprawić testy/zmiany i spróbować ponownie.

- Zalety:
  - Szybkie sprawdzenie krytycznych przepływów lokalnie przed wysłaniem zmian.
  - Mniej fałszywych PR i szybsze wykrywanie problemów.

- Ograniczenia / uwagi:
  - Hook działa lokalnie (nie wpływa na CI). Pełna bateria testów nadal powinna uruchamiać się w CI (np. nightly lub PR).
  - Pre-push może opóźnić workflow developerski, dlatego używamy tylko krótkiego zestawu smoke (kilka najważniejszych testów), a nie pełnego.

Przykładowy prosty pre-push hook (Linux / macOS / Git Bash / WSL / Git for Windows):

```sh
#!/bin/sh
echo "Running E2E smoke tests before push..."

# Zakładamy że serwer dev działa lokalnie (albo uruchom go w drugim terminalu)
# Uruchom szybkie testy smoke (szybkie, krytyczne przepływy)
npm run test:e2e:smoke --silent
ret=$?
if [ $ret -ne 0 ]; then
  echo "Smoke tests failed — push aborted. Fix tests or use 'git push --no-verify' to override.";
  exit 1
fi
exit 0
```

Uwaga (Windows PowerShell): użyj prostego skryptu PowerShell lub narzędzia `husky` (zalecane) aby hook był przenośny.

---

EN version — short explanation for non-Polish speakers
- Goal: run a thin E2E smoke test set locally before `git push` to catch obvious critical regressions and avoid pushing broken code upstream.
- Behaviour (example pre-push):
  1. Hook runs `npm run test:e2e:smoke` (local quick tests).
  2. If tests pass → push proceeds.
  3. If tests fail → push is aborted and you get a failure message. Fix tests/changes and try again.

- Benefits:
  - Fast local verification of key flows before push.
  - Fewer broken PRs and earlier detection of regressions.

- Caveats:
  - This is a local safeguard only; CI must still run the full test suite (or nightly runs) before merges to main or release.
  - Running a pre-push hook can slow down your commits if the smoke suite is large — keep smoke tiny and focused.

Example PowerShell pre-push snippet (Windows) — minimal, run in `.git/hooks/pre-push` (make executable as needed):

```powershell
#!/usr/bin/env pwsh
Write-Output "Running E2E smoke tests before push..."
$result = npm run test:e2e:smoke --silent
if ($LASTEXITCODE -ne 0) {
  Write-Error "Smoke tests failed — push aborted. Fix tests or run 'git push --no-verify' to override."
  exit 1
}
exit 0
```

## Interaktywny hook PowerShell (lokalnie)

Jeżeli chcesz mieć wygodniejszy, mniej inwazyjny pre-push na Windowsie, w repo dodaliśmy interaktywny skrypt PowerShell `scripts/hooks/pre-push-windows.ps1`.

- Zachowanie:
  - Sprawdza, czy dev server jest dostępny pod `http://127.0.0.1:5000`.
  - Jeżeli serwer nie działa — pyta użytkownika (Y/n) czy uruchomić go lokalnie.
  - Jeśli użytkownik zgodzi się, hook uruchamia serwer w tle *i zapisuje PID procesu*.
  - Po zakończeniu testów hook **zatrzymuje tylko proces, który sam uruchomił**. Dzięki temu nie zamknie serwera uruchomionego ręcznie przez użytkownika (brak "stray process" problemu).

- Drobne uwagi techniczne:
  - Skrypt w repo został poprawiony, żeby być kompatybilny z PowerShell 5.1 (usunięto mieszanie flag `-NoNewWindow` i `-WindowStyle` oraz zastąpiono nie-ASCII myślniki ASCII). To zapobiega błędom parsowania w starszych runtime PowerShell.

Jeżeli chcesz, mogę automatycznie zainstalować ten skrypt do Twojego lokalnego `.git/hooks/pre-push` i przetestować scenariusze — uruchamianie serwera, przerywanie i czyszczenie procesu. Daj znać czy mam to zrobić.

---

## Krok po kroku — co robi hook i jak go zainstalować

### 1) Co dokładnie się dzieje przy `git push`
- Hook jest pre-push (uruchamiany tylko przy `git push`).
- Sprawdza, czy lokalny dev server odpowiada na http://127.0.0.1:5000.
- Jeśli serwer jest dostępny: uruchamia szybki zestaw smoke testów `npm run test:e2e:smoke`.
- Jeśli serwer nie jest dostępny: pytanie interaktywne (Y/n). Jeśli odpowiesz tak, hook uruchomi serwer w tle (domyślnie: `python -m flask --app app run --host 127.0.0.1 --port 5000 --no-reload`), poczeka aż będzie dostępny, odpali testy, a następnie zatrzyma tylko proces, który sam uruchomił.
- Jeżeli testy przejdą → push kontynuuje; jeśli testy się nie powiodą → push jest przerwany (exit code != 0).

### 2) Jak zainstalować lokalnie (Windows)
1. W repo: uruchom instalator (tworzy kopię zapasową istniejącego hooka oraz wrapper):
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/hooks/install-pre-push.ps1
```
2. Po instalacji sprawdź wrapper `.git/hooks/pre-push` (uruchomi PowerShell) i wykonaj szybki test manualnie:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .git/hooks/pre-push.ps1
```
3. Gdy chcesz zrezygnować: przywróć backup lub usuń lokalny hook:
```powershell
Move-Item .git/hooks/pre-push.ps1.bak .git/hooks/pre-push.ps1 -Force  # przywrócenie
Remove-Item .git/hooks/pre-push.ps1 -Force                          # usunięcie
```

### 3) Szybkie testy bez interakcji (automatyczny tryb)
- Ustaw zmienne środowiskowe, żeby hook działał w trybie automatycznym (przydatne do testów lub CI lokalnego):
  - `PRE_PUSH_ASSUME=Y` — automatycznie przyjmuj start serwera (odpowiednik wpisania 'Y')
  - `PRE_PUSH_ASSUME=n` — automatycznie odmów startu serwera
  - `PRE_PUSH_TEST_SERVER_CMD='-m http.server 5000'` — zamiast Flask użyje `python -m http.server 5000` (przydatne podczas testów bez zależności Flask)

Przykład użycia (uruchomienie i przetestowanie bez interakcji):
```powershell
$env:PRE_PUSH_ASSUME='Y'
$env:PRE_PUSH_TEST_SERVER_CMD='-m http.server 5000'
powershell -NoProfile -ExecutionPolicy Bypass -File .git/hooks/pre-push.ps1
Remove-Item env:PRE_PUSH_ASSUME, env:PRE_PUSH_TEST_SERVER_CMD -ErrorAction SilentlyContinue
```

### 4) Krótkie FAQ
- Czy to uruchamia testy przy każdym commicie? Nie — tylko przy `git push` (pre-push). Dla pre-commit należy stosować oddzielny pre-commit hook.
- Co jeśli chcę pominąć hook? Użyj `git push --no-verify`.

---

## Step-by-step — what the hook does and how to install it (EN)

### 1) What happens at `git push`
- The hook is a pre-push hook (runs only on `git push`).
- It first checks if the dev server responds at http://127.0.0.1:5000.
- If the server is up: it runs the quick smoke test suite `npm run test:e2e:smoke`.
- If the server isn't reachable: it prompts the user (Y/n). If accepted, the hook starts the server in the background (by default: `python -m flask --app app run --host 127.0.0.1 --port 5000 --no-reload`), waits until ready, runs the smoke tests, and then stops only the process it started.
- If tests pass → push proceeds. If tests fail → push is aborted (exit code != 0).

### 2) How to install locally (Windows)
1. From repo root run the installer (it will backup existing local hook and create a wrapper):
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/hooks/install-pre-push.ps1
```
2. Verify wrapper `.git/hooks/pre-push` (it should call the PS script) and test manually:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .git/hooks/pre-push.ps1
```
3. To remove or restore backup:
```powershell
Move-Item .git/hooks/pre-push.ps1.bak .git/hooks/pre-push.ps1 -Force  # restore
Remove-Item .git/hooks/pre-push.ps1 -Force                          # uninstall
```

### 3) Test mode / non-interactive runs
- These environment variables allow testing the hook without manual input and without Flask:
  - `PRE_PUSH_ASSUME=Y` — always accept starting server
  - `PRE_PUSH_ASSUME=n` — always decline
  - `PRE_PUSH_TEST_SERVER_CMD='-m http.server 5000'` — use `python -m http.server` instead of Flask to avoid extra dependencies

Example (run in a single PowerShell session):
```powershell
$env:PRE_PUSH_ASSUME='Y'
$env:PRE_PUSH_TEST_SERVER_CMD='-m http.server 5000'
powershell -NoProfile -ExecutionPolicy Bypass -File .git/hooks/pre-push.ps1
Remove-Item env:PRE_PUSH_ASSUME, env:PRE_PUSH_TEST_SERVER_CMD -ErrorAction SilentlyContinue
```

### Stop / cleanup script
If you need to stop a dev server that was started by the hook (or clean up a stale `dev-server.pid`), use the helper:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/stop-dev-server.ps1
```
This will attempt to stop the process referenced by `dev-server.pid` (if running) and remove the pid file. Use `-Force` to ignore failures stopping the process.

### Developer tests (Pester)
We ship a small suite of PowerShell unit/integration tests using Pester to guard the hook and helper scripts. Run them locally with:
```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -Command "Import-Module Pester -MinimumVersion 5.0; Invoke-Pester -Script 'tests/pester'"
```
The CI workflow `pre-push-dry-run.yml` runs these tests on Windows runners as part of the dry-run job.

### 4) Quick FAQ
- Will this run tests on every commit? No — the hook is pre-push only. Use pre-commit or Husky to run tests pre-commit.
- Want to skip the hook? Use `git push --no-verify`.


---

Jeżeli chcesz, mogę:
- dodać przykładowy pre-push hook do repo (np. w `scripts/hooks/pre-push-example`), lub
- skonfigurować `husky` aby zarządzać hookami przy pomocy `package.json`, albo
- zostawić instrukcję i nie zapisywać żadnych hooków w repo (wygodniejsze, mniej inwazyjne).
