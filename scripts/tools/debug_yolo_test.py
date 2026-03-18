import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))
import numpy as np
from PIL import Image

from talk_electronic.services.symbol_detection.yolov8 import YoloV8SegDetector

img = Image.open("data/yolo_dataset/mix_small/images/schemat_page19_wycinek-prostokat_2025-12-01_19-24-30.png").convert(
    "RGB"
)
arr = np.array(img)
d = YoloV8SegDetector()
res = d.detect(arr, return_summary=False)
print("n", len(res.detections))
for det in res.detections[:10]:
    print(det.score, det.metadata.get("class_id"), det.box.as_tuple(), list(det.metadata.keys())[:3])
