# CI / GitHub Actions — polecenia do monitorowania runów (wyjaśnienia po polsku)

Poniżej krótkie, jasne wyjaśnienia trzech poleceń używanych do sprawdzania statusów workflowów i ich logów na GitHubie.

---

## 1) gh run list --branch <branch> -L <n>
Przykład użycia:

  gh run list --branch feat/ci-add-e2e-auto-refresh -L 20

- Co robi (składniki):
  - `gh` — GitHub CLI (narzędzie do pracy z GitHub z terminala).
  - `run list` — lista uruchomień workflowów (actions runs) dla repozytorium.
  - `--branch <branch>` — filtruje listę, pokazuje tylko runy dotyczące wskazanej gałęzi.
  - `-L <n>` — limituje liczbę wyników zwracanych przez polecenie (np. -L 20 = maks. 20 wyników).
- Kiedy użyć: gdy chcesz szybko zobaczyć ostatnie runy dla danej gałęzi i ich ogólny status (queued / in_progress / completed / failed). To dobre pierwsze polecenie do szybkiego przeglądu historii uruchomień.

---

## 2) gh run view <ID> --log
Przykład:

  gh run view 21114852904 --log

- Co robi (składniki):
  - `gh run view <ID>` — wypisuje szczegóły konkretnego runu (ID = numer uruchomienia workflow).
  - `--log` — prosi o pobranie i pokazanie pełnych logów wykonanych kroków i jobów (stdout/krok po kroku).
- Uwaga: jeśli run jest nadal w toku, `gh` może zwrócić komunikat typu: `run <ID> is still in progress; logs will be available when it is complete`. Wtedy pełne logi będą dostępne dopiero po zakończeniu runu.
- Dodatkowo: `gh run view <ID> --web` otwiera UI danego runu w przeglądarce (przydatne do wygodnego przeglądu kroków i pobrania artefaktów jak zrzuty ekranu i raporty).

---

## 3) gh api <endpoint> --jq '<jq expression>' (przykład użycia dla jobów runu)
Przykład:

  gh api repos/robetr286/Talk_electronic/actions/runs/21114852904/jobs --jq '.jobs[] | {name: .name, status: .status, conclusion: .conclusion, steps: [.steps[] | {name: .name, status: .status, conclusion: .conclusion}] }'

- Co robi (składniki):
  - `gh api` — wykonuje dowolne wywołanie GitHub REST API (przydatne gdy potrzebujemy specyficznych danych).
  - `repos/<owner>/<repo>/actions/runs/<run_id>/jobs` — endpoint REST, zwraca listę jobów w ramach wskazanego runu.
  - `--jq '<expression>'` — filtruje/formatuje zwrócony JSON przy pomocy `jq` (wbudowanego mechanizmu w `gh`), dzięki czemu uzyskujemy tylko potrzebne pola w czytelnym formacie.
- Co zwraca: lista jobów z podstawowymi informacjami (nazwa jobu, status: `in_progress`/`completed`, conclusion: `success`/`failure`/`skipped`/`null`) oraz krótką listą kroków (`steps`) z ich nazwami i statusami.
- Kiedy użyć: gdy run jest w trakcie i `--log` nie pokazuje logów (bo są dostępne dopiero po zakończeniu), chcemy wiedzieć który job/krok jest aktywny lub gdzie dokładnie job się zatrzymał (np. instalacja zależności, uruchomienie testów itp.).

---

## Krótkie praktyczne wskazówki
- Jeśli `gh run view --log` zwraca komunikat, że run jest w toku, użyj `gh api .../jobs --jq ...` żeby zobaczyć na jakim jobie/stepie pracuje runner.
- Gdy chcesz szybko otworzyć run w UI (np. żeby pobrać artefakty), użyj `gh run view <ID> --web`.
- W sytuacji, gdy chcesz automatycznie monitorować lub integrować status runów w skryptach, `gh api` z `--jq` daje elastyczny sposób na automatyczne parsowanie i reakcję.

---

Plik można zaktualizować/rozszerzyć o dodatkowe przykłady (np. filtrowanie po statusie, wyświetlanie artefaktów). Jeśli chcesz, wkleję skróconą wersję tego tekstu bezpośrednio do `qa_git.md` (na Twoją prośbę).
