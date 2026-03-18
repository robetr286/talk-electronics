"""Synchronizuje manifest patchy junction na podstawie struktury katalogów."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

DEFAULT_LABELS = ("dot_present", "no_dot", "unknown")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aktualizuje manifest patchy zgodnie z katalogami.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/sample_benchmark/junction_patches"),
        help="Katalog zawierający podfoldery etykiet.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Ścieżka do manifest.csv (domyślnie data-root/manifest.csv).",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Zachowaj kopię starego manifestu (manifest.csv.bak).",
    )
    return parser.parse_args()


def scan_directories(data_root: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for label in DEFAULT_LABELS:
        folder = data_root / label
        if not folder.exists():
            continue
        for file in folder.glob("*.png"):
            mapping[file.name] = label
    return mapping


def read_manifest(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(row)
    return rows


def write_manifest(path: Path, rows: List[Dict[str, str]]) -> None:
    fieldnames = [
        "filename",
        "label",
        "node_id",
        "degree",
        "position_row",
        "position_col",
        "timestamp",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def main() -> None:
    args = parse_args()
    manifest = args.manifest or args.data_root / "manifest.csv"
    mapping = scan_directories(args.data_root)
    rows = read_manifest(manifest)
    updated = 0
    missing = set(mapping.keys())
    for row in rows:
        filename = row.get("filename")
        if not filename:
            continue
        if filename in mapping:
            if row.get("label") != mapping[filename]:
                row["label"] = mapping[filename]
                updated += 1
            missing.discard(filename)
    for filename in sorted(missing):
        rows.append(
            {
                "filename": filename,
                "label": mapping[filename],
                "node_id": "",
                "degree": "",
                "position_row": "",
                "position_col": "",
                "timestamp": "",
            }
        )
    if args.backup and manifest.exists():
        backup_path = manifest.with_suffix(manifest.suffix + ".bak")
        backup_path.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
    write_manifest(manifest, rows)
    print(f"Zaktualizowano manifest {manifest}. Zmieniono {updated} wpisów, dodano {len(missing)}.")


if __name__ == "__main__":
    main()
