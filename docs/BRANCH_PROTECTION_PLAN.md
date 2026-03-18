# Plan: Konfiguracja ochrony gałęzi (branch protection)

Cel
----
Zabezpieczyć gałąź `main` w repozytorium tak, aby blokować scalanie (merge) dopóki nie przejdą krytyczne status‑checki CI i nie zostanie udzielone wymagane review. Konfiguracja powinna być łatwa do automatyzacji, zawierać kroki weryfikacyjne i opcję podniesienia do poziomu organizacji (org‑level Ruleset) po upgrade do planu Team.

8 punktów planu
----------------
1) Przygotowanie (wymagania)
   - Uprawnienia: konto z rolą repo‑admin/owner.
   - PAT (Personal Access Token) z zakresem `repo` (i `admin:org` gdy będzie potrzeba Rulesetów organizacji).
   - `gh` CLI (opcjonalnie) lub dostęp do REST API GitHub.

2) Jak zidentyfikować dokładne nazwy status‑checków
   - Utwórz tymczasowy branch + draft PR, odpalą się workflowy i w UI pojawią się nazwy checków.
   - Alternatywa: pobierz check‑runs przez API i odczytaj pole `name`.

3) Classic: ręczna konfiguracja w UI (szybka)
   - Repo → Settings → Branches → Add rule dla pattern `main`.
   - Przełącz: Require a pull request before merging, Require status checks (wybierz checki), Require approving review count (min 1), opcjonalnie enforce for admins i require up‑to‑date.

4) Classic: automatyczne ustawienie przez API / skrypt (curl / gh / PowerShell)
   - Endpoint: PUT /repos/{owner}/{repo}/branches/{branch}/protection
   - W payloadzie `required_status_checks.contexts` podaj dokładne nazwy checków (np. "test (3.11)", "lint", "smoke", "Run gating check (fast)", "full-suite").
   - Ustaw `enforce_admins` i `required_pull_request_reviews` wedle polityki.

5) Opcja: Org-level Ruleset (po upgrade do Team)
   - Umożliwia wymuszanie reguł na poziomie organizacji (applied across repos).
   - Endpoint: POST /orgs/{org}/rulesets (wymaga `admin:org`).
   - Payload: warunki obejmujące branches.include ["main"], checks.include listę checków i ustawienia approval/min approvers.

6) Rekomendowany minimalny zestaw zasad
   - Wymuszony PR do scalania (Require pull request)
   - Wymagane status‑checki: test (3.11), lint, smoke, Run gating check (fast), full‑suite
   - Min 1 approval (require_approving_review_count = 1)
   - Dismiss stale reviews (opcjonalne)
   - Enforce for admins (zalecane gdy chcesz surową ochronę)

7) Weryfikacja i testowanie po konfiguracji
   - Stwórz nowy branch → utwórz PR → sprawdź czy wymagane checki pojawiają się jako required i blokują merge do czasu przejścia.
   - Użyj API GET /repos/{owner}/{repo}/branches/{branch}/protection, żeby odczytać aktualne ustawienia.

8) Pułapki i dobre praktyki
   - Dokładne nazwy checków są CASE‑SENSITIVE; używaj dokładnych ciągów z UI/APi.
   - Przetestuj zmiany na testowym repo przed zastosowaniem w `main` produkcyjnie.
   - Oszczędzaj i chroń PAT (nie publikuj go).
   - Jeżeli support GitHub instruuje o niestosowaniu polskich znaków — stosuj ich wskazówki przy wypełnianiu pól w UI/API.

---

Plik przygotowany automatycznie przez narzędzie robocze — mogę na jego podstawie wygenerować gotowy skrypt PowerShell / curl / gh do uruchomienia (gdy potwierdzisz nazwy checków i token PAT).
