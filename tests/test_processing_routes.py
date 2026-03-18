import base64
import io

from PIL import Image


def _make_data_url(size=(16, 16), color=(255, 255, 255)) -> str:
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def test_deskew_accepts_data_url(client):
    data_url = _make_data_url((32, 32), (128, 128, 128))

    resp = client.post(
        "/processing/deskew",
        json={"imageData": data_url, "manualAngle": 1.5},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    payload = resp.get_json()
    assert payload.get("success") is True
    assert "previewUrl" in payload and isinstance(payload["previewUrl"], str)
