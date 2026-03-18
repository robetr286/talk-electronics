#!/usr/bin/env bash
# ============================================================================
# pre-push-linux.sh — odpowiednik pre-push-windows.ps1
# ============================================================================
# Co robi:
#   Hook pre-push dla systemu Linux. Przed każdym pushem:
#   1. Sprawdza, czy serwer deweloperski Flask jest uruchomiony
#   2. Jeśli nie, opcjonalnie uruchamia go automatycznie
#   3. Uruchamia testy smoke E2E (npm run test:e2e:smoke)
#   4. Jeśli testy nie przejdą — push jest blokowany
#
# Zmienne środowiskowe:
#   PRE_PUSH_ASSUME        — "yes" pomija pytanie o auto-start serwera
#   PRE_PUSH_TEST_SERVER_CMD — nadpisuje komendę do uruchomienia serwera
#   PRE_PUSH_SKIP_SMOKE    — 1/true pomija testy smoke
#
# Użycie:
#   Instalacja: ./scripts/hooks/install-pre-push.sh
#   Lub ręcznie: cp scripts/hooks/pre-push-linux.sh .git/hooks/pre-push
# ============================================================================

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SERVER_SCRIPT="$REPO_ROOT/scripts/dev/ensure-dev-server.sh"
STOP_SCRIPT="$REPO_ROOT/scripts/dev/stop-dev-server.sh"

# ---- Skip smoke? ----
if [[ "${PRE_PUSH_SKIP_SMOKE:-}" == "1" || "${PRE_PUSH_SKIP_SMOKE:-}" == "true" ]]; then
    echo "[pre-push] PRE_PUSH_SKIP_SMOKE ustawione — pomijam testy smoke"
    exit 0
fi

# ---- Sprawdź / uruchom serwer ----
started_by_hook=false

server_running() {
    curl -sf -o /dev/null "http://127.0.0.1:5000/" 2>/dev/null
}

if ! server_running; then
    # Sprawdź czy mamy auto-start w git config
    auto_start=$(git config --get hooks.devserver.autoStart 2>/dev/null || echo "")

    if [[ "${PRE_PUSH_ASSUME:-}" == "yes" || "$auto_start" == "true" ]]; then
        echo "[pre-push] Serwer nie działa — uruchamiam automatycznie…"
        bash "$SERVER_SCRIPT"
        started_by_hook=true
    else
        echo "[pre-push] Serwer deweloperski nie odpowiada na http://127.0.0.1:5000/"
        echo "Opcje:"
        echo "  1) Uruchom ręcznie: bash $SERVER_SCRIPT"
        echo "  2) Ustaw auto-start: git config hooks.devserver.autoStart true"
        echo "  3) Pomiń: PRE_PUSH_SKIP_SMOKE=1 git push"
        exit 1
    fi
fi

# ---- Uruchom testy E2E smoke ----
echo "[pre-push] Uruchamiam testy smoke E2E…"
test_cmd="${PRE_PUSH_TEST_SERVER_CMD:-npm run test:e2e:smoke}"
test_exit=0
if ! eval "$test_cmd"; then
    test_exit=1
fi

# ---- Cleanup: jeśli hook uruchomił serwer, zatrzymaj go ----
if $started_by_hook; then
    echo "[pre-push] Zatrzymuję serwer uruchomiony przez hook…"
    bash "$STOP_SCRIPT" 2>/dev/null || true
fi

if [[ $test_exit -ne 0 ]]; then
    echo "[pre-push] ❌ Testy smoke FAILED — push zablokowany"
    exit 1
fi

echo "[pre-push] ✅ Testy smoke OK"
exit 0
