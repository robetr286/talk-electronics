## Q&A — pre-push PowerShell hook (zapis rozmowy)

Poniżej dopisuję krótkie pytania użytkownika i moje odpowiedzi, aby zachować kontekst i postęp prac — dokończymy jutro.

- Q: "Zrób 1." (uruchomienie instalacji lokalnej hooka)
  - A: Planowałem zainstalować `scripts/hooks/pre-push-windows.ps1` do `.git/hooks/pre-push.ps1` i przetestować trzy scenariusze (serwer już działa / serwer nie działa + zgoda na start / serwer nie działa + odmowa). Proces instalacji przerwałeś ze względu na długi czas — zapisałem postępy i dopisuję log rozmowy.

- Q: "Dlaczego występował błąd parsowania (Missing closing '}')?"
  - A: Przyczyną były dwa problemy: (1) w pliku znalazły się nie-ASCII znaki myślnika (em-dash‑like), które powodowały problemy z parserem w PowerShell 5.1, (2) użycie obu flag Start-Process (`-NoNewWindow` i `-WindowStyle`) na raz — to też generowało błąd. Naprawiłem obie sprawy (zastąpiłem myślniki ASCII i usunąłem konfliktującą flagę) w `scripts/hooks/pre-push-windows.ps1` i lokalnej kopii `.git/hooks/pre-push.ps1`.

- Q: "Czy hook bezpiecznie sprząta uruchomiony proces?"
  - A: Tak — hook zapisuje obiekt procesu (PID) tylko wtedy, gdy sam uruchomi serwer, i tylko wtedy zatrzymuje proces po zakończeniu testów. Nie zatrzyma serwera uruchomionego ręcznie przez użytkownika.

- Q: "Jak mogę go zainstalować u siebie lokalnie?"
  - A: Kopiuj plik i (opcjonalnie) zainstaluj bat-wrapper:
    - Copy-Item scripts/hooks/pre-push-windows.ps1 .git/hooks/pre-push.ps1 -Force
    - (opcjonalnie) utwórz wrapper `.git/hooks/pre-push` uruchamiający PowerShell z opcją `-ExecutionPolicy Bypass`.

- Q: "Co jest dalej?"
  - A: Dokończyć instalację i pełne testy na Twojej maszynie — przetestować scenariusze uruchomienia i sprzątania procesu; ewentualnie rozważyć `husky` dla przenośności hooków.

---

Zapis dopisany: 23 listopada 2025 — prace w toku, dokończymy jutro.

---

## Dalszy postęp — 24 listopada 2025

- Wdrożenie pre-push testów: potwierdziłem i zainstalowałem skrypt lokalnie w moim środowisku i przetestowałem trzy scenariusze:
  - A — serwer już działa -> hook wykrywa i odpala smoke (pass) → push kontynuowany.
  - B — serwer nie działa + zgoda -> hook uruchamia serwer (testowy), odpala smoke (pass), sprząta uruchomiony proces.
  - C — serwer nie działa + odmowa -> hook przerywa push (exit code 1).

- Dodatkowe pliki dodane: `scripts/hooks/install-pre-push.ps1` — prosty instalator, który kopiuje hook do lokalnego `.git/hooks` i tworzy wrapper. To ułatwia wdrożenie na kolejnych maszynach deweloperskich.

- Wprowadzono także wsparcie testowe: zmienne środowiskowe `PRE_PUSH_ASSUME` i `PRE_PUSH_TEST_SERVER_CMD` (pomagają automatyzować testy hooka bez interakcji i bez zależności Flask).

- Dodatkowe notatki: zaktualizowałem `docs/E2E_PRE_PUSH.md` (PL + EN) o szczegółowe instrukcje krok-po-kroku, test mode i FAQ.

Stan: wdrożenie lokalne przetestowane. Jeżeli chcesz, mogę teraz zautomatyzować instalację hooka na Twojej maszynie (uruchomić skrypt instalacyjny) albo skonfigurować `husky` dla łatwiejszego udostępniania hooków w zespole.

---

## Wykonane kroki — zainstalowano lokalnie (24 listopada 2025)

- Na Twoje życzenie wdrożyłem lokalny pre-push hook przy użyciu `scripts/hooks/install-pre-push.ps1`. Skrypt utworzył backup (jeżeli nie istniał) i zainstalował lokalny wrapper `.git/hooks/pre-push` oraz skrypt `.git/hooks/pre-push.ps1`.
- Przeprowadziłem bezpieczne testy (z użyciem tymczasowego stubu dla `npm` aby nie uruchamiać Playwright): trzy scenariusze zweryfikowane — server already running, server not running + accept, server not running + decline. Wynik: wszystkie zachowania zgodne z oczekiwaniami (hook uruchamia testy tylko przy push, uruchamia serwer tylko gdy zaakceptujesz i czyści tylko proces, który sam uruchomił).

- Dalsze opcje:
  - Jeżeli chcesz, mogę dodać `husky` by hooki były automatycznie instalowane dla wszystkich devów (polecane),
  - Albo pozostawić obecny instalator i instrukcję (mniej inwazyjne).

Jeżeli potwierdzasz — mogę teraz uruchomić skrypt instalacyjny u Ciebie w repo (jeśli chcesz, zrobię to od razu) i dostarczę krótki log potwierdzający.
