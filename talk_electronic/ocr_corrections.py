"""Utility for aggregating user OCR corrections.

The directory ``reports/textract/corrections`` contains one JSON file per
interaction, each with fields ``request_id`` and ``corrections`` (list of
objects with 'component'/'value').  We want to be able to read all of them,
count total corrections, list most frequently corrected components, etc.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List


def load_all_corrections(directory: Path = Path("reports/textract/corrections")) -> List[Dict]:
    files = []
    if not directory.exists():
        return files
    for p in directory.glob("*_corrections.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            files.append(data)
        except Exception:
            continue
    return files


def summarize_corrections(directory: Path = Path("reports/textract/corrections")) -> Dict[str, any]:
    """Return a summary dictionary containing:
    - total_files: number of correction files
    - total_entries: total number of corrected tokens across all files
    - component_counts: Counter mapping component names to how often they
      appear in corrections
    - value_counts: Counter mapping corrected values (string) to frequency
    """
    all_corr = load_all_corrections(directory)
    comp_ctr = Counter()
    val_ctr = Counter()
    total = 0
    for entry in all_corr:
        for corr in entry.get("corrections", []):
            comp = corr.get("component", "").strip()
            val = corr.get("value", "").strip()
            if comp or val:
                total += 1
                if comp:
                    comp_ctr[comp] += 1
                if val:
                    val_ctr[val] += 1
    return {
        "total_files": len(all_corr),
        "total_entries": total,
        "component_counts": comp_ctr,
        "value_counts": val_ctr,
    }


if __name__ == "__main__":
    import pprint

    print("Scanning OCR corrections...")
    summary = summarize_corrections()
    pprint.pprint(summary)
