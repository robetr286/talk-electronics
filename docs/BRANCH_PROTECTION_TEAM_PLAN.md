# Branch protection — plan Team (instrukcja)

Ten dokument zbiera kroki i przykłady, żeby skonfigurować wymuszanie status checks/Rulesets na GitHub po przejściu na plan Team.

Krótko — skoro wybrałeś/aś plan Team: możesz utworzyć Organization Ruleset i wymusić sprawdzanie statusów (status checks) dla prywatnych repo.

1) Najważniejsze nazwy checków / jobów które warto dodać jako wymagane

- `test (3.11)`  — job test z matrixem Pythona (z workflow `Tests`)
- `lint`         — job lint z workflow `Tests`
- `smoke`        — Playwright smoke job (workflow `Playwright E2E`)
- `Run gating check (fast)` — fast gating job (workflow `PR gating — local_patch_repair`)

Użyj dokładnych nazw tak jak pojawiają się na liście status checks w interfejsie GitHub.

2) Ręczny UI (szybkie kroki)

- Organizacja → Settings → Policies and rules (Reguły) → Rulesets → New ruleset
- Zaznacz repo (albo use pattern) oraz podaj gałąź bazową (np. `refs/heads/main`)
- Włącz protections:
  - Required status checks → dodaj powyższe konteksty (test (3.11), lint, smoke, Run gating check (fast))
  - Require branches to be up to date before merging (recommended)
  - Require pull request reviews (np. min 1) oraz inne opcje (signed commits, linear history, etc.)
  - Włącz enforcement dla administracji (jeżeli chcesz żeby admins też musieli spełniać checks)

3) Klasyczne branch protection (repo-level) — REST API przykładowy payload

Endpoint (classic branch protection):

PUT /repos/:owner/:repo/branches/:branch/protection

Przykładowe ciało JSON (strict=true wymusza "up-to-date"):

{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "test (3.11)",
      "lint",
      "smoke",
      "Run gating check (fast)"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1
  },
  "restrictions": null
}

4) Przykładowe polecenie PowerShell (gh + GH_TOKEN powinny być ustawione):

```powershell
# Ustawienie klasycznego branch protection (repo-level)
$owner = 'robetr286'
$repo = 'Talk_electronic'
$branch = 'main'
$body = @{
  required_status_checks = @{ strict = $true; contexts = @("test (3.11)","lint","smoke","Run gating check (fast)") }
  enforce_admins = $true
  required_pull_request_reviews = @{ required_approving_review_count = 1 }
  restrictions = $null
} | ConvertTo-Json -Depth 5

gh api --method PUT "/repos/$owner/$repo/branches/$branch/protection" --input - <<JSON
$body
JSON
```

5) Jeśli chcesz utworzyć Organization Ruleset programowo (po zakupie Team):

- Możesz użyć GitHub REST/GraphQL (org-level rulesets endpoints). Najwygodniej — użyć `gh api` z odpowiednim JSON.
- Przy tworzeniu rulesetu w JSON uwzględnij requiredStatusChecks i wymagane konteksty (jak wyżej). Upewnij się, że token ma uprawnienia admin:org / repo.

6) Test weryfikacyjny po ustawieniu

- Stwórz PR z commitem, który celowo powoduje błąd testów (np. drobny bug) i spróbuj zmerge'ować — powinno być zablokowane.
- W razie wątpliwości przetestuj obie konfiguracje (org Ruleset i klasyczne branch-protection) i sprawdź co jest włączone (UI pokaże enforcement).

7) Dobre praktyki

- Wymagaj co najmniej 1 approver + status checks.
- Włącz "Require branches to be up to date" jeśli chcesz dodatkowo zmusić aktualizację gałęzi PR (redukuje rebase/merge conflicts problems).
- Ogranicz kto może pushować na protected branches (jeśli chcesz mieć centralną kontrolę).

---
Jeśli chcesz, mogę teraz:
- wygenerować PowerShell/Script (gotowy do uruchomienia) by ustawić klasyczne branch protection natychmiast, albo
- przygotować skrypt, który tworzy Organization Ruleset (po tym jak skończysz zakup planu Team).
