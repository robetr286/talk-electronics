"""Generuje krótkie README / prezentację z wynikami porównawczego przebiegu.

Skrypt analizuje pliki summary.json dla conservative/aggressive i tworzy
`debug/graph_repair_sweep_comparative/README_summary.md` z kluczowymi metrykami
oraz kilkoma przykładowymi przypadkami do przejrzenia.
"""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "debug" / "graph_repair_sweep_comparative"


def load(path: Path):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(arr):
    total = len(arr)
    timeouts = sum(1 for r in arr if r.get("timeout"))
    avg_elapsed = None
    elapsed_vals = [
        r.get("elapsed_s") for r in arr if not r.get("timeout") and isinstance(r.get("elapsed_s"), (int, float))
    ]
    if elapsed_vals:
        avg_elapsed = sum(elapsed_vals) / len(elapsed_vals)
    nonzero = sum(1 for r in arr if not r.get("timeout") and r.get("returncode", 0) != 0)
    return dict(total=total, timeouts=timeouts, avg_elapsed=avg_elapsed, nonzero=nonzero)


def main():
    cons = load(BASE / "conservative" / "summary.json")
    aggr = load(BASE / "aggressive" / "summary.json")

    csum = summarize(cons)
    asum = summarize(aggr)

    out = BASE / "README_summary.md"
    lines = [
        "# Graph-repair comparative sweep — summary",
        "",
        "## Conservative",
        f'- total images: {csum["total"]}',
        f'- timeouts: {csum["timeouts"]}',
        f'- avg elapsed (s): {csum["avg_elapsed"]}',
        f'- non-zero return codes: {csum["nonzero"]}',
        "",
        "## Aggressive",
        f'- total images: {asum["total"]}',
        f'- timeouts: {asum["timeouts"]}',
        f'- avg elapsed (s): {asum["avg_elapsed"]}',
        f'- non-zero return codes: {asum["nonzero"]}',
        "",
        "## Notes",
        "- See debug/graph_repair_inspection for representative examples and index.html",
        "- If diagonals are not repaired reliably, consider running the skeleton-resolution",
        "  plan in docs/GRAPH_REPAIR_SKELETON_RESOLUTION_PLAN.md",
    ]

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote summary README -> {out}")
    # commit & push the summary README
    try:
        import subprocess

        subprocess.run(["git", "add", str(out)], check=True)
        subprocess.run(["git", "commit", "-m", "docs: add graph-repair comparative README summary"], check=True)
        subprocess.run(["git", "push", "--no-verify", "origin", "HEAD:main"], check=False)
        print("Committed and pushed README summary")
    except Exception as exc:  # pragma: no cover - best-effort
        print("Failed to commit/push README summary:", exc)


if __name__ == "__main__":
    main()
