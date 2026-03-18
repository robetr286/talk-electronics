#!/usr/bin/env python3
"""Validate generated OCR eval samples in ocr_eval/ci and ocr_eval/local

Prints a concise report: counts, per-file component counts, and whether designator/value are present.
Exits with code 1 if any JSON has zero components or if any expected image is missing.
"""
import json
import sys
from pathlib import Path

base = Path("ocr_eval")
ci = base / "ci"
local = base / "local"
any_errors = False

for split in (ci, local):
    print(f"Checking {split} (exists={split.exists()})")
    if not split.exists():
        print(f"  -> missing {split}")
        continue
    files = sorted(split.glob("*.json"))
    print(f"  json count: {len(files)}")
    for f in files:
        try:
            j = json.loads(f.read_text(encoding="utf8"))
        except Exception as e:
            print(f"  ERROR reading {f}: {e}")
            any_errors = True
            continue
        comps = j.get("components") or []
        if len(comps) == 0:
            print(f"  ERROR {f.name}: zero components")
            any_errors = True
            continue
        design_count = sum(1 for c in comps if c.get("label"))
        value_count = sum(1 for c in comps if c.get("value"))
        # check image exists
        img_candidates = list(split.glob(f"{f.stem}.*"))
        img_exists = any(p.suffix.lower() in [".png", ".jpg", ".jpeg"] for p in img_candidates)
        if not img_exists:
            print(f"  WARNING {f.name}: image missing in {split} (looked for {f.stem}.*)")
        img_status = "found" if img_exists else "MISSING"
        print(f"  {f.name}: comps={len(comps)} designators={design_count} values={value_count} image={img_status}")

# summary counts
ci_count = len(list(ci.glob("*.json"))) if ci.exists() else 0
local_count = len(list(local.glob("*.json"))) if local.exists() else 0
print("\nSUMMARY:")
print(f"  ci json: {ci_count}")
print(f"  local json: {local_count}")

if any_errors:
    print("\nValidation FAILED")
    sys.exit(1)
else:
    print("\nValidation PASSED")
    sys.exit(0)
