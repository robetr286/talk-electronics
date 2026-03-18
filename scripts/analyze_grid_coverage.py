#!/usr/bin/env python3
"""
🗺️ Grid Sector Analyzer - Narzędzie do analizy pokrycia siatki w anotacjach

Analizuje eksportowane anotacje Label Studio i pokazuje, które sektory siatki 3x3
zostały zanotowane w polu 'comment'.

Usage:
    python analyze_grid_coverage.py <export.json>
"""

import json
import sys
from collections import defaultdict


def parse_sector(comment: str) -> str:
    """Ekstraktuj sektor (np. 'A1', 'B2') z komentarza."""
    if not comment:
        return None

    # Szukaj wzorca [A-C][1-3]
    import re

    match = re.search(r"\b([A-C])([1-3])\b", comment.upper())
    if match:
        return match.group(0)
    return None


def analyze_coverage(export_path: str):
    """Analizuj pokrycie siatki z eksportu Label Studio."""

    with open(export_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sectors_found = defaultdict(int)
    all_sectors = [f"{col}{row}" for row in "123" for col in "ABC"]

    # Analizuj każdą anotację
    for task in data:
        annotations = task.get("annotations", [])
        for annotation in annotations:
            # Sprawdź pole comment w result
            for result in annotation.get("result", []):
                if result.get("from_name") == "comment":
                    comment = result.get("value", {}).get("text", [""])[0]
                    sector = parse_sector(comment)
                    if sector:
                        sectors_found[sector] += 1

    # Wyświetl wyniki
    print("\n" + "=" * 50)
    print("🗺️  ANALIZA POKRYCIA SIATKI 3x3")
    print("=" * 50 + "\n")

    print("     A          B          C")
    print("   ┌──────────┬──────────┬──────────┐")

    for row in "123":
        print(f" {row} │", end="")
        for col in "ABC":
            sector = f"{col}{row}"
            count = sectors_found.get(sector, 0)

            if count > 0:
                status = f"[✓] {count:2d}  "
            else:
                status = "[ ]      "

            print(f" {status}│", end="")
        print()

        if row != "3":
            print("   ├──────────┼──────────┼──────────┤")

    print("   └──────────┴──────────┴──────────┘\n")

    # Statystyki
    covered = len(sectors_found)
    total = 9
    percentage = (covered / total) * 100

    print(f"📊 Pokrycie: {covered}/{total} sektorów ({percentage:.1f}%)")
    print(f"📝 Całkowita liczba oznaczonych anotacji: {sum(sectors_found.values())}")

    # Brakujące sektory
    missing = [s for s in all_sectors if s not in sectors_found]
    if missing:
        print(f"\n⚠️  Brakujące sektory: {', '.join(missing)}")
    else:
        print("\n✅ Wszystkie sektory pokryte!")

    print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_grid_coverage.py <export.json>")
        sys.exit(1)

    export_path = sys.argv[1]
    analyze_coverage(export_path)
