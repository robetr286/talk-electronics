"""OCR service package for electronic schematic text recognition.

This package provides:
- PaddleOCR PP-OCRv4 integration for text detection and recognition
- Token preprocessing and postprocessing pipelines
- Component-to-value pairing algorithms
- Overlay rendering for visualization

Modules:
    preprocessing: PDF rasterization, bbox normalization
    pairing: Component-value matching algorithms
    paddle_engine: PaddleOCR PP-OCRv4 integration
"""

from .paddle_engine import run_ocr, run_ocr_with_pairing, get_ocr_engine, format_for_frontend
from .pairing import categorize, pair_components_to_values
from .postprocessing import postprocess_tokens, fix_truncated_ic, clean_token_text, should_drop_noise
from .preprocessing import (
    bbox_center,
    bbox_distance,
    bbox_iou,
    rasterize_pdf,
    rasterize_pdf_pages,
    parse_pages_param,
)

__all__ = [
    # Engine
    "run_ocr",
    "run_ocr_with_pairing",
    "get_ocr_engine",
    "format_for_frontend",
    # Pairing
    "categorize",
    "pair_components_to_values",
    # Postprocessing
    "postprocess_tokens",
    "fix_truncated_ic",
    "clean_token_text",
    "should_drop_noise",
    # Preprocessing
    "bbox_center",
    "bbox_distance",
    "bbox_iou",
    "rasterize_pdf",
    "rasterize_pdf_pages",
    "parse_pages_param",
]
