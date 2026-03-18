from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, Tuple

from ..pdf_store import PdfStore

PDF_PATTERN = "*.pdf"
PNG_PATTERN = "*_page_*.png"
CROP_PATTERN = "*_crop_*.png"
IMAGE_SOURCE_PATTERNS = (
    "*_source.png",
    "*_source.jpg",
    "*_source.jpeg",
    "*_source.webp",
    "*_source.tif",
    "*_source.tiff",
    "*_source.bmp",
)
DEFAULT_PATTERNS = (PDF_PATTERN, PNG_PATTERN, CROP_PATTERN, *IMAGE_SOURCE_PATTERNS)


def _iter_temp_files(upload_folder: Path, patterns: Iterable[str]) -> Iterator[Path]:
    """Yield matching files once even if multiple patterns overlap."""

    seen: set[str] = set()

    for pattern in patterns:
        for file_path in upload_folder.glob(pattern):
            key = str(file_path.resolve(strict=False))
            if key in seen:
                continue
            seen.add(key)
            yield file_path


def cleanup_temp_files(
    upload_folder: Path,
    pdf_store: PdfStore | None = None,
    preserve_filenames: Iterable[str] | None = None,
) -> Tuple[int, int]:
    """Remove residual temporary files used during PDF rendering and cropping."""
    removed = 0
    freed_bytes = 0
    preserved = {str(name) for name in preserve_filenames or ()}

    for file_path in _iter_temp_files(upload_folder, DEFAULT_PATTERNS):
        try:
            relative = file_path.relative_to(upload_folder).as_posix()
        except ValueError:
            relative = file_path.name
        if relative in preserved:
            continue
        try:
            file_size = file_path.stat().st_size
            file_path.unlink()
            removed += 1
            freed_bytes += file_size
        except FileNotFoundError:
            continue

    if pdf_store is not None:
        pdf_store.clear()

    return removed, freed_bytes


def get_temp_files_info(
    upload_folder: Path,
    preserve_filenames: Iterable[str] | None = None,
) -> Tuple[int, int]:
    """Return the current count and total size of temporary files."""
    count = 0
    total_size = 0
    preserved = {str(name) for name in preserve_filenames or ()}

    for file_path in _iter_temp_files(upload_folder, DEFAULT_PATTERNS):
        try:
            relative = file_path.relative_to(upload_folder).as_posix()
        except ValueError:
            relative = file_path.name
        if relative in preserved:
            continue
        try:
            total_size += file_path.stat().st_size
            count += 1
        except FileNotFoundError:
            continue

    return count, total_size
