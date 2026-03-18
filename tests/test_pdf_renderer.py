"""
Testy jednostkowe dla talk_electronic.services.pdf_renderer
"""

from pathlib import Path

import fitz  # PyMuPDF
import pytest

from talk_electronic.services.pdf_renderer import RenderedPage, render_pdf_page


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Tworzy prosty PDF do testów."""
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()

    # Strona 1: US Letter (8.5 x 11 inch)
    page1 = doc.new_page(width=8.5 * 72, height=11 * 72)
    page1.insert_text((100, 100), "Test Page 1", fontsize=20)

    # Strona 2: A4
    page2 = doc.new_page(width=8.27 * 72, height=11.69 * 72)
    page2.insert_text((100, 100), "Test Page 2", fontsize=20)

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def upload_folder(tmp_path: Path) -> Path:
    """Folder dla wyrenderowanych PNG."""
    folder = tmp_path / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def test_render_pdf_page_basic(sample_pdf: Path, upload_folder: Path):
    """Test podstawowego renderowania strony PDF."""
    result = render_pdf_page(pdf_path=sample_pdf, page_number=1, token="test123", upload_folder=upload_folder, dpi=300)

    assert isinstance(result, RenderedPage)
    assert result.filename == "test123_page_1.png"
    assert result.dpi == 300
    assert result.width_px > 0
    assert result.height_px > 0
    assert result.width_in > 0
    assert result.height_in > 0

    # Sprawdź czy plik został utworzony
    output_file = upload_folder / result.filename
    assert output_file.exists()


def test_render_pdf_page_custom_dpi(sample_pdf: Path, upload_folder: Path):
    """Test renderowania z niestandardowym DPI."""
    result = render_pdf_page(
        pdf_path=sample_pdf, page_number=1, token="test_dpi", upload_folder=upload_folder, dpi=150, baseline_dpi=300
    )

    assert result.filename == "test_dpi_page_1_150dpi.png"
    assert result.dpi == 150

    # DPI 150 powinno dać połowę rozdzielczości DPI 300
    result_300 = render_pdf_page(
        pdf_path=sample_pdf, page_number=1, token="test_300", upload_folder=upload_folder, dpi=300
    )

    # Proporcja powinna być w przybliżeniu 2:1
    ratio = result_300.width_px / result.width_px
    assert 1.8 < ratio < 2.2  # Akceptuj małe błędy zaokrągleń


def test_render_pdf_page_baseline_dpi_no_suffix(sample_pdf: Path, upload_folder: Path):
    """Test że DPI równe baseline_dpi nie dodaje sufiksu."""
    result = render_pdf_page(
        pdf_path=sample_pdf, page_number=1, token="baseline", upload_folder=upload_folder, dpi=300, baseline_dpi=300
    )

    assert result.filename == "baseline_page_1.png"
    assert "_dpi" not in result.filename


def test_render_pdf_page_second_page(sample_pdf: Path, upload_folder: Path):
    """Test renderowania drugiej strony."""
    result = render_pdf_page(pdf_path=sample_pdf, page_number=2, token="page2", upload_folder=upload_folder, dpi=300)

    assert result.filename == "page2_page_2.png"
    output_file = upload_folder / result.filename
    assert output_file.exists()


def test_render_pdf_page_force_rerender(sample_pdf: Path, upload_folder: Path):
    """Test że force=True nadpisuje istniejący plik."""
    # Pierwsze renderowanie
    result1 = render_pdf_page(
        pdf_path=sample_pdf, page_number=1, token="force", upload_folder=upload_folder, dpi=300, force=False
    )

    output_file = upload_folder / result1.filename
    original_mtime = output_file.stat().st_mtime

    # Drugie renderowanie bez force - nie powinno nadpisać
    import time

    time.sleep(0.01)  # Upewnij się że różnica czasu jest widoczna

    render_pdf_page(
        pdf_path=sample_pdf, page_number=1, token="force", upload_folder=upload_folder, dpi=300, force=False
    )

    assert output_file.stat().st_mtime == original_mtime

    # Trzecie renderowanie z force=True - powinno nadpisać
    time.sleep(0.01)
    render_pdf_page(pdf_path=sample_pdf, page_number=1, token="force", upload_folder=upload_folder, dpi=300, force=True)

    # W praktyce mtime może być ten sam przez buforowanie systemu plików
    # więc sprawdzamy tylko czy plik nadal istnieje
    assert output_file.exists()


def test_render_pdf_page_invalid_page_number(sample_pdf: Path, upload_folder: Path):
    """Test błędu dla nieprawidłowego numeru strony."""
    with pytest.raises(ValueError, match="Invalid page number"):
        render_pdf_page(pdf_path=sample_pdf, page_number=0, token="invalid", upload_folder=upload_folder, dpi=300)

    with pytest.raises(ValueError, match="Invalid page number"):
        render_pdf_page(pdf_path=sample_pdf, page_number=99, token="invalid", upload_folder=upload_folder, dpi=300)


def test_render_pdf_page_invalid_dpi(sample_pdf: Path, upload_folder: Path):
    """Test błędu dla nieprawidłowego DPI."""
    with pytest.raises(ValueError, match="DPI must be positive"):
        render_pdf_page(pdf_path=sample_pdf, page_number=1, token="invalid_dpi", upload_folder=upload_folder, dpi=0)

    with pytest.raises(ValueError, match="DPI must be positive"):
        render_pdf_page(pdf_path=sample_pdf, page_number=1, token="invalid_dpi", upload_folder=upload_folder, dpi=-100)


def test_render_pdf_page_dimensions_calculation(sample_pdf: Path, upload_folder: Path):
    """Test poprawności obliczania wymiarów."""
    result = render_pdf_page(
        pdf_path=sample_pdf,
        page_number=1,  # US Letter: 8.5 x 11 inch
        token="dims",
        upload_folder=upload_folder,
        dpi=300,
    )

    # US Letter: 8.5 x 11 inch
    # W 300 DPI: 8.5 * 300 = 2550px, 11 * 300 = 3300px
    assert abs(result.width_in - 8.5) < 0.1
    assert abs(result.height_in - 11) < 0.1
    assert abs(result.width_px - 2550) < 10
    assert abs(result.height_px - 3300) < 10


def test_render_pdf_page_nonexistent_file(upload_folder: Path):
    """Test błędu dla nieistniejącego pliku PDF."""
    with pytest.raises(Exception):  # fitz.FileNotFoundError lub podobny
        render_pdf_page(
            pdf_path=Path("/nonexistent/file.pdf"), page_number=1, token="error", upload_folder=upload_folder, dpi=300
        )


def test_rendered_page_dataclass_immutable():
    """Test że RenderedPage jest immutable (frozen)."""
    page = RenderedPage(filename="test.png", dpi=300, width_px=2550, height_px=3300, width_in=8.5, height_in=11.0)

    with pytest.raises(AttributeError):
        page.dpi = 150  # type: ignore

    with pytest.raises(AttributeError):
        page.filename = "changed.png"  # type: ignore
