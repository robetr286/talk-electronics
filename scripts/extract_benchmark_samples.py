#!/usr/bin/env python3
"""Export PNG samples from PDF schematics for benchmarking detectors."""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import fitz  # PyMuPDF
from PIL import Image

DEFAULT_OUTPUT = Path("data/sample_benchmark")
DEFAULT_METADATA = DEFAULT_OUTPUT / "samples.csv"


@dataclass(frozen=True)
class SampleInfo:
    sample_id: str
    filename: Path
    source_pdf: Path
    page: int
    row: int
    col: int
    width: int
    height: int
    tag: str | None
    license: str
    notes: str


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate PNG benchmark samples from PDF schematics")
    parser.add_argument("pdf", nargs="+", type=Path, help="Input PDF files")
    parser.add_argument("--pages", type=int, nargs="*", default=None, help="Specific page numbers to export (1-based)")
    parser.add_argument("--tile-rows", type=int, default=1, help="Number of rows to split each page into")
    parser.add_argument("--tile-cols", type=int, default=1, help="Number of columns to split each page into")
    parser.add_argument("--dpi", type=int, default=300, help="Render DPI")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory for PNG tiles")
    parser.add_argument("--metadata", type=Path, default=None, help="Path to CSV metadata file")
    parser.add_argument("--tag", type=str, default=None, help="Optional tag/category for all generated samples")
    parser.add_argument("--license", type=str, default="unspecified", help="License descriptor stored in metadata")
    parser.add_argument("--notes", type=str, default="", help="Free-form notes stored in metadata")
    return parser.parse_args(argv)


def _ensure_output(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def _iter_pages(document: fitz.Document, pages: Iterable[int] | None) -> Iterator[int]:
    if not pages:
        yield from range(1, document.page_count + 1)
        return
    for page in pages:
        if 1 <= page <= document.page_count:
            yield page


def _render_page(document: fitz.Document, page_number: int, dpi: int) -> Image.Image:
    page = document.load_page(page_number - 1)
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    mode = "RGB" if pixmap.n < 4 else "RGBA"
    image = Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples)
    if mode == "RGBA":
        image = image.convert("RGB")
    return image


def _tile_image(image: Image.Image, rows: int, cols: int) -> Iterator[tuple[int, int, Image.Image]]:
    if rows <= 0 or cols <= 0:
        raise ValueError("Tile rows and cols must be positive")
    tile_width = image.width // cols
    tile_height = image.height // rows
    for row in range(rows):
        for col in range(cols):
            left = col * tile_width
            upper = row * tile_height
            right = image.width if col == cols - 1 else left + tile_width
            lower = image.height if row == rows - 1 else upper + tile_height
            yield row, col, image.crop((left, upper, right, lower))


def _write_metadata(rows: Sequence[SampleInfo], metadata_path: Path) -> None:
    header = (
        "sample_id",
        "filename",
        "source_pdf",
        "page",
        "row",
        "col",
        "width_px",
        "height_px",
        "tag",
        "license",
        "notes",
    )
    file_exists = metadata_path.exists()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if not file_exists:
            writer.writerow(header)
        for row in rows:
            writer.writerow(
                [
                    row.sample_id,
                    row.filename.as_posix(),
                    row.source_pdf.as_posix(),
                    row.page,
                    row.row,
                    row.col,
                    row.width,
                    row.height,
                    row.tag or "",
                    row.license,
                    row.notes,
                ]
            )


def _generate_samples(args: argparse.Namespace) -> list[SampleInfo]:
    output_dir = args.output
    metadata_path = args.metadata or DEFAULT_METADATA
    _ensure_output(output_dir)

    sample_records: list[SampleInfo] = []

    for pdf_path in args.pdf:
        if not pdf_path.exists():
            print(f"[WARN] PDF not found: {pdf_path}")
            continue
        with fitz.open(pdf_path) as document:
            for page_number in _iter_pages(document, args.pages):
                image = _render_page(document, page_number, dpi=args.dpi)
                for row, col, tile in _tile_image(image, args.tile_rows, args.tile_cols):
                    sample_id = f"{pdf_path.stem}_p{page_number:02d}_r{row}_c{col}"
                    filename = output_dir / f"{sample_id}.png"
                    tile.save(filename, format="PNG")
                    sample_records.append(
                        SampleInfo(
                            sample_id=sample_id,
                            filename=filename,
                            source_pdf=pdf_path.resolve(),
                            page=page_number,
                            row=row,
                            col=col,
                            width=tile.width,
                            height=tile.height,
                            tag=args.tag,
                            license=args.license,
                            notes=args.notes,
                        )
                    )
    if sample_records:
        _write_metadata(sample_records, metadata_path)
    return sample_records


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    samples = _generate_samples(args)
    if not samples:
        print("No samples generated.")
        return 1
    print(f"Generated {len(samples)} samples under {args.output}.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
