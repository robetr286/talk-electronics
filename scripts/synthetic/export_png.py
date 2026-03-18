#!/usr/bin/env python3
"""
Konwersja wygenerowanych schematów PDF/SVG do PNG w zadanym DPI.

Wykorzystuje PyMuPDF (fitz) lub Pillow do renderowania obrazów.

Użycie:
    python export_png.py --input schematic.pdf --output schematic.png --dpi 300

TODO:
- [ ] Implementować konwersję PDF -> PNG z PyMuPDF
- [ ] Obsłużyć konwersję SVG -> PNG (cairosvg lub Pillow)
- [ ] Dodać opcje DPI i rozdzielczości
- [ ] Wspierać batch processing dla wielu plików
- [ ] Zapisać metadane renderowania
"""

import argparse
from pathlib import Path
from typing import Optional

try:
    import fitz  # PyMuPDF

    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("⚠️  PyMuPDF nie jest zainstalowany. Zainstaluj: pip install PyMuPDF")


def pdf_to_png(input_path: Path, output_path: Path, dpi: int = 300, page: int = 0) -> Optional[Path]:
    """
    Konwertuje stronę PDF do PNG.

    Args:
        input_path: Ścieżka do pliku PDF.
        output_path: Ścieżka wyjściowa dla PNG.
        dpi: Rozdzielczość w DPI.
        page: Numer strony do wyrenderowania (0-indexed).

    Returns:
        Ścieżka do zapisanego PNG lub None w przypadku błędu.
    """
    if not HAS_PYMUPDF:
        raise ImportError("PyMuPDF jest wymagany do konwersji PDF")

    try:
        doc = fitz.open(input_path)

        if page >= len(doc):
            print(f"❌ Strona {page} nie istnieje w PDF (max: {len(doc)-1})")
            return None

        # Oblicz zoom na podstawie DPI
        # PyMuPDF używa 72 DPI jako bazę
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        # Renderuj stronę
        pix = doc[page].get_pixmap(matrix=mat)

        # Zapisz jako PNG
        pix.save(output_path)

        doc.close()

        print(f"✓ Wyrenderowano PNG: {output_path} ({pix.width}×{pix.height} px)")
        return output_path

    except Exception as e:
        print(f"❌ Błąd podczas konwersji PDF: {e}")
        return None


def svg_to_png(input_path: Path, output_path: Path, dpi: int = 300) -> Optional[Path]:
    """
    Konwertuje SVG do PNG.

    Args:
        input_path: Ścieżka do pliku SVG.
        output_path: Ścieżka wyjściowa dla PNG.
        dpi: Rozdzielczość w DPI.

    Returns:
        Ścieżka do zapisanego PNG lub None w przypadku błędu.
    """
    # TODO: Implementacja konwersji SVG
    # Opcje: cairosvg, svglib + reportlab, lub inkscape CLI
    print("⚠️  Konwersja SVG nie jest jeszcze zaimplementowana")
    return None


def batch_convert(input_dir: Path, output_dir: Path, dpi: int = 300, pattern: str = "*.pdf") -> int:
    """
    Konwertuje batch plików PDF/SVG do PNG.

    Args:
        input_dir: Katalog z plikami wejściowymi.
        output_dir: Katalog wyjściowy dla PNG.
        dpi: Rozdzielczość w DPI.
        pattern: Pattern glob dla plików wejściowych.

    Returns:
        Liczba pomyślnie skonwertowanych plików.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    files = list(input_dir.glob(pattern))
    success_count = 0

    for input_file in files:
        output_file = output_dir / f"{input_file.stem}.png"

        if input_file.suffix.lower() == ".pdf":
            result = pdf_to_png(input_file, output_file, dpi=dpi)
        elif input_file.suffix.lower() == ".svg":
            result = svg_to_png(input_file, output_file, dpi=dpi)
        else:
            print(f"⚠️  Nieobsługiwany format: {input_file}")
            continue

        if result:
            success_count += 1

    return success_count


def main():
    """Główna funkcja skryptu."""
    parser = argparse.ArgumentParser(description="Konwersja schematów PDF/SVG do PNG")
    parser.add_argument("--input", type=Path, help="Plik wejściowy (PDF/SVG) lub katalog dla batch")
    parser.add_argument("--output", type=Path, help="Plik wyjściowy (PNG) lub katalog dla batch")
    parser.add_argument("--dpi", type=int, default=300, help="Rozdzielczość w DPI (domyślnie: 300)")
    parser.add_argument("--page", type=int, default=0, help="Numer strony PDF (0-indexed, domyślnie: 0)")
    parser.add_argument("--batch", action="store_true", help="Tryb batch: konwertuj wszystkie pliki w katalogu")
    parser.add_argument("--pattern", default="*.pdf", help="Pattern glob dla trybu batch (domyślnie: *.pdf)")

    args = parser.parse_args()

    if not args.input:
        parser.error("Wymagany parametr --input")

    if args.batch:
        # Tryb batch
        if not args.output:
            args.output = args.input / "rendered"

        count = batch_convert(args.input, args.output, dpi=args.dpi, pattern=args.pattern)
        print(f"\n✓ Skonwertowano {count} plików do {args.output}")
    else:
        # Pojedynczy plik
        if not args.output:
            args.output = args.input.with_suffix(".png")

        if args.input.suffix.lower() == ".pdf":
            result = pdf_to_png(args.input, args.output, dpi=args.dpi, page=args.page)
        elif args.input.suffix.lower() == ".svg":
            result = svg_to_png(args.input, args.output, dpi=args.dpi)
        else:
            print(f"❌ Nieobsługiwany format: {args.input.suffix}")
            return

        if result:
            print(f"✓ Zapisano: {result}")


if __name__ == "__main__":
    main()
