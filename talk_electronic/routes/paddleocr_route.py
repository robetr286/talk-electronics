"""PaddleOCR endpoint for local OCR.

This module provides Flask routes for running PaddleOCR PP-OCRv4
on schematic images, with token categorization and component-value pairing.
"""

import json
import os
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from PIL import Image

# Import OCR service package (handles PaddlePaddle flags internally)
try:
    from talk_electronic.services.ocr import (
        run_ocr_with_pairing,
        get_ocr_engine,
        categorize,
    )
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False

paddleocr_bp = Blueprint("paddleocr", __name__, url_prefix="/ocr")


@paddleocr_bp.post("/paddle")
def paddleocr_run():
    """Local OCR endpoint using PaddleOCR PP-OCRv4.
    
    Returns token coordinates with categories and component-value pairings.
    """
    if not PADDLE_AVAILABLE:
        return jsonify({"error": "PaddleOCR not installed"}), 500
        
    req_id = str(uuid.uuid4())
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "brak pliku 'file'", "request_id": req_id}), 400
        
    upload_dir = Path(current_app.config.get("UPLOAD_FOLDER", "uploads")).resolve() / "paddle"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{req_id}_{file.filename}"
    file.save(dest)
    
    try:
        # Run OCR with categorization and pairing
        result = run_ocr_with_pairing(str(dest), min_confidence=30.0)
    except Exception as exc:
        current_app.logger.exception("PaddleOCR inference failed: %s", exc)
        return jsonify({"error": f"OCR inference failed: {exc}", "request_id": req_id}), 500

    # Get image dimensions
    img_w = result.get("width", 1000)
    img_h = result.get("height", 1000)
    
    # Add IDs to tokens for frontend compatibility
    tokens = []
    for token in result.get("tokens", []):
        tokens.append({
            "id": str(uuid.uuid4()),
            "text": token["text"],
            "confidence": token["confidence"],
            "bbox": token["bbox"],
            "center": token["center"],
            "category": token["category"],
            "paddle_type": "WORD",
        })
    
    # Format pairs for frontend
    pairs = []
    for pair in result.get("pairs", []):
        pairs.append({
            "component": pair["component"],
            "value": pair["value"],
            "component_bbox": pair["component_bbox"],
            "value_bbox": pair["value_bbox"],
            "component_center": pair.get("component_center"),
            "value_center": pair.get("value_center"),
        })
    
    pages_out = [
        {
            "page": 1,
            "width": img_w,
            "height": img_h,
            "tokens": tokens,
            "pairs": pairs,
        }
    ]

    return jsonify({
        "request_id": req_id,
        "status": "ok",
        "pages": pages_out,
        "tokens": tokens,
        "pairs": pairs,
        "warnings": []
    }), 200

@paddleocr_bp.post("/paddle/corrections")
def paddle_save_corrections():
    """
    Zapisuje korekty dokonane przez użytkownika na frontendzie w Canvas,
    zeby nie wywoływać błędu po stronie JS (analogicznie do starego Textracta).
    """
    payload = request.json or {}
    req_id = payload.get("request_id", "unknown_req")
    corrections = payload.get("corrections", [])
    
    corr_dir = Path("reports/paddle/corrections").resolve()
    corr_dir.mkdir(parents=True, exist_ok=True)
    out_path = corr_dir / f"{req_id}_corrections.json"
    
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as exc:
        current_app.logger.exception("Unable to save corrections %s", exc)
        return jsonify({"status": "error", "message": "Failed to save corrections"}), 500
        
    return jsonify({
        "status": "ok",
        "message": f"Saved {len(corrections)} corrections",
        "doc": str(out_path.name)
    })
