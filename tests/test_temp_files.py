from __future__ import annotations

from pathlib import Path

from talk_electronic.pdf_store import PdfDocument, PdfStore
from talk_electronic.services.temp_files import cleanup_temp_files, get_temp_files_info


def create_file(path: Path, size: int) -> None:
    path.write_bytes(b"0" * size)


def test_get_temp_files_info_counts_and_sizes(tmp_path: Path) -> None:
    pdf_file = tmp_path / "example.pdf"
    png_file = tmp_path / "token_page_1.png"
    crop_file = tmp_path / "token_page_1_crop_abcd.png"

    create_file(pdf_file, 128)
    create_file(png_file, 256)
    create_file(crop_file, 64)

    count, size = get_temp_files_info(tmp_path)

    assert count == 3
    assert size == 128 + 256 + 64


def test_cleanup_temp_files_removes_supported_patterns(tmp_path: Path) -> None:
    pdf_file = tmp_path / "doc.pdf"
    png_file = tmp_path / "doc_page_2.png"
    crop_file = tmp_path / "doc_page_2_crop_xyz.png"

    create_file(pdf_file, 32)
    create_file(png_file, 48)
    create_file(crop_file, 16)

    store = PdfStore()
    store.add("token", PdfDocument(path=str(pdf_file), total_pages=2, name="doc.pdf"))

    removed, freed = cleanup_temp_files(tmp_path, store)

    assert removed == 3
    assert freed == 32 + 48 + 16
    assert store.get("token") is None
    assert not any(tmp_path.iterdir())
