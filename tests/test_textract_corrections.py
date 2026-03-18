from __future__ import annotations

import json
from pathlib import Path


def test_save_corrections_endpoint(client, tmp_path, monkeypatch):
    # ensure directory exists and is empty
    corr_dir = Path("reports/textract/corrections").resolve()
    if corr_dir.exists():
        for f in corr_dir.iterdir():
            f.unlink()

    payload = {"request_id": "abc123", "corrections": [{"component": "R1", "value": "22K"}]}
    resp = client.post("/ocr/textract/corrections", data=json.dumps(payload), content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("status") == "ok"
    path = Path(data.get("path"))
    assert path.exists()
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == payload

    # now create a fake post file (with image) and resend different corrections to verify merging
    post_dir = Path("reports/textract/post").resolve()
    post_dir.mkdir(parents=True, exist_ok=True)
    # create a minimal valid PNG image so overlay regen can open it
    from PIL import Image

    dummy_img = tmp_path / "foo.png"
    Image.new("RGB", (10, 10), color="white").save(dummy_img)
    sample_post = {
        "request_id": "abc123",
        "tokens": [{"text": "R1"}],
        "pairs": [{"component": "R1", "value": "10K"}],
        "image": str(dummy_img),
    }
    post_path = post_dir / "abc123_test_post.json"
    post_path.write_text(json.dumps(sample_post, ensure_ascii=False), encoding="utf-8")
    (post_dir / "overlays").mkdir(exist_ok=True)

    payload2 = {
        "request_id": "abc123",
        "corrections": [{"component": "R1", "value": "22K"}, {"component": "C1", "value": "100nF"}],
    }
    resp2 = client.post("/ocr/textract/corrections", data=json.dumps(payload2), content_type="application/json")
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    # merged key should be present and contain updated pairs
    merged = data2.get("merged")
    assert merged is not None
    assert any(p.get("value") == "22K" for p in merged.get("pairs", []))
    assert any(p.get("component") == "C1" for p in merged.get("pairs", []))
    overlay_path = Path(merged.get("overlay", ""))
    assert overlay_path.exists()

    # create fake segmentation file tagged with req_id to exercise netlist regen
    from talk_electronic.services.line_detection import LineDetectionResult

    # avoid application context by reading config from test client
    proc = client.application.config.get("PROCESSED_FOLDER", "processed")
    seg_dir = Path(proc) / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    from talk_electronic.services.line_detection import LineNode, LineSegment

    # create minimal detection with one node and one segment
    det = LineDetectionResult(
        lines=[LineSegment(id="s1", start=(0, 0), end=(1, 0), length=1.0, angle_deg=0.0)],
        nodes=[LineNode(id="n1", position=(0, 0), attached_segments=["s1"])],
        metadata={},
    )
    seg_file = seg_dir / f"lines_{payload['request_id']}_dummy.json"
    seg_file.write_text(json.dumps(det.to_dict()), encoding="utf-8")

    resp3 = client.post("/ocr/textract/corrections", data=json.dumps(payload2), content_type="application/json")
    data3 = resp3.get_json()
    merged3 = data3.get("merged")
    assert merged3 is not None
    assert "netlist" in merged3
    assert isinstance(merged3["netlist"].get("id"), str)
