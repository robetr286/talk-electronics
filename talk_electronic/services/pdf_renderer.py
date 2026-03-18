from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:  # PyMuPDF
    import fitz  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    fitz = None  # type: ignore
try:  # Pillow
    from PIL import Image, UnidentifiedImageError
except ImportError:  # pragma: no cover - optional dependency
    Image = None  # type: ignore
    UnidentifiedImageError = None  # type: ignore


@dataclass(frozen=True)
class RenderedPage:
    filename: str
    dpi: int
    width_px: int
    height_px: int
    width_in: float
    height_in: float


def render_pdf_page(
    pdf_path: Path,
    page_number: int,
    token: str,
    upload_folder: Path,
    dpi: int = 300,
    *,
    baseline_dpi: int = 300,
    force: bool = False,
) -> RenderedPage:
    """Render a PDF page to a PNG file and return metadata about the render."""
    if dpi <= 0:
        raise ValueError("DPI must be positive")

    if fitz is None:  # pragma: no cover - exercised when PyMuPDF is missing
        raise RuntimeError("PyMuPDF (fitz) is not installed")

    suffix = "" if dpi == baseline_dpi else f"_{dpi}dpi"
    png_filename = f"{token}_page_{page_number}{suffix}.png"
    destination = upload_folder / png_filename

    with fitz.open(pdf_path) as document:
        if page_number < 1 or page_number > document.page_count:
            raise ValueError("Invalid page number")

        page = document.load_page(page_number - 1)
        rect = page.rect
        width_in = rect.width / 72.0
        height_in = rect.height / 72.0
        width_px = max(1, int(round(width_in * dpi)))
        height_px = max(1, int(round(height_in * dpi)))

        if force or not destination.exists():
            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            pixmap.save(destination)

    return RenderedPage(
        filename=png_filename,
        dpi=dpi,
        width_px=width_px,
        height_px=height_px,
        width_in=width_in,
        height_in=height_in,
    )


def render_image_page(
    image_path: Path,
    token: str,
    upload_folder: Path,
    dpi: int = 300,
    *,
    baseline_dpi: int | None = 300,
    force: bool = False,
) -> RenderedPage:
    """Render a raster image to PNG respecting target DPI and return metadata."""
    if dpi <= 0:
        raise ValueError("DPI must be positive")

    if Image is None or UnidentifiedImageError is None:  # pragma: no cover - optional dep
        raise RuntimeError("Pillow (PIL) is not installed")

    effective_baseline = baseline_dpi if baseline_dpi and baseline_dpi > 0 else 300
    suffix = "" if dpi == effective_baseline else f"_{dpi}dpi"
    png_filename = f"{token}_page_1{suffix}.png"
    destination = upload_folder / png_filename

    try:
        with Image.open(image_path) as img:
            img.load()
            source_width, source_height = img.size
            page_width_in = source_width / effective_baseline
            page_height_in = source_height / effective_baseline

            target_width = max(1, int(round(page_width_in * dpi)))
            target_height = max(1, int(round(page_height_in * dpi)))

            if force or not destination.exists():
                resample_filter = getattr(Image, "LANCZOS", Image.BICUBIC)
                if target_width != source_width or target_height != source_height:
                    rendered = img.resize((target_width, target_height), resample=resample_filter)
                else:
                    rendered = img.copy()
                rendered.save(destination, format="PNG")
    except UnidentifiedImageError as exc:
        raise ValueError("Invalid image file") from exc

    return RenderedPage(
        filename=png_filename,
        dpi=dpi,
        width_px=target_width,
        height_px=target_height,
        width_in=page_width_in,
        height_in=page_height_in,
    )
