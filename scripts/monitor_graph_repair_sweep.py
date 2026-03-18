"""Monitoruje przebieg comparative sweep i uruchamia następne kroki po zakończeniu.

Funkcjonalność:
- Co 10 minut zapisuje stan/procent ukończenia oraz liczbę przetworzonych obrazów.
- Po wykryciu, że oba tryby (conservative + aggressive) zakończyły i istnieją summary.json,
  uruchamia automatyczne zadania: dodanie dodatkowych testów regresyjnych i wygenerowanie
  krótkiego README/prezentacji (skrypty `add_regression_tests.py` i `generate_graph_repair_readme.py`).

Uruchomienie: python scripts/monitor_graph_repair_sweep.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Tuple

BASE = Path(__file__).resolve().parents[1] / "debug" / "graph_repair_sweep_comparative"
DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "junction_inputs"
SLEEP = 60 * 10  # 10 minutes


def count_images_in_data() -> int:
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
    total = 0
    for sub in ("small", "medium", "large", "big"):
        d = DATA_ROOT / sub
        if not d.exists():
            continue
        for _ in d.rglob("*"):
            if _.suffix.lower() in exts:
                total += 1
    return total


def count_processed(mode: str) -> int:
    p = BASE / mode
    if not p.exists():
        return 0
    # count directories per image
    return sum(1 for f in p.iterdir() if f.is_dir())


def summaries_exist() -> Tuple[bool, bool]:
    c = (BASE / "conservative" / "summary.json").exists()
    a = (BASE / "aggressive" / "summary.json").exists()
    return c, a


def load_summary(mode: str):
    p = BASE / mode / "summary.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def report_progress():
    total_images = count_images_in_data()
    if total_images == 0:
        print("No images found under data/junction_inputs/* — aborting monitor")
        return False

    processed_cons = count_processed("conservative")
    processed_aggr = count_processed("aggressive")
    expected_total = total_images * 2
    processed_total = processed_cons + processed_aggr

    percent = round(processed_total / expected_total * 100.0, 2) if expected_total else 0.0

    print(f"Progress: {processed_total}/{expected_total} images processed ({percent}%)")
    print(f"  conservative: {processed_cons}, aggressive: {processed_aggr}")

    return processed_total >= expected_total


def main():
    print("Monitor started — will report every 10 minutes")

    # fast loop to give immediate feedback until completion
    while True:
        done = report_progress()
        if done:
            print("Sweep appears complete — verifying summaries...")
            c_exists, a_exists = summaries_exist()
            if c_exists and a_exists:
                print("Found both summary.json files — proceeding to next steps")
                # trigger follow-up steps if scripts exist
                next_script_1 = Path(__file__).resolve().parents[0] / "add_more_graph_repair_tests.py"
                next_script_2 = Path(__file__).resolve().parents[0] / "generate_graph_repair_readme.py"
                if next_script_1.exists():
                    print(f"Running {next_script_1}")
                    import subprocess

                    subprocess.run(["python", str(next_script_1)], check=False)
                else:
                    print(f"Follow-up script not found: {next_script_1}")

                if next_script_2.exists():
                    print(f"Running {next_script_2}")
                    import subprocess

                    subprocess.run(["python", str(next_script_2)], check=False)
                else:
                    print(f"Follow-up script not found: {next_script_2}")

                print("Monitor exiting after follow-up steps")
                return
            else:
                print("Summaries not ready yet — waiting another 10 minutes to re-check")

        time.sleep(SLEEP)


if __name__ == "__main__":
    main()
