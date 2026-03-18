import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "export_labelstudio_to_ignore",
    Path(__file__).resolve().parents[2] / "scripts" / "export_labelstudio_to_ignore.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore
convert_labelstudio_to_ignore = mod.convert_labelstudio_to_ignore


def test_convert_labelstudio_to_ignore(tmp_path):
    # Prepare a small fake Label Studio export with one task containing a polygon and a rectangle
    task = {
        "data": {"image": "test_img.png", "width": 200, "height": 100},
        "annotations": [
            {
                "result": [
                    {
                        "type": "polygonlabels",
                        "value": {
                            "points": [[10, 10], [20, 10], [20, 20], [10, 20]],
                            "polygonlabels": ["ignore_region"],
                        },
                    },
                    {
                        "type": "rectanglelabels",
                        "value": {
                            "x": 50,
                            "y": 30,
                            "width": 20,
                            "height": 10,
                            "rotation": 0,
                            "rectanglelabels": ["ignore_region"],
                        },
                    },
                ]
            }
        ],
    }

    outdir = tmp_path / "out"
    convert_labelstudio_to_ignore([task], outdir, images_dir=None, labels=["ignore_region"], make_masks=False)

    # Expect a file 'test_img.json' created with ignore_regions
    out_file = outdir / "test_img.json"
    assert out_file.exists()

    with open(out_file, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    assert data["image"] == "test_img.png"
    assert "ignore_regions" in data
    assert len(data["ignore_regions"]) == 2
