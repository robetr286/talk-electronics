#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--n", type=int, default=8)
    args = p.parse_args()
    inp = Path(args.input)
    out = Path(args.output)
    coco = json.loads(inp.read_text(encoding="utf-8"))
    imgs = coco["images"][: args.n]
    ids = {im["id"] for im in imgs}
    anns = [a for a in coco["annotations"] if a["image_id"] in ids]
    new = {"images": imgs, "annotations": anns, "categories": coco.get("categories", [])}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(new, indent=2), encoding="utf-8")
    print("wrote", out, "images", len(imgs), "anns", len(anns))


if __name__ == "__main__":
    main()
