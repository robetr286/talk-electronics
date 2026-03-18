"""Create a zipped inspection package for the comparative sweep.

Selects representative images: timeouts, longest-running tasks, and images
with largest differences in 'saved' counts between conservative/aggressive
(parsed from stdout). Copies the per-image debug folders into a tidy
inspection directory and creates an index.html for manual browsing.

Usage: python scripts/generate_graph_repair_inspection_package.py
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


def parse_saved(stdout: str) -> int:
    m = re.search(r"saved=(\d+)", stdout or "")
    if m:
        return int(m.group(1))
    return 0


def load_summary(path: Path):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    repo = Path(__file__).resolve().parents[1]
    base = repo / "debug" / "graph_repair_sweep_comparative"
    cons = load_summary(base / "conservative" / "summary.json")
    aggr = load_summary(base / "aggressive" / "summary.json")

    # index by image path
    c_map = {r["image"]: r for r in cons}
    a_map = {r["image"]: r for r in aggr}

    images = sorted(set(list(c_map.keys()) + list(a_map.keys())))

    # categories
    timeouts = [img for img in images if c_map.get(img, {}).get("timeout") or a_map.get(img, {}).get("timeout")]

    # longest running (non-timeout) union of both
    elapsed = []
    for img in images:
        vals = []
        if not c_map.get(img, {}).get("timeout") and "elapsed_s" in c_map.get(img, {}):
            vals.append(c_map[img]["elapsed_s"])
        if not a_map.get(img, {}).get("timeout") and "elapsed_s" in a_map.get(img, {}):
            vals.append(a_map[img]["elapsed_s"])
        if vals:
            elapsed.append((max(vals), img))
    elapsed_sorted = [img for _, img in sorted(elapsed, reverse=True)[:6]]

    # largest saved-count differences
    diffs = []
    for img in images:
        s1 = parse_saved(c_map.get(img, {}).get("stdout", ""))
        s2 = parse_saved(a_map.get(img, {}).get("stdout", ""))
        diffs.append((abs(s1 - s2), img, s1, s2))
    diffs_sorted = [img for _, img, _, _ in sorted(diffs, reverse=True)[:8]]

    # pick representatives: union of the above groups plus a few random small ones
    rep_set = set(timeouts) | set(elapsed_sorted) | set(diffs_sorted)
    rep_list = sorted(rep_set)[:16]

    out_dir = repo / "debug" / "graph_repair_inspection"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    # copy debug folders for each representative image and mode
    mode_dirs = {"conservative": base / "conservative", "aggressive": base / "aggressive"}

    index_rows = []
    for mode, src_root in mode_dirs.items():
        for img in rep_list:
            stem = Path(img).stem
            src = src_root / stem
            if not src.exists():
                continue
            dst = out_dir / mode / stem
            shutil.copytree(src, dst)
            index_rows.append((mode, stem, dst))

    # write index.html
    html_lines = [
        '<html><head><meta charset="utf-8"><title>Graph-repair comparative inspection</title></head><body>',
        "<h1>Graph-repair — comparative inspection</h1>",
        "<p>Representative examples (timeouts, long-runs, largest saved-count diffs)</p>",
        "<ul>",
    ]
    for mode, stem, dst in index_rows:
        rel = Path(mode) / stem
        html_lines.append(f'<li><strong>{mode}</strong> — <a href="{rel}">{stem}</a></li>')
    html_lines.extend(["</ul>", "</body></html>"])

    (out_dir / "index.html").write_text("\n".join(html_lines), encoding="utf-8")

    # create zip
    zip_path = repo / "debug" / "graph_repair_inspection" / "graph_repair_comparative_inspection.zip"
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=out_dir)

    print("Created inspection package:", zip_path)


if __name__ == "__main__":
    main()
