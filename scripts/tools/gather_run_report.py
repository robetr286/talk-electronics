#!/usr/bin/env python3
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: gather_run_report.py <run_dir>")
    sys.exit(1)

run_dir = Path(sys.argv[1])
if not run_dir.exists():
    print("Run dir not found:", run_dir)
    sys.exit(1)

# files we want
files = {
    "results": run_dir / "results.csv",
    "conf": run_dir / "confusion_matrix.png",
    "val": run_dir / "val_batch0_pred.jpg",
}

md = []
md.append(f"### Report: {run_dir.name}\n")
if files["results"].exists():
    # take last line or summary
    with files["results"].open("r", encoding="utf-8") as f:
        lines = f.read().strip().splitlines()
    if lines:
        md.append("Key results (last epoch):")
        md.append("\n")
        code_block = "```\n" + "\n".join(lines[-3:]) + "\n```\n"
        md.append(code_block)

if files["conf"].exists():
    md.append(f'![confusion]({files["conf"].as_posix()})\n')
else:
    md.append("confusion_matrix not found\n")

out = "\n".join(md)
print(out)
# append to qa_log.md under a new subsection
qa = Path("qa_log.md")
text = qa.read_text(encoding="utf-8")
text = text.rstrip() + "\n\n" + out
qa.write_text(text, encoding="utf-8")
print("Appended report to qa_log.md")
