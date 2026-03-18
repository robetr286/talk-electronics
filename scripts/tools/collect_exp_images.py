#!/usr/bin/env python3
from pathlib import Path

dirs = [Path("runs/segment/exp_reduced"), Path("runs/segment/exp_augmented_real"), Path("runs/segment/exp_mix_small")]
md_lines = []
for d in dirs:
    name = d.name
    md_lines.append(f"- **{name}**")
    for img in ["val_batch0_pred.jpg", "confusion_matrix.png"]:
        p = d / img
        if p.exists():
            md_lines.append(f"  - ![{name} {img}]({p.as_posix()})")
        else:
            md_lines.append(f"  - {img} (plik nie znaleziony: {p.as_posix()})")

out = "\n".join(md_lines)
print(out)

# write to file for manual use
Path("debug/qa_report_images.md").parent.mkdir(exist_ok=True)
Path("debug/qa_report_images.md").write_text(out, encoding="utf-8")
print("\nWynik zapisany w debug/qa_report_images.md")
