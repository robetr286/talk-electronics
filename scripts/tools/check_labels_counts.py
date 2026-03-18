import re
import sys
from pathlib import Path

data_yaml = Path("data/yolo_dataset/mix_small/dataset.yaml")
labels_dir = Path("data/yolo_dataset/mix_small/labels")
if not data_yaml.exists():
    print("dataset.yaml not found")
    sys.exit(1)

# parse names count
text = data_yaml.read_text(encoding="utf-8")
match = re.search(r"names:\n((?:\s+\d+:.*\n)+)", text)
if match:
    names_block = match.group(1)
    names = [line.strip() for line in names_block.strip().splitlines()]
    nc = len(names)
else:
    names = []
    nc = 0

max_label = -1
count = 0
for p in labels_dir.glob("*.txt"):
    s = p.read_text(encoding="utf-8").strip()
    if not s:
        continue
    for line in s.splitlines():
        parts = line.split()
        try:
            cls = int(parts[0])
            if cls > max_label:
                max_label = cls
            count += 1
        except Exception:
            continue

print(f"dataset.yaml classes: {nc}, max label found in *.txt: {max_label}, total labels: {count}")
if max_label >= nc:
    print("Mismatch detected: some label class ids >= nc. Consider updating dataset.yaml names or remapping labels.")
    sys.exit(2)
print("OK")
