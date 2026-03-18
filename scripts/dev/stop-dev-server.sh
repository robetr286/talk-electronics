#!/usr/bin/env bash
# ============================================================================
# stop-dev-server.sh — odpowiednik stop-dev-server.ps1
# ============================================================================
# Co robi:
#   Zatrzymuje serwer deweloperski Flask, który został wcześniej uruchomiony
#   przez ensure-dev-server.sh. Odczytuje PID z pliku dev-server.pid,
#   wysyła sygnał SIGTERM i usuwa plik PID.
#
# Użycie:
#   ./scripts/dev/stop-dev-server.sh
# ============================================================================

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || dirname "$(dirname "$(realpath "$0")")")"
PID_FILE="$REPO_ROOT/dev-server.pid"

if [[ ! -f "$PID_FILE" ]]; then
    echo "No pid file found at $PID_FILE"
    exit 0
fi

pid=$(head -1 "$PID_FILE" 2>/dev/null || true)

if [[ -z "$pid" ]]; then
    rm -f "$PID_FILE"
    echo "Removed empty pid file"
    exit 0
fi

if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null && echo "Stopped process PID $pid" || echo "Failed to stop process $pid" >&2
else
    echo "No running process found for PID $pid - removing stale pid file"
fi

rm -f "$PID_FILE"
echo "Cleanup complete"
exit 0
