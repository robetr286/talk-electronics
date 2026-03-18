from __future__ import annotations

from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF
import pytest

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency
    Image = None


def _make_pdf_bytes() -> bytes:
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Hello, PDF!")
        return document.tobytes()
    finally:
        document.close()


def test_upload_endpoint_stores_pdf_and_renders_first_page(app, client) -> None:
    upload_folder: Path = app.config["UPLOAD_FOLDER"]

    pdf_bytes = _make_pdf_bytes()
    response = client.post(
        "/upload",
        data={"file": (BytesIO(pdf_bytes), "sample.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["token"]
    assert payload["total_pages"] == 1
    assert payload["image_url"].startswith("/uploads/")

    stored_pdf = upload_folder / f"{payload['token']}.pdf"
    rendered_png = upload_folder / payload["image_url"].split("/uploads/")[-1]

    assert stored_pdf.exists()
    assert rendered_png.exists()


@pytest.mark.skipif(Image is None, reason="Pillow nie jest zainstalowany")
def test_upload_endpoint_accepts_png_image(app, client) -> None:
    upload_folder: Path = app.config["UPLOAD_FOLDER"]

    buffer = BytesIO()
    image = Image.new("RGB", (120, 80), color=(0, 128, 255))
    image.save(buffer, format="PNG", dpi=(300, 300))
    buffer.seek(0)

    response = client.post(
        "/upload",
        data={"file": (buffer, "sample.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["token"]
    assert payload["total_pages"] == 1
    assert payload["image_url"].startswith("/uploads/")

    stored_source = upload_folder / f"{payload['token']}_source.png"
    rendered_png = upload_folder / payload["image_url"].split("/uploads/")[-1]

    assert stored_source.exists()
    assert rendered_png.exists()
    assert payload.get("image_dpi") == 300
