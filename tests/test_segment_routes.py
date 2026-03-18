from pathlib import Path


def test_segment_with_roi(client):
    payload = {
        "imageUrl": "/static/fixtures/line-segmentation/cross_gray.png",
        "roi": {"x": 10, "y": 10, "width": 50, "height": 50},
    }
    resp = client.post("/api/segment/lines", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "result" in data
    metadata = data["result"].get("metadata") or {}
    assert "roi" in metadata
    roi = metadata["roi"]
    assert roi.get("x") == 10 and roi.get("y") == 10
    assert roi.get("width") == 50 and roi.get("height") == 50


def test_segment_with_invalid_roi_ignored(client):
    # ROI outside bounds -> should be ignored but still return 200
    payload = {
        "imageUrl": "/static/fixtures/line-segmentation/cross_gray.png",
        "roi": {"x": 99999, "y": 99999, "width": 100, "height": 100},
    }
    resp = client.post("/api/segment/lines", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    metadata = data["result"].get("metadata") or {}
    # No roi attached when invalid
    assert "roi" not in metadata


def test_segment_with_data_url_image_and_roi(client):
    import base64

    fixture_path = Path("static/fixtures/line-segmentation/cross_gray.png")
    # Read fixture bytes and build a data URL
    full_path = Path(__file__).resolve().parents[1] / fixture_path
    data = full_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"

    payload = {
        "imageUrl": data_url,
        "roi": {"x": 10, "y": 10, "width": 50, "height": 50},
    }
    resp = client.post("/api/segment/lines", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    metadata = data["result"].get("metadata") or {}
    assert "roi" in metadata
    roi = metadata["roi"]
    assert roi.get("x") == 10 and roi.get("y") == 10
    assert roi.get("width") == 50 and roi.get("height") == 50
