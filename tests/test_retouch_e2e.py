from pathlib import Path

from talk_electronic import create_app


def test_send_to_retouch_creates_buffer_with_dataurl(tmp_path):
    # create app with temporary upload folder
    upload_dir = tmp_path / "uploads"
    app = create_app({"UPLOAD_FOLDER": str(upload_dir)})
    client = app.test_client()

    # use existing test_debug.png from repository root
    repo_root = Path(__file__).resolve().parents[1]
    test_img = repo_root / "test_debug.png"
    assert test_img.exists(), "test_debug.png must exist in repository root for E2E test"

    with open(test_img, "rb") as fh:
        data = {"file": (fh, "test_debug.png")}
        resp = client.post("/processing/send-to-retouch", data=data, content_type="multipart/form-data")
    assert resp.status_code == 201
    body = resp.get_json()
    assert "entry" in body
    entry = body["entry"]

    # server should include dataUrl and url should equal dataUrl
    assert (
        "dataUrl" in entry and isinstance(entry["dataUrl"], str) and entry["dataUrl"].startswith("data:")
    ), "dataUrl present and data:"
    assert "url" in entry and entry["url"].startswith("data:"), "entry.url should be dataUrl for stable client loading"
    # serverUrl should be present and point under /uploads/
    assert (
        "serverUrl" in entry and isinstance(entry["serverUrl"], str) and entry["serverUrl"].startswith("/uploads/")
    ), "serverUrl preserved"

    # buffer GET should return the same
    resp2 = client.get("/processing/retouch-buffer")
    assert resp2.status_code == 200
    body2 = resp2.get_json()
    entry2 = body2.get("entry")
    assert entry2, "retouch buffer should contain entry"
    assert entry2["url"].startswith("data:")
    assert entry2["dataUrl"].startswith("data:")
    assert entry2.get("serverUrl", "").startswith("/uploads/")
