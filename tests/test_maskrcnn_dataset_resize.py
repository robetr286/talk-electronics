import json
from pathlib import Path

import torch
from torchvision import transforms as T

from scripts.experiments.run_maskrcnn_poc import CocoLikeDataset


def test_boxes_and_masks_scaled_on_resize(tmp_path: Path):
    # create temp image and COCO json
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    img_path = images_dir / "test.png"
    # create simple blank image
    from PIL import Image

    orig_w, orig_h = 1000, 500
    Image.new("RGB", (orig_w, orig_h), (255, 255, 255)).save(img_path)

    # one annotation: bbox x=100,y=50,w=200,h=100 -> x1=100,y1=50,x2=300,y2=150
    coco = {
        "images": [{"id": 1, "file_name": img_path.name, "width": orig_w, "height": orig_h}],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 1,
                "bbox": [100, 50, 200, 100],
                "area": 200 * 100,
                # simple rectangle polygon
                "segmentation": [[100, 50, 300, 50, 300, 150, 100, 150]],
            }
        ],
        "categories": [{"id": 1, "name": "sym"}],
    }

    coco_json = tmp_path / "coco.json"
    with open(coco_json, "w", encoding="utf8") as f:
        json.dump(coco, f)

    transforms = T.Compose([T.Resize(250), T.ToTensor()])
    ds = CocoLikeDataset(coco_json, images_dir, transforms=transforms)
    img, target = ds[0]
    # resized dims
    new_h = 250
    new_w = int(orig_w * new_h / orig_h)
    assert img.shape[1] == new_h and img.shape[2] == new_w

    boxes = target["boxes"]
    assert boxes.shape[0] == 1
    # expected scaled coords: multiply by 0.5
    expected = torch.tensor(
        [
            100.0 * (new_w / orig_w),
            50.0 * (new_h / orig_h),
            300.0 * (new_w / orig_w),
            150.0 * (new_h / orig_h),
        ]
    )
    assert torch.allclose(boxes[0], expected, atol=1e-4)
