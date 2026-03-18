"""Prosty monitor wynikow treningu YOLO zapisanych w results.csv."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


def load_rows(csv_path: Path) -> List[Dict[str, str]]:
    """Zwraca wszystkie wiersze z pliku CSV lub pusta liste, gdy plik nie istnieje."""
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def safe_float(value: Optional[str], default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except ValueError:
        return default


def infer_total_epochs(run_dir: Path) -> Optional[int]:
    """Probuje wyczytac parametr epochs z args.yaml (najpierw PyYAML, potem prosty parser)."""
    args_path = run_dir / "args.yaml"
    if not args_path.exists():
        return None

    try:
        import yaml  # type: ignore
    except Exception:  # pragma: no cover - PyYAML moze byc niedostepny
        yaml = None

    if yaml is not None:
        try:
            data = yaml.safe_load(args_path.read_text(encoding="utf-8"))
        except Exception:
            data = None
        if isinstance(data, dict) and "epochs" in data:
            try:
                return int(float(data["epochs"]))
            except (TypeError, ValueError):
                pass

    for line in args_path.read_text(encoding="utf-8").splitlines():
        if line.strip().lower().startswith("epochs:"):
            value = line.split(":", 1)[1].strip()
            try:
                return int(float(value))
            except ValueError:
                return None
    return None


def format_eta(epoch: int, total_epochs: Optional[int], elapsed: float) -> str:
    if not total_epochs or epoch <= 0 or elapsed <= 0:
        return "ETA: ?"
    avg = elapsed / epoch
    remaining = max(total_epochs - epoch, 0) * avg
    return f"ETA: {timedelta(seconds=int(remaining))}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitoruje postep treningu YOLO z pliku results.csv")
    parser.add_argument("run_dir", nargs="?", default="runs/segment/train2", help="Katalog z wynikami treningu")
    parser.add_argument("--interval", type=float, default=30.0, help="Czas miedzy odczytami w sekundach")
    parser.add_argument("--once", action="store_true", help="Pojedynczy odczyt zamiast petli")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    csv_path = run_dir / "results.csv"
    total_epochs = infer_total_epochs(run_dir)
    last_epoch = None
    last_elapsed = 0.0

    if args.once and not csv_path.exists():
        print(f"Brak pliku: {csv_path}", file=sys.stderr)
        sys.exit(1)

    while True:
        rows = load_rows(csv_path)
        if rows:
            latest = rows[-1]
            epoch = int(safe_float(latest.get("epoch"), -1))
            elapsed = safe_float(latest.get("time"), 0.0)
            train_box = safe_float(latest.get("train/box_loss"))
            train_seg = safe_float(latest.get("train/seg_loss"))
            val_box = safe_float(latest.get("val/box_loss"))
            val_seg = safe_float(latest.get("val/seg_loss"))
            map50 = safe_float(latest.get("metrics/mAP50(B)"))
            mask_map50 = safe_float(latest.get("metrics/mAP50(M)"))

            if epoch != last_epoch:
                timestamp = datetime.now().strftime("%H:%M:%S")
                eta = format_eta(epoch, total_epochs, elapsed)
                progress = f"{epoch}/{total_epochs}" if total_epochs else str(epoch)
                delta = elapsed - last_elapsed
                delta_str = f"dT {delta:.1f}s" if delta > 0 else "dT ?"
                print(
                    f"[{timestamp}] ep {progress} | train box {train_box:.3f} seg {train_seg:.3f} | "
                    f"val box {val_box:.3f} seg {val_seg:.3f} | det mAP50 {map50:.3f} | seg mAP50 {mask_map50:.3f} | "
                    f"{delta_str} | {eta}",
                    flush=True,
                )
                last_epoch = epoch
                last_elapsed = elapsed if elapsed > 0 else last_elapsed
        else:
            print(f"[{datetime.now():%H:%M:%S}] Oczekiwanie na {csv_path}...", flush=True)

        if args.once:
            break
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitoring przerwany przez uzytkownika.")
            break


if __name__ == "__main__":
    main()
