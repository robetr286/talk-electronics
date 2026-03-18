"""PaddleOCR PP-OCRv4 engine for electronic schematic OCR.

This module provides a wrapper around PaddleOCR PP-OCRv4 for text detection
and recognition on schematic diagrams.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Set PaddlePaddle flags BEFORE importing paddle
os.environ.setdefault('FLAGS_use_mkldnn', '0')
os.environ.setdefault('FLAGS_enable_pir_api', '0')
os.environ.setdefault('FLAGS_enable_pir_in_executor', '0')
os.environ.setdefault('FLAGS_pir_apply_inplace_pass', '0')
os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')

import paddle
paddle.set_flags({'FLAGS_use_mkldnn': False})

from paddleocr import PaddleOCR as PaddleOCRBase

from .preprocessing import bbox_center
from .pairing import categorize

# Singleton OCR engine instance
_ocr_engine: Optional[PaddleOCRBase] = None


def get_ocr_engine() -> PaddleOCRBase:
    """Get or create singleton PaddleOCR engine instance.
    
    Returns:
        Initialized PaddleOCR engine with PP-OCRv4 model
    """
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = PaddleOCRBase(
            use_textline_orientation=False,  # Updated from deprecated use_angle_cls
            lang='en',
            ocr_version='PP-OCRv4',
            enable_mkldnn=False,
        )
    return _ocr_engine


def run_ocr(
    image_path: str | Path,
    min_confidence: float = 30.0,
) -> Dict[str, Any]:
    """Run OCR on image and return structured results.
    
    Args:
        image_path: Path to input image
        min_confidence: Minimum confidence threshold (0-100)
        
    Returns:
        Dict with keys:
            - tokens: List of token dicts with text, bbox, center, category, confidence
            - pairs: List of component-value pairings (empty, computed later)
            - width: Image width
            - height: Image height
    """
    ocr = get_ocr_engine()
    image_path = Path(image_path)
    
    # Run OCR prediction
    result = ocr.predict(str(image_path))
    
    if not result:
        return {"tokens": [], "pairs": [], "width": 0, "height": 0}
    
    # Extract page result (PaddleOCR returns list of pages)
    page = result[0]
    
    # Get image dimensions
    width = page.get('width', 0)
    height = page.get('height', 0)
    
    # If dimensions not in result, read from image
    if width == 0 or height == 0:
        from PIL import Image
        with Image.open(image_path) as img:
            width, height = img.size
    
    # Extract tokens
    tokens = []
    rec_texts = page.get('rec_texts', [])
    rec_scores = page.get('rec_scores', [])
    rec_boxes = page.get('rec_boxes', [])
    dt_polys = page.get('dt_polys', [])
    
    for i, text in enumerate(rec_texts):
        text = text.strip()
        if not text:
            continue
            
        # Get confidence (0-1 scale → 0-100)
        confidence = rec_scores[i] * 100 if i < len(rec_scores) else 0.0
        
        # Skip low confidence
        if confidence < min_confidence:
            continue
        
        # Get bounding box [x_min, y_min, x_max, y_max]
        if i < len(rec_boxes):
            box = rec_boxes[i]
            if hasattr(box, 'tolist'):
                box = box.tolist()
            x1, y1, x2, y2 = box
            # Convert to (x, y, width, height) format
            bbox = (float(x1), float(y1), float(x2 - x1), float(y2 - y1))
        elif i < len(dt_polys):
            # Fallback to polygon - compute bounding rect
            poly = dt_polys[i]
            if hasattr(poly, 'tolist'):
                poly = poly.tolist()
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            x1, y1 = min(xs), min(ys)
            x2, y2 = max(xs), max(ys)
            bbox = (float(x1), float(y1), float(x2 - x1), float(y2 - y1))
        else:
            continue
        
        # Compute center
        center = bbox_center(bbox)
        
        # Categorize token
        category = categorize(text)
        
        tokens.append({
            "text": text,
            "confidence": confidence,
            "bbox": bbox,
            "center": center,
            "category": category,
        })
    
    return {
        "tokens": tokens,
        "pairs": [],  # Computed by pairing module
        "width": width,
        "height": height,
    }


def run_ocr_with_pairing(
    image_path: str | Path,
    min_confidence: float = 30.0,
) -> Dict[str, Any]:
    """Run OCR, apply postprocessing, and compute component-value pairings.
    
    Pipeline: OCR → clean/merge/fix → pair components to values → fix truncated ICs
    
    Args:
        image_path: Path to input image
        min_confidence: Minimum confidence threshold (0-100)
        
    Returns:
        Dict with tokens, pairs, width, height
    """
    from .pairing import pair_components_to_values
    from .postprocessing import postprocess_tokens, fix_truncated_ic
    
    result = run_ocr(image_path, min_confidence)
    
    if result["tokens"]:
        result["tokens"] = postprocess_tokens(result["tokens"], min_confidence)
        result["pairs"] = pair_components_to_values(result["tokens"])
        result["tokens"], result["pairs"] = fix_truncated_ic(
            result["tokens"], result["pairs"]
        )
    
    return result


def format_for_frontend(
    ocr_result: Dict[str, Any],
    image_width: Optional[int] = None,
    image_height: Optional[int] = None,
) -> Dict[str, Any]:
    """Format OCR result for frontend display.
    
    Converts internal format to JSON-serializable structure
    expected by the frontend JavaScript.
    
    Args:
        ocr_result: Result from run_ocr or run_ocr_with_pairing
        image_width: Override image width
        image_height: Override image height
        
    Returns:
        Dict suitable for JSON response
    """
    width = image_width or ocr_result.get("width", 0)
    height = image_height or ocr_result.get("height", 0)
    
    # Format tokens for frontend
    blocks = []
    for token in ocr_result.get("tokens", []):
        bbox = token["bbox"]
        # Convert to normalized coordinates (0-1) for frontend
        norm_bbox = {
            "Left": bbox[0] / width if width else 0,
            "Top": bbox[1] / height if height else 0,
            "Width": bbox[2] / width if width else 0,
            "Height": bbox[3] / height if height else 0,
        }
        blocks.append({
            "BlockType": "WORD",
            "Text": token["text"],
            "Confidence": token["confidence"],
            "Geometry": {"BoundingBox": norm_bbox},
            "Category": token["category"],
        })
    
    # Format pairs for frontend
    pairs = []
    for pair in ocr_result.get("pairs", []):
        comp_bbox = pair["component_bbox"]
        val_bbox = pair["value_bbox"]
        pairs.append({
            "component": pair["component"],
            "value": pair["value"],
            "component_bbox": {
                "Left": comp_bbox[0] / width if width else 0,
                "Top": comp_bbox[1] / height if height else 0,
                "Width": comp_bbox[2] / width if width else 0,
                "Height": comp_bbox[3] / height if height else 0,
            },
            "value_bbox": {
                "Left": val_bbox[0] / width if width else 0,
                "Top": val_bbox[1] / height if height else 0,
                "Width": val_bbox[2] / width if width else 0,
                "Height": val_bbox[3] / height if height else 0,
            },
        })
    
    return {
        "Blocks": blocks,
        "Pairs": pairs,
        "ImageWidth": width,
        "ImageHeight": height,
    }
