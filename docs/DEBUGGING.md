# Debugging UI overlay & Playwright helper

Krótka instrukcja jak używać `scripts/debug_accept_playwright.js` do lokalnej diagnozy problemów z overlay (przycisk `#acceptWarning`) i uruchamianiem aplikacji w testach E2E.

## Po co to narzędzie
- Szybko sprawdza, czy przycisk `#acceptWarning` jest obecny i możliwy do kliknięcia.
- Wykonuje próbne kliknięcie i sprawdza, czy `#appContent` zostaje ujawnione (czyli aplikacja zainicjalizowała UI poprawnie).
- Loguje błędy strony / `pageerror` i requesty, co ułatwia odnalezienie problemów z inicjalizacją skryptów frontendu.

> Uwaga: skrypt jest przeznaczony do użytku lokalnego — nie uruchamiaj go automatycznie w CI.

## Wymagania
- Node.js (wersja zgodna z projektem)
- Playwright zainstalowany lokalnie (raz: `npm install` oraz `npx playwright install`)
- Działający dev server (Flask) dostępny pod `http://127.0.0.1:5000`

## Jak uruchomić
1. Uruchom serwer deweloperski (lokalnie):
   ```powershell
   C:/Users/DELL/miniconda3/envs/talk_flask/python.exe -m flask --app app run --debug
   ```
2. Uruchom skrypt:
   ```bash
   npm run debug:accept
   ```

Skrypt otworzy kontekst Playwright, poda krótkie logi i zakończy.

## Przykładowe wyjście i ich interpretacja

1) Normalne, oczekiwane wyjście (kliknięcie się powiodło):
```
#acceptWarning count: 1
#acceptWarning visible: true
click via page.click succeeded
appContent visible after click: true
appContent classlist:
```
Interpretacja: overlay istnieje i klik działa — UI powinno być w stanie interaktywnym.

2) Błąd inicjalizacji frontendu (widoczny w `PAGE ERROR`):
```
PAGE ERROR: Unexpected identifier 'highlightSegment'
#acceptWarning count: 1
#acceptWarning visible: true
click via page.click succeeded
appContent visible after click: false
appContent classlist: hidden
```
Interpretacja: klik działa, ale handler JS wywołujący `onShowApp()` mógł nie wykonać się z powodu błędu JS — sprawdź konsolę (stacktrace), napraw błąd (np. brakujący przecinek, niezainicjalizowana zmienna) i spróbuj ponownie.

3) Brak przycisku overlay (np. UI nie załadował DOM albo przycisk ma inny selektor):
```
#acceptWarning count: 0
#acceptWarning visible: false
```
Interpretacja: sprawdź, czy strona prawidłowo załadowała szablon (czy `templates/index.html` ma przycisk), czy żadne błędy sieciowe nie przerwały ładowania skryptów i czy serwer działa poprawnie.

## Kroki naprawcze
- Jeśli `PAGE ERROR` się pojawia: napraw błędy JS (sprawdź `static/js/*` oraz konsolę), zaktualizuj pliki i odśwież serwer.
- Jeśli klik nie powoduje ujawnienia `#appContent`: sprawdź handler `initUi()` (`static/js/ui.js`) i upewnij się, że event listener jest rejestrowany przed pokazaniem overlay.
- Jeśli nie widzisz `#acceptWarning` w DOM: zweryfikuj szablon (`templates/index.html`) i warunki, które go renderują.

## Dodatek: kiedy używać
- Przy flakach E2E (czekania na elementy, timeouty na widoczność) — uruchom szybko lokalnie, by zobaczyć, czy problem wynika z braku inicjalizacji UI lub z błędów JS.
- Przed uruchomieniem pełnego smoke suite — szybki sanity check lokalny.

---

Plik pomocny w codziennej pracy QA/dewelopera — jeśli chcesz, mogę dodać kilka przykładowych screenshotów/logów do katalogu `reports/` lub dodać testy integracyjne wykorzystujące ten helper do tworzenia artefaktów w `test-results/`.
