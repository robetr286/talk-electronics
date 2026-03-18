import json

p = "runs/benchmarks/preds_yolo.json"
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)
keys = list(data.keys())[:3]
print("sample images", keys)
for k in keys:
    print("img", k, "n", len(data[k]))
    print(data[k][:3])
