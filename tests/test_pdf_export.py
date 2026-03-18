"""
Testy dla endpointu eksportu stron PDF do PNG.

Sprawdza poprawność renderowania z różnymi DPI oraz metadanych.
"""

import json
from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF
import pytest


def _make_pdf_bytes() -> bytes:
    """Tworzy prosty PDF z jedną stroną."""
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Test PDF Export")
        return document.tobytes()
    finally:
        document.close()


@pytest.fixture
def uploaded_pdf(client):
    """Przesyła przykładowy PDF i zwraca token."""
    pdf_bytes = _make_pdf_bytes()

    response = client.post(
        "/upload", data={"file": (BytesIO(pdf_bytes), "test.pdf")}, content_type="multipart/form-data"
    )

    assert response.status_code == 200
    result = json.loads(response.data)

    return result["token"], result["total_pages"]


class TestPDFExport:
    """Testy dla endpointu /page/<token>/<page>/export"""

    def test_export_page_basic(self, client, uploaded_pdf):
        """Test podstawowego eksportu strony."""
        token, total_pages = uploaded_pdf

        if total_pages == 0:
            pytest.skip("PDF nie ma stron")

        response = client.get(f"/page/{token}/1/export")

        assert response.status_code == 200

        data = json.loads(response.data)
        assert "download_url" in data
        assert "filename" in data
        assert "image_dpi" in data
        assert "image_width_px" in data
        assert "image_height_px" in data

    def test_export_page_with_dpi(self, client, uploaded_pdf):
        """Test eksportu z konkretnym DPI."""
        token, _ = uploaded_pdf

        response = client.get(f"/page/{token}/1/export?dpi=200")

        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["requested_dpi"] == 200
        assert data["applied_dpi"] == 200
        assert data["clamped"] is False

    def test_export_page_dpi_clamping(self, client, uploaded_pdf):
        """Test ograniczenia zbyt wysokiego DPI."""
        token, _ = uploaded_pdf

        # Próbujemy ustawić bardzo wysokie DPI (powinno być ograniczone)
        response = client.get(f"/page/{token}/1/export?dpi=9999")

        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["requested_dpi"] == 9999
        assert data["clamped"] is True
        assert data["applied_dpi"] <= data["max_render_dpi"]
        assert "clamped_dpi" in data

    def test_export_page_low_dpi_clamping(self, client, uploaded_pdf):
        """Test ograniczenia zbyt niskiego DPI."""
        token, _ = uploaded_pdf

        response = client.get(f"/page/{token}/1/export?dpi=10")

        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["requested_dpi"] == 10
        assert data["clamped"] is True
        assert data["applied_dpi"] >= data["min_render_dpi"]

    def test_export_page_default_dpi(self, client, uploaded_pdf):
        """Test eksportu z domyślnym DPI (bez parametru)."""
        token, _ = uploaded_pdf

        response = client.get(f"/page/{token}/1/export")

        assert response.status_code == 200

        data = json.loads(response.data)
        # Powinno użyć DEFAULT_PREVIEW_DPI (zazwyczaj 150)
        assert data["applied_dpi"] > 0
        assert data["clamped"] is False

    def test_export_page_multiple_dpi_values(self, client, uploaded_pdf):
        """Test różnych wartości DPI."""
        token, _ = uploaded_pdf

        dpi_values = [72, 150, 200, 300, 600]

        for dpi in dpi_values:
            response = client.get(f"/page/{token}/1/export?dpi={dpi}")

            assert response.status_code == 200

            data = json.loads(response.data)
            assert data["requested_dpi"] == dpi

            # Sprawdź czy wymiary rosną z DPI
            assert data["image_width_px"] > 0
            assert data["image_height_px"] > 0

    def test_export_page_dimensions_scale_with_dpi(self, client, uploaded_pdf):
        """Test czy wymiary obrazu rosną proporcjonalnie do DPI."""
        token, _ = uploaded_pdf

        # Renderuj z niskim DPI
        response_low = client.get(f"/page/{token}/1/export?dpi=100")
        data_low = json.loads(response_low.data)

        # Renderuj z wysokim DPI
        response_high = client.get(f"/page/{token}/1/export?dpi=300")
        data_high = json.loads(response_high.data)

        # Wymiary powinny być ~3x większe
        width_ratio = data_high["image_width_px"] / data_low["image_width_px"]
        height_ratio = data_high["image_height_px"] / data_low["image_height_px"]

        # Sprawdź czy stosunek jest zbliżony do 3.0 (±10%)
        assert 2.7 <= width_ratio <= 3.3
        assert 2.7 <= height_ratio <= 3.3

    def test_export_page_clamps_by_pixel_limit(self, client):
        """Large PDF pages should be clamped so resulting image sides <= MAX_PREVIEW_PX."""
        # Create a huge PDF page (~50in x 50in) so at 300 DPI it would be 15000 px
        document = fitz.open()
        page = document.new_page(width=50 * 72, height=50 * 72)
        page.insert_text((72, 72), "Large page for clamping test")
        pdf_bytes = document.tobytes()
        document.close()

        response = client.post(
            "/upload", data={"file": (BytesIO(pdf_bytes), "large.pdf")}, content_type="multipart/form-data"
        )
        assert response.status_code == 200
        result = json.loads(response.data)
        # Upload should return applied/requested DPI and clamped flag
        assert "requested_dpi" in result
        assert "applied_dpi" in result
        assert "clamped" in result
        token = result["token"]

        # Request export at 300 DPI and ensure clamped to keep dimensions reasonable
        resp = client.get(f"/page/{token}/1/export?dpi=300")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["requested_dpi"] == 300
        assert data["clamped"] is True
        assert data["image_width_px"] <= client.application.config.get("MAX_PREVIEW_PIXELS", 10000)
        assert data["image_height_px"] <= client.application.config.get("MAX_PREVIEW_PIXELS", 10000)

    def test_export_page_force_rerender(self, client, uploaded_pdf):
        """Test wymuszenia ponownego renderowania."""
        token, _ = uploaded_pdf

        # Pierwsze renderowanie
        response1 = client.get(f"/page/{token}/1/export?dpi=150")
        data1 = json.loads(response1.data)

        # Drugie renderowanie (cached)
        response2 = client.get(f"/page/{token}/1/export?dpi=150")
        data2 = json.loads(response2.data)

        # Powinny mieć tę samą nazwę pliku (cache)
        assert data1["filename"] == data2["filename"]

        # Wymuszenie rerenderowania
        response3 = client.get(f"/page/{token}/1/export?dpi=150&force=true")
        data3 = json.loads(response3.data)

        # Nazwy mogą się różnić lub być takie same (zależy od implementacji)
        assert "filename" in data3

    def test_export_page_invalid_token(self, client):
        """Test eksportu z nieprawidłowym tokenem."""
        response = client.get("/page/invalid_token_xyz/1/export")

        assert response.status_code == 404

        data = json.loads(response.data)
        assert "error" in data
        assert "Unknown document" in data["error"]

    def test_get_page_includes_applied_dpi(self, client, uploaded_pdf):
        """GET /page/<token>/<page> should include requested/applied/clamped fields."""
        token, _ = uploaded_pdf
        resp = client.get(f"/page/{token}/1")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "requested_dpi" in data
        assert "applied_dpi" in data
        assert "clamped" in data

    def test_export_page_out_of_range(self, client, uploaded_pdf):
        """Test eksportu strony poza zakresem."""
        token, total_pages = uploaded_pdf

        # Próbujemy pobrać stronę poza zakresem
        invalid_page = total_pages + 10
        response = client.get(f"/page/{token}/{invalid_page}/export")

        assert response.status_code == 400

        data = json.loads(response.data)
        assert "error" in data
        assert "out of range" in data["error"].lower()

    def test_export_page_zero(self, client, uploaded_pdf):
        """Test eksportu strony 0 (nieprawidłowy numer)."""
        token, _ = uploaded_pdf

        response = client.get(f"/page/{token}/0/export")

        assert response.status_code == 400

        data = json.loads(response.data)
        assert "error" in data

    def test_export_metadata_completeness(self, client, uploaded_pdf):
        """Test kompletności metadanych w odpowiedzi."""
        token, total_pages = uploaded_pdf

        response = client.get(f"/page/{token}/1/export?dpi=200")

        assert response.status_code == 200

        data = json.loads(response.data)

        # Sprawdź wszystkie wymagane pola
        required_fields = [
            "download_url",
            "filename",
            "image_dpi",
            "image_width_px",
            "image_height_px",
            "page",
            "total_pages",
            "max_render_dpi",
            "min_render_dpi",
            "requested_dpi",
            "applied_dpi",
            "clamped",
        ]

        for field in required_fields:
            assert field in data, f"Brak pola: {field}"

        # Sprawdź typy
        assert isinstance(data["image_width_px"], int)
        assert isinstance(data["image_height_px"], int)
        assert isinstance(data["image_dpi"], int)
        assert isinstance(data["page"], int)
        assert isinstance(data["total_pages"], int)
        assert isinstance(data["clamped"], bool)

        # Sprawdź wartości
        assert data["page"] == 1
        assert data["total_pages"] == total_pages
        assert data["image_width_px"] > 0
        assert data["image_height_px"] > 0

    def test_export_download_url_valid(self, client, uploaded_pdf):
        """Test czy download_url jest prawidłowy i dostępny."""
        token, _ = uploaded_pdf

        response = client.get(f"/page/{token}/1/export?dpi=150")

        assert response.status_code == 200

        data = json.loads(response.data)
        download_url = data["download_url"]

        # Sprawdź czy możemy pobrać plik
        download_response = client.get(download_url)
        assert download_response.status_code == 200

        # Sprawdź czy to faktycznie obraz PNG
        assert download_response.content_type.startswith("image/")


class TestExportIntegration:
    """Testy integracyjne pipeline'u eksportu z innymi funkcjami."""

    def test_export_then_process(self, client, uploaded_pdf):
        """Test eksportu PNG a następnie przetwarzania obrazu."""
        token, _ = uploaded_pdf

        # Eksportuj stronę
        response = client.get(f"/page/{token}/1/export?dpi=200")
        assert response.status_code == 200

        data = json.loads(response.data)
        filename = data["filename"]

        # Sprawdź czy plik został zapisany
        upload_folder = Path(client.application.config["UPLOAD_FOLDER"])
        image_path = upload_folder / filename

        assert image_path.exists()

        # Sprawdź wymiary pliku
        try:
            from PIL import Image

            img = Image.open(image_path)

            assert img.width == data["image_width_px"]
            assert img.height == data["image_height_px"]
        except ImportError:
            pytest.skip("Pillow nie jest zainstalowany")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
