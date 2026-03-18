from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify

from ..pdf_store import PdfStore
from ..services.processing_history import ProcessingHistoryStore
from ..services.retouch_buffer import RetouchBuffer
from ..services.temp_files import cleanup_temp_files, get_temp_files_info

maintenance_bp = Blueprint("maintenance", __name__)


def _get_pdf_store() -> PdfStore:
    return current_app.extensions["pdf_store"]


def _get_history_store() -> ProcessingHistoryStore:
    return current_app.extensions["processing_history"]


def _get_retouch_buffer() -> RetouchBuffer:
    return current_app.extensions["retouch_buffer"]


def _roi_metrics_snapshot() -> dict[str, int]:
    metrics = current_app.extensions.get("roi_metrics") or {}
    keys = (
        "total",
        "roi_used",
        "roi_missing",
        "roi_crop_ok",
        "roi_crop_empty",
        "roi_crop_error",
        "load_error",
    )
    return {key: int(metrics.get(key, 0)) for key in keys}


@maintenance_bp.get("/temp-files-info")
def temp_files_info():  # type: ignore[override]
    upload_folder: Path = current_app.config["UPLOAD_FOLDER"]
    preserved = _get_history_store().get_referenced_filenames()
    preserved.update(_get_retouch_buffer().get_preserved_filenames())
    file_count, total_size = get_temp_files_info(upload_folder, preserved)
    size_mb = total_size / (1024 * 1024)
    return jsonify({"count": file_count, "size_bytes": total_size, "size_mb": round(size_mb, 2)})


@maintenance_bp.post("/cleanup-temp")
def cleanup_temp():  # type: ignore[override]
    upload_folder: Path = current_app.config["UPLOAD_FOLDER"]
    preserved = _get_history_store().get_referenced_filenames()
    preserved.update(_get_retouch_buffer().get_preserved_filenames())
    removed_count, freed_space = cleanup_temp_files(upload_folder, _get_pdf_store(), preserved)
    freed_mb = freed_space / (1024 * 1024)
    return jsonify(
        {
            "success": True,
            "removed_count": removed_count,
            "freed_space_bytes": freed_space,
            "freed_space_mb": round(freed_mb, 2),
        }
    )


@maintenance_bp.get("/healthz")
def healthcheck():  # type: ignore[override]
    upload_folder: Path = current_app.config["UPLOAD_FOLDER"]
    return jsonify(
        {
            "status": "ok",
            "upload_exists": upload_folder.exists(),
            "roi_metrics": _roi_metrics_snapshot(),
            "version": current_app.config.get("APP_VERSION", "unknown"),
        }
    )
