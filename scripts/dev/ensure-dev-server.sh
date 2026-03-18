#!/usr/bin/env bash
# ============================================================================
# ensure-dev-server.sh — odpowiednik ensure-dev-server.ps1
# ============================================================================
# Co robi:
#   Sprawdza, czy serwer deweloperski Flask działa pod adresem http://127.0.0.1:5000.
#   Jeśli nie — uruchamia go w tle i czeka, aż zacznie odpowiadać.
#   Zapisuje PID procesu do pliku dev-server.pid, żeby można go było później zatrzymać.
#
# Użycie:
#   ./scripts/dev/ensure-dev-server.sh                  # domyślnie: Flask na porcie 5000
#   ./scripts/dev/ensure-dev-server.sh http://127.0.0.1:8080 30   # inny URL, 30s timeout
#
# Zmienne środowiskowe:
#   PRE_PUSH_TEST_SERVER_CMD — niestandardowa komenda startowa (np. "gunicorn app:app")
# ============================================================================

set -euo pipefail

URL="${1:-http://127.0.0.1:5000}"
WAIT_SECONDS="${2:-20}"
START_CMD="${PRE_PUSH_TEST_SERVER_CMD:-}"

# Ustal katalog główny repo
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || dirname "$(dirname "$(realpath "$0")")")"
PID_FILE="$REPO_ROOT/dev-server.pid"

# Funkcja: czy serwer odpowiada?
test_server() {
    curl -s -o /dev/null -w '' --connect-timeout 2 "$URL" 2>/dev/null
}

# Jeśli plik PID istnieje — sprawdź, czy proces żyje i serwer odpowiada
if [[ -f "$PID_FILE" ]]; then
    existing_pid=$(head -1 "$PID_FILE" 2>/dev/null || true)
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null && test_server; then
        echo "Found running dev server (PID: $existing_pid) and it's responding at $URL"
        echo "$existing_pid"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

echo "Dev server not reachable. Attempting to start (background)..."

# Ustal komendę startową
if [[ -n "$START_CMD" ]]; then
    CMD_ARRAY=($START_CMD)
else
    PYTHON="$(command -v python3 || command -v python)" || {
        echo "Python not found in PATH. Cannot start dev server." >&2
        exit 2
    }
    CMD_ARRAY=("$PYTHON" -m flask --app app run --host 127.0.0.1 --port 5000 --no-debugger --no-reload)
fi

# Uruchom serwer w tle (stdout/stderr do pliku logu)
cd "$REPO_ROOT"
"${CMD_ARRAY[@]}" > /tmp/dev-server.log 2>&1 &
SERVER_PID=$!

echo "Started dev server process (PID: $SERVER_PID). Waiting up to $WAIT_SECONDS seconds..."

elapsed=0
while (( elapsed < WAIT_SECONDS )); do
    if test_server; then
        break
    fi
    sleep 1
    (( elapsed++ )) || true
done

if ! test_server; then
    echo "Server failed to start within $WAIT_SECONDS seconds." >&2
    kill "$SERVER_PID" 2>/dev/null || true
    exit 4
fi

echo "Server is up at $URL (PID: $SERVER_PID)."
echo "$SERVER_PID" > "$PID_FILE"
echo "$SERVER_PID"
exit 0
