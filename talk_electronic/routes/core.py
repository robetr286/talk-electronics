from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml
from dateutil import parser as date_parser
from flask import Blueprint, current_app, jsonify, render_template, send_from_directory

core_bp = Blueprint("core", __name__)


@core_bp.get("/")
def index() -> str:
    # Load data-driven 'O aplikacji' entries if available
    project_root = Path(current_app.root_path).parent
    data_file = project_root / "data" / "about_entries.yaml"
    about_entries = []
    if data_file.exists():
        try:
            raw = yaml.safe_load(data_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                about_entries = raw.get("about_entries", []) or []
            elif isinstance(raw, list):
                about_entries = raw
        except Exception:  # pragma: no cover - best effort
            current_app.logger.exception("Failed to load about entries from %s", data_file)

    # Sort entries by parsed date (oldest -> newest); fallback to minimal date
    def _parse_date(entry: dict) -> datetime:
        d = entry.get("date")
        if not d:
            return datetime.min
        try:
            return date_parser.parse(str(d))
        except Exception:
            return datetime.min

    about_entries_sorted = sorted(about_entries, key=_parse_date)

    return render_template("index.html", about_entries=about_entries_sorted)


@core_bp.get("/uploads/<path:filename>")
def serve_upload(filename: str):  # type: ignore[override]
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    response = send_from_directory(str(upload_folder), filename, max_age=0)
    # Wyłącz cache przeglądarki, żeby po nadpisaniu pobierać świeży plik
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@core_bp.get("/favicon.ico")
def favicon():  # type: ignore[override]
    """Serve favicon if present in static folder, otherwise return 204 to avoid browser 404 spam."""
    static_folder = current_app.static_folder or "static"
    # If a static favicon exists, serve it; otherwise return 204 No Content.
    try:
        return send_from_directory(static_folder, "favicon.ico")
    except Exception:
        return "", 204


def _ensure_roi_metrics() -> dict:
    store = current_app.extensions.setdefault("roi_metrics", {})
    for key in (
        "total",
        "roi_used",
        "roi_missing",
        "roi_crop_ok",
        "roi_crop_empty",
        "roi_crop_error",
        "load_error",
    ):
        store.setdefault(key, 0)
    return dict(store)


@core_bp.get("/healthz")
def healthz():  # type: ignore[override]
    roi_metrics = _ensure_roi_metrics()
    payload = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "roi_metrics": roi_metrics,
        "upload_dir": str(current_app.config.get("UPLOAD_FOLDER")),
    }
    return jsonify(payload), 200
