"""Small follow-up sweep that runs export_junction_patches on a few chosen images
using current default graph-repair settings. Writes debug output into debug/graph_repair_followup/.

Use: python scripts/mini_graph_repair_followup.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path

PY = sys.executable
SCRIPT = Path("scripts/export_junction_patches.py")
images = [
    "data/junction_inputs/medium/schemat_page23_wycinek-prostokat_2025-12-01_19-27-13.png",
    "data/junction_inputs/small/schemat_page25_wycinek-prostokat_2025-12-01_19-28-13.png",
    "data/junction_inputs/small/schemat_page26_wycinek-prostokat_2025-12-01_19-28-40.png",
    "data/junction_inputs/small/schemat_page27_wycinek-prostokat_2025-12-01_19-29-16.png",
    "data/junction_inputs/small/schemat_page28_wycinek-prostokat_2025-12-01_19-29-45.png",
    "data/junction_inputs/small/schemat_page28_wycinek-prostokat_2025-12-01_19-30-02.png",
]

out_base = Path("debug/graph_repair_followup")
out_base.mkdir(parents=True, exist_ok=True)

results = []
for img in images:
    stem = Path(img).stem
    outdir = out_base / stem
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [PY, str(SCRIPT), img, "--debug-dir", str(outdir), "--enable-graph-repair"]
    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - start
        results.append(
            {
                "image": img,
                "elapsed": elapsed,
                "timeout": False,
                "returncode": proc.returncode,
                "stdout_lines": proc.stdout.strip().splitlines()[-5:],
                "stderr_lines": proc.stderr.strip().splitlines()[:5],
            }
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.time() - start
        results.append({"image": img, "elapsed": elapsed, "timeout": True, "error": str(exc)})

with open(out_base / "mini_sweep_summary.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("Wrote", out_base / "mini_sweep_summary.json")
