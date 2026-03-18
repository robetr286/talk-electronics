#!/usr/bin/env bash
# ============================================================================
# install-pre-push.sh — instaluje hook pre-push dla Linuxa
# ============================================================================
# Co robi:
#   Kopiuje pre-push-linux.sh do .git/hooks/pre-push i nadaje mu
#   uprawnienia wykonywalne, aby hook uruchamiał się automatycznie
#   przed każdym git push.
#
# Użycie:
#   bash scripts/hooks/install-pre-push.sh
# ============================================================================

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_SRC="$REPO_ROOT/scripts/hooks/pre-push-linux.sh"
HOOK_DST="$REPO_ROOT/.git/hooks/pre-push"

if [[ ! -f "$HOOK_SRC" ]]; then
    echo "Błąd: nie znaleziono $HOOK_SRC" >&2
    exit 1
fi

mkdir -p "$REPO_ROOT/.git/hooks"
cp "$HOOK_SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"
echo "✅ Hook pre-push zainstalowany: $HOOK_DST"
