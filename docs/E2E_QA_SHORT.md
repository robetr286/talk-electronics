# E2E — krótkie podsumowanie i komendy (Q&A)

Plik zawiera krótkie objaśnienie, kiedy używać E2E, minimalne komendy do uruchamiania testów lokalnie oraz krótką rekomendację dotyczącą automatycznego uruchamiania testów przed push.

## Krótko — co zrobiłem
- Utrzymujemy E2E, ale jako mały, krytyczny zestaw (`smoke`) + pełny zestaw (`full`).
- Nagrywanie wideo: wyłączone domyślnie. Zapisujemy screenshoty i trace tylko przy porażce.
- CI: smoke uruchamiany na push/PR, pełna bateria uruchamiana nightly (cron).

## Najważniejsze polecenia (PowerShell)

1) Uruchom serwer (w terminalu):

```powershell
conda activate talk_flask
python -m flask --app app run --host 127.0.0.1 --port 5000 --no-debugger --no-reload
```

2) Smoke tests (lokalnie — szybkie, krytyczne):

```powershell
npm ci            # jeśli jeszcze nie zainstalowane
npm run test:e2e:smoke -- --reporter=list
```

3) Full suite (wszystkie testy):

```powershell
npm run test:e2e:full -- --reporter=list
```

4) Debug (interaktywnie, headed):

```powershell
npx playwright test tests/e2e/retouch_flow.spec.js --headed --debug
```

## Czy testy powinny się uruchamiać przed pushem?

Krótko: tak — ale rozsądnie.

- Zalecenie: uruchamiać mały, szybki zestaw **smoke** lokalnie (np. pre-push hook) przed wysłaniem zmian, aby szybko wyłapywać oczywiste regresje.
- Niezalecane: uruchamianie całej, pełnej puli (full) bezpośrednio przed każdym pushem — to może być wolne i uciążliwe.
- Zamiast full przed push: zostaw full do CI (scheduled/nightly) lub uruchamiaj ręcznie przed większym release.

Dlaczego?
- Pre-push smoke: szybkie, mniejsze ryzyko blokowania pracy - daje natychmiastowe info.
- CI / PR: pełna weryfikacja powinna się odbywać na serwerze CI (PR), nie lokalnie na każdym puszu.

## Jak to dodać lokalnie (przykład — prosty pre-push hook)

W katalogu repo utwórz plik `.git/hooks/pre-push` (wersja powershell):

```powershell
#!/bin/sh
echo "Running E2E smoke tests before push..."
# startuj serwer w tle (jeśli nie jest uruchomiony) - tutaj przyjmujemy że dev server działa lokalnie
# uruchom tylko szybkie testy smoke, zakończ push gdy nieudane
npm run test:e2e:smoke --silent
if [ $? -ne 0 ]; then
  echo "Smoke tests failed — push aborted. Fix tests or run 'git push --no-verify' to override.";
  exit 1
fi
exit 0
```

Uwaga: pre-push hook działa lokalnie i wymaga Node + Playwright + aktywowanego serwera. Możemy dodać zamiast tego narzędzie `husky` dla bardziej przenośnego rozwiązania.

## Gdzie znaleźć artefakty po porażce
- `tests/e2e/artifacts/` — screeny, trace (lokalnie i CI są uploadowane jako artefakty).
- `playwright-report/` — skondensowany HTML report.

---

Jeśli chcesz, mogę:
- dodać przykładowy pre-push hook do repo (lokalny, jako przykład),
- pomóc skonfigurować `husky` / automatyczny mechanizm hooków, lub
- rozszerzyć listę smoke tests o kolejne krytyczne ścieżki.
