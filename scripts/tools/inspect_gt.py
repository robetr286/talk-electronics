import json

c = "data/yolo_dataset/mix_small/coco_annotations.json"
with open(c, "r", encoding="utf-8") as f:
    coco = json.load(f)
imgs = coco["images"]
print(imgs[0])
anns = [a for a in coco["annotations"] if a["image_id"] == 1]
print("n anns", len(anns))
print(anns[:3])
