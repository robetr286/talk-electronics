#!/usr/bin/env python3
"""Generate sample OCR evaluation JSONs and placeholder PNGs for CI tests.

Usage:
  python scripts/generate_sample_ocr_ci.py --out-dir ocr_eval --count 20

The script writes `count` files into `{out_dir}/ci`:
- `sample_{i}.json` with a minimal standardized example
- `sample_{i}.png` a tiny 1x1 PNG placeholder
"""
import argparse
import base64
import json
from pathlib import Path

# 1x1 transparent PNG
_BASE64_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAAWgmWQ0AAAAASUVORK5CYII="


def make_sample(i: int) -> dict:
    return {
        "id": f"sample_{i}",
        "source": "generated",
        "original": f"sample_{i}.json",
        "components": [{"id": "c1", "label": f"R{i}", "value": "1K", "bbox": [1, 2, 3, 4], "raw": {}}],
    }


def write_samples(out_dir: Path, count: int):
    ci = out_dir / "ci"
    ci.mkdir(parents=True, exist_ok=True)

    for i in range(1, count + 1):
        j = make_sample(i)
        jpath = ci / f"sample_{i}.json"
        jpath.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf8")
        img_path = ci / f"sample_{i}.png"
        img_path.write_bytes(base64.b64decode(_BASE64_PNG))

    print(f"Wrote {count} samples into {ci}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", type=Path, default=Path("ocr_eval"))
    p.add_argument("--count", type=int, default=20)
    args = p.parse_args()
    write_samples(args.out_dir, args.count)
