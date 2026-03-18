from __future__ import annotations

import io
import shutil
import uuid
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency
    Image = None  # type: ignore

from flask import Blueprint, current_app, jsonify, request, url_for

from ..pdf_store import PdfStore
from ..services.pdf_renderer import render_image_page

crop_bp = Blueprint("crop", __name__)


@crop_bp.post("/erase")
def erase():  # type: ignore[override]
    data = request.get_json(silent=True) or {}
    x = data.get("x")
    y = data.get("y")
    if x is None or y is None:
        return jsonify({"error": "Missing coordinates"}), 400

    # Placeholder response until image erase support is implemented.
    return jsonify({"image_url": "/uploads/placeholder.png"})


@crop_bp.post("/save-crop")
def save_crop():  # type: ignore[override]
    upload_folder: Path = current_app.config["UPLOAD_FOLDER"]

    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"success": False, "error": "No selected file"})

    token = request.form.get("token", "unknown")
    page = request.form.get("page", "1")

    crop_filename = f"{token}_page_{page}_crop_{uuid.uuid4().hex[:8]}.png"
    crop_path = upload_folder / crop_filename

    try:
        file.save(crop_path)
        size_kb = crop_path.stat().st_size / 1024
    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception("Error saving crop", exc_info=exc)
        return jsonify({"success": False, "error": str(exc)})

    return jsonify(
        {
            "success": True,
            "filename": crop_filename,
            "size_kb": round(size_kb, 2),
            "url": url_for("core.serve_upload", filename=crop_filename),
        }
    )


def _get_pdf_store() -> PdfStore:
    return current_app.extensions["pdf_store"]


def _suffix_to_pillow_format(suffix: str) -> str | None:
    mapping = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".bmp": "BMP",
        ".tif": "TIFF",
        ".tiff": "TIFF",
        ".webp": "WEBP",
    }
    return mapping.get(suffix.lower())


@crop_bp.post("/overwrite-original")
def overwrite_original():  # type: ignore[override]
    upload_folder: Path = current_app.config["UPLOAD_FOLDER"]

    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"success": False, "error": "Brak pliku do zapisania"}), 400

    token = request.form.get("token", "").strip()
    if not token:
        return jsonify({"success": False, "error": "Brak tokenu dokumentu"}), 400

    store = _get_pdf_store()
    metadata = store.get(token)
    if metadata is None:
        return jsonify({"success": False, "error": "Nie znaleziono dokumentu"}), 404

    original_path = Path(metadata.path)
    if not original_path.exists():
        return jsonify({"success": False, "error": "Plik źródłowy niedostępny"}), 404

    if metadata.kind != "image":
        return (
            jsonify({"success": False, "error": "Nadpisywanie dostępne jest tylko dla plików graficznych (nie PDF)."}),
            400,
        )

    backup_dir = upload_folder / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{original_path.stem}_backup_{timestamp}{original_path.suffix}"
    backup_path = backup_dir / backup_filename

    try:
        shutil.copy2(original_path, backup_path)
    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception("Nie udało się wykonać kopii zapasowej", exc_info=exc)
        return jsonify({"success": False, "error": "Nie udało się utworzyć kopii zapasowej pliku."}), 500

    try:
        raw_bytes = file.read()
        file.stream.seek(0)

        if not raw_bytes:
            return jsonify({"success": False, "error": "Pusty plik — brak danych do zapisania."}), 400

        # Zapisywanie do nowego pliku (omija ewentualne blokady Windows), potem podmieniamy ścieżkę w PdfStore
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        new_source_path = original_path.with_name(f"{original_path.stem}_overwrite_{timestamp}{original_path.suffix}")

        suffix = original_path.suffix.lower()
        pillow_format = _suffix_to_pillow_format(suffix)
        if Image is not None and pillow_format:
            try:
                with Image.open(io.BytesIO(raw_bytes)) as img:
                    img_converted = img
                    if pillow_format == "JPEG" and img.mode != "RGB":
                        # JPEG nie wspiera kanału alfa ani palety
                        img_converted = img.convert("RGB")
                    img_converted.save(new_source_path, format=pillow_format)
            except Exception:  # pragma: no cover - fallback gdy PIL nie zapisze
                current_app.logger.warning("Pillow nie zapisał pliku, zapisuję surowe bajty", exc_info=True)
                new_source_path.write_bytes(raw_bytes)
        else:
            # Bez PIL lub bez formatu — zapisz surowe bajty 1:1
            new_source_path.write_bytes(raw_bytes)

        current_app.logger.info(
            "Zapisałem nowy plik źródłowy: %s (size=%s bytes)", new_source_path, new_source_path.stat().st_size
        )

        # Podmień ścieżkę dokumentu w store na nową wersję
        metadata.path = str(new_source_path)

        # Usuń stary plik źródłowy (jeśli istnieje i jest inny)
        old_deleted = False
        old_delete_error = None
        try:
            if original_path.exists() and original_path.resolve() != new_source_path.resolve():
                try:
                    original_path.unlink()
                    old_deleted = True
                    current_app.logger.info("Usunąłem stary plik źródłowy: %s", original_path)
                except Exception as unlink_exc:
                    old_delete_error = str(unlink_exc)
                    current_app.logger.warning(
                        "Nie udało się usunąć starego pliku %s: %s", original_path, unlink_exc, exc_info=unlink_exc
                    )
        except Exception as exists_exc:
            # Problem z sprawdzeniem istnienia pliku
            old_delete_error = str(exists_exc)
            current_app.logger.warning("Błąd podczas sprawdzania starego pliku: %s", exists_exc, exc_info=exists_exc)

        new_size_kb = new_source_path.stat().st_size / 1024
        backup_size_kb = backup_path.stat().st_size / 1024
    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception("Nie udało się nadpisać oryginału", exc_info=exc)
        return jsonify({"success": False, "error": "Nie udało się zapisać nowej wersji pliku."}), 500

    # Przepisz render podglądu, aby UI widziało nową wersję
    # Użyj DPI z metadanych jeśli dostępne, w przeciwnym razie domyślne 300.
    render_dpi = metadata.dpi or 300
    rendered = render_image_page(
        Path(metadata.path),
        token,
        upload_folder,
        dpi=render_dpi,
        baseline_dpi=render_dpi,
        force=True,
    )

    rendered_path = upload_folder / rendered.filename
    rendered_exists = rendered_path.exists()
    rendered_size_kb = rendered_path.stat().st_size / 1024 if rendered_exists else None

    current_app.logger.info(
        "Rendered preview: %s exists=%s size_kb=%s", rendered_path, rendered_exists, rendered_size_kb
    )

    backup_url = url_for("core.serve_upload", filename=f"backups/{backup_filename}")
    preview_url = url_for("core.serve_upload", filename=rendered.filename)
    return jsonify(
        {
            "success": True,
            "backup_filename": backup_filename,
            "backup_url": backup_url,
            "original_filename": Path(metadata.path).name,
            "new_size_kb": round(new_size_kb, 2),
            "backup_size_kb": round(backup_size_kb, 2),
            "rendered_filename": rendered.filename,
            "rendered_dpi": render_dpi,
            "preview_url": preview_url,
            "new_source_path": str(new_source_path),
            "new_source_exists": True,
            "new_source_size_kb": round(new_size_kb, 2),
            "rendered_exists": rendered_exists,
            "rendered_size_kb": round(rendered_size_kb, 2) if rendered_size_kb is not None else None,
            "old_source_path": str(original_path),
            "old_source_existed": original_path.exists(),
            "old_source_deleted": old_deleted,
            "old_source_delete_error": old_delete_error,
        }
    )
