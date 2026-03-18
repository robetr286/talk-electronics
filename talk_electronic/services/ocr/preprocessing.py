"""Preprocessing utilities for OCR pipeline.

Contains:
- Bounding box normalization and calculations
- PDF rasterization to images
- Page parameter parsing
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

try:
    import fitz  # PyMuPDF for PDF rasterization
except Exception:
    fitz = None


def norm_bbox_to_px(
    bbox: Dict[str, float], w: int, h: int
) -> Tuple[float, float, float, float]:
    """Convert normalized bbox (0-1) to pixel coordinates.
    
    Args:
        bbox: Dict with Left, Top, Width, Height (normalized 0-1)
        w: Image width in pixels
        h: Image height in pixels
        
    Returns:
        Tuple (x, y, width, height) in pixels
    """
    return (
        bbox.get("Left", 0.0) * w,
        bbox.get("Top", 0.0) * h,
        bbox.get("Width", 0.0) * w,
        bbox.get("Height", 0.0) * h,
    )


def bbox_center(bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """Calculate center point of bounding box.
    
    Args:
        bbox: Tuple (x, y, width, height)
        
    Returns:
        Tuple (center_x, center_y)
    """
    x, y, bw, bh = bbox
    return x + bw / 2.0, y + bh / 2.0


def bbox_distance(b1: Tuple[float, ...], b2: Tuple[float, ...]) -> float:
    """Calculate Euclidean distance between bbox centers.
    
    Args:
        b1, b2: Bounding boxes as (x, y, w, h) tuples
        
    Returns:
        Distance in pixels
    """
    c1 = bbox_center((b1[0], b1[1], b1[2], b1[3]))
    c2 = bbox_center((b2[0], b2[1], b2[2], b2[3]))
    return ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2) ** 0.5


def bbox_iou(b1: Tuple[float, ...], b2: Tuple[float, ...]) -> float:
    """Calculate Intersection over Union for two bounding boxes.
    
    Args:
        b1, b2: Bounding boxes as (x, y, w, h) tuples
        
    Returns:
        IoU value between 0 and 1
    """
    x1, y1, w1, h1 = b1[:4]
    x2, y2, w2, h2 = b2[:4]
    
    # Calculate intersection
    xi1 = max(x1, x2)
    yi1 = max(y1, y2)
    xi2 = min(x1 + w1, x2 + w2)
    yi2 = min(y1 + h1, y2 + h2)
    
    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0
    
    inter_area = (xi2 - xi1) * (yi2 - yi1)
    area1 = w1 * h1
    area2 = w2 * h2
    union_area = area1 + area2 - inter_area
    
    return inter_area / union_area if union_area > 0 else 0.0


def rasterize_pdf(pdf_path: Path, req_id: str, dpi: int = 200) -> Path | None:
    """Rasterize first page of PDF to PNG image.
    
    Args:
        pdf_path: Path to PDF file
        req_id: Request ID for output filename
        dpi: Resolution for rasterization
        
    Returns:
        Path to rasterized PNG or None on failure
    """
    if fitz is None:
        return None
    try:
        doc = fitz.open(pdf_path)
        if not doc:
            return None
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=dpi)
        out_path = pdf_path.with_suffix("").parent / f"{req_id}_{pdf_path.stem}.png"
        pix.save(out_path)
        return out_path
    except Exception:
        return None


def rasterize_pdf_pages(
    pdf_path: Path, req_id: str, page_numbers: List[int], dpi: int = 200
) -> Dict[int, Path]:
    """Rasterize selected PDF pages to PNG images.
    
    Args:
        pdf_path: Path to PDF file
        req_id: Request ID for output filenames
        page_numbers: List of 1-based page numbers to rasterize
        dpi: Resolution for rasterization
        
    Returns:
        Dict mapping page number -> Path to rasterized PNG
    """
    if fitz is None:
        return {}
    try:
        doc = fitz.open(pdf_path)
        result: Dict[int, Path] = {}
        for pnum in page_numbers:
            idx = pnum - 1
            if idx < 0 or idx >= len(doc):
                continue
            page = doc.load_page(idx)
            pix = page.get_pixmap(dpi=dpi)
            out_path = pdf_path.with_suffix("").parent / f"{req_id}_{pdf_path.stem}_p{pnum}.png"
            pix.save(out_path)
            result[pnum] = out_path
        return result
    except Exception:
        return {}


def parse_pages_param(raw: str | None) -> List[int]:
    """Parse page range string like "1,3-5,7" into list of page numbers.
    
    Args:
        raw: Page range string (comma-separated, supports ranges with "-")
        
    Returns:
        Sorted list of unique page numbers
    """
    if not raw:
        return []
    pages: set[int] = set()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for part in parts:
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                s, e = int(start), int(end)
                if s <= e:
                    for n in range(s, e + 1):
                        pages.add(n)
            except ValueError:
                continue
        else:
            try:
                pages.add(int(part))
            except ValueError:
                continue
    return sorted(pages)
