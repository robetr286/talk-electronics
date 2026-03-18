from __future__ import annotations

import pytest

import talk_electronic.routes.textract as textract


@pytest.mark.skipif(textract.fitz is None, reason="PyMuPDF (fitz) not available")
def test_textract_warns_when_pdf_exceeds_sync_limit(monkeypatch, client, tmp_path):
    class DummyTextractClient:
        def analyze_document(self, *_, **__):
            return {"Blocks": []}

    monkeypatch.setattr(textract, "_textract_client", lambda: DummyTextractClient())

    client.application.config.update(
        {
            "TEXTRACT_MAX_PDF_PAGES": 2,
            "TEXTRACT_DEFAULT_RASTER_DPI": 150,
            "TEXTRACT_MAX_RASTER_DPI": 200,
        }
    )

    pdf_path = tmp_path / "big.pdf"
    doc = textract.fitz.open()
    for _ in range(4):
        doc.new_page()
    doc.save(pdf_path)

    with pdf_path.open("rb") as f:
        resp = client.post("/ocr/textract", data={"file": (f, "big.pdf")}, content_type="multipart/form-data")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload is not None
    warnings = payload.get("warnings", [])
    assert any("pełen zakres wymaga trybu async Textract" in w for w in warnings)


@pytest.mark.skipif(textract.fitz is None, reason="PyMuPDF (fitz) not available")
def test_textract_warns_when_pages_param_exceeds_limit(monkeypatch, client, tmp_path):
    class DummyTextractClient:
        def analyze_document(self, *_, **__):
            return {"Blocks": []}

    monkeypatch.setattr(textract, "_textract_client", lambda: DummyTextractClient())

    client.application.config.update(
        {
            "TEXTRACT_MAX_PDF_PAGES": 2,
            "TEXTRACT_DEFAULT_RASTER_DPI": 150,
            "TEXTRACT_MAX_RASTER_DPI": 200,
        }
    )

    pdf_path = tmp_path / "big.pdf"
    doc = textract.fitz.open()
    for _ in range(3):
        doc.new_page()
    doc.save(pdf_path)

    with pdf_path.open("rb") as f:
        resp = client.post(
            "/ocr/textract",
            data={"file": (f, "big.pdf"), "pages": "1,2,3"},
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload is not None
    warnings = payload.get("warnings", [])
    assert any("przycięto liczbę stron do" in w for w in warnings)
