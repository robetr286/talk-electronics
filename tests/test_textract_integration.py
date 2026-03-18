from __future__ import annotations

import json
from pathlib import Path

import types

import pytest


@pytest.fixture(autouse=True)
def patch_textract(monkeypatch):
    # stub Textract client to avoid boto3 credential issues on CI
    monkeypatch.setattr(
        "talk_electronic.routes.textract._textract_client",
        lambda: types.SimpleNamespace(analyze_document=lambda **kw: {"Blocks": []}),
    )
    # stub Textract call to return empty blocks
    monkeypatch.setattr(
        "talk_electronic.routes.textract._run_textract_on_image",
        lambda client, image_path: {"Blocks": []},
    )
    # ensure filter_tokens returns at least one token so pairs are computed
    monkeypatch.setattr(
        "talk_electronic.routes.textract._filter_tokens",
        lambda blocks, w, h, min_conf=40.0: [{"text": "R1", "category": "component", "Confidence": 99.0}],
    )
    # stub postprocessing pairing to a fixed value
    monkeypatch.setattr(
        "talk_electronic.routes.textract._pair_components_to_values",
        lambda tokens: [{"component": "R1", "value": "10K"}],
    )
    yield


def test_end_to_end_flow(client, tmp_path):
    # prepare a small valid PNG image
    from PIL import Image

    img = tmp_path / "schem.png"
    Image.new("RGB", (10, 10), color="white").save(img)

    # run ocr endpoint
    with img.open("rb") as f:
        resp = client.post("/ocr/textract", data={"file": (f, "schem.png")})
    assert resp.status_code == 200
    data = resp.get_json()
    req_id = data.get("request_id")
    assert req_id
    # pairs should contain stubbed result
    assert data.get("pairs") == [{"component": "R1", "value": "10K"}]

    # now apply a correction and expect merged output including overlay
    payload = {"request_id": req_id, "corrections": [{"component": "R1", "value": "22K"}]}
    resp2 = client.post("/ocr/textract/corrections", data=json.dumps(payload), content_type="application/json")
    assert resp2.status_code == 200
    merged = resp2.get_json().get("merged")
    assert merged
    assert any(p.get("value") == "22K" for p in merged.get("pairs", []))
    overlay_path = Path(merged.get("overlay", ""))
    assert overlay_path.exists()

    # simulate segmentation and request a second correction to trigger netlist
    from talk_electronic.services.line_detection import LineDetectionResult

    # determine processed folder from application config
    proc = client.application.config.get("PROCESSED_FOLDER", "processed")
    seg_dir = Path(proc) / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    det = LineDetectionResult(lines=[], nodes=[], metadata={})
    seg_file = seg_dir / f"lines_{req_id}_integr.json"
    seg_file.write_text(json.dumps(det.to_dict()), encoding="utf-8")

    resp3 = client.post("/ocr/textract/corrections", data=json.dumps(payload), content_type="application/json")
    merged3 = resp3.get_json().get("merged")
    assert merged3 and "netlist" in merged3
    assert isinstance(merged3["netlist"].get("id"), str)
