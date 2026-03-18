from __future__ import annotations

import uuid
from pathlib import Path

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    fitz = None  # type: ignore
try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # pragma: no cover - optional dependency
    Image = None  # type: ignore
    UnidentifiedImageError = None  # type: ignore
from flask import Blueprint, current_app, jsonify, request, url_for
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from ..pdf_store import PdfDocument, PdfStore
from ..services.pdf_renderer import RenderedPage, render_image_page, render_pdf_page

pdf_bp = Blueprint("pdf", __name__)

ALLOWED_PDF_EXTENSIONS = {".pdf"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
ALLOWED_EXTENSIONS = ALLOWED_PDF_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS
DEFAULT_PREVIEW_DPI = 300
DEFAULT_IMAGE_DPI = DEFAULT_PREVIEW_DPI
MIN_RENDER_DPI = 72
MAX_RENDER_DPI = 1200
# Maximum allowed width/height in pixels for preview renders to avoid creating huge bitmaps
DEFAULT_MAX_PREVIEW_PX = 10000


def _get_pdf_store() -> PdfStore:
    return current_app.extensions["pdf_store"]


def _normalize_dpi(raw_value: int | None) -> int:
    if raw_value is None or raw_value <= 0:
        return DEFAULT_PREVIEW_DPI
    return max(MIN_RENDER_DPI, min(MAX_RENDER_DPI, raw_value))


def _build_page_payload(rendered: RenderedPage) -> dict[str, float | int | str]:
    """Build base payload from a RenderedPage. Additional fields like
    requested_dpi, applied_dpi and clamped may be added by the caller.
    """
    return {
        "image_url": url_for("core.serve_upload", filename=rendered.filename),
        "image_dpi": rendered.dpi,
        "image_width_px": rendered.width_px,
        "image_height_px": rendered.height_px,
        "page_width_in": rendered.width_in,
        "page_height_in": rendered.height_in,
        "max_render_dpi": MAX_RENDER_DPI,
        "min_render_dpi": MIN_RENDER_DPI,
    }


def _is_pdf_extension(ext: str) -> bool:
    return ext in ALLOWED_PDF_EXTENSIONS


def _is_image_extension(ext: str) -> bool:
    return ext in ALLOWED_IMAGE_EXTENSIONS


def _get_max_preview_pixels() -> int:
    # Allow overriding the server-wide maximum preview pixels via config
    return int(current_app.config.get("MAX_PREVIEW_PIXELS", DEFAULT_MAX_PREVIEW_PX))


def _compute_max_dpi_for_pdf(pdf_path: Path, page_num: int) -> int:
    """Compute maximum DPI for a PDF page so that no side exceeds the
    configured maximum pixel dimension. Returns an integer DPI clamped to
    MIN_RENDER_DPI..MAX_RENDER_DPI.
    """
    max_px = _get_max_preview_pixels()
    try:
        with fitz.open(pdf_path) as doc:
            if page_num < 1 or page_num > doc.page_count:
                return MAX_RENDER_DPI
            page = doc.load_page(page_num - 1)
            rect = page.rect
            width_in = rect.width / 72.0
            height_in = rect.height / 72.0
            max_in = max(width_in, height_in)
            if max_in <= 0:
                return MAX_RENDER_DPI
            dpi_by_px = int(max_px // max_in)
            return max(MIN_RENDER_DPI, min(MAX_RENDER_DPI, max(1, dpi_by_px)))
    except Exception:
        # On error be permissive and allow default max
        return MAX_RENDER_DPI


def _compute_max_dpi_for_image(image_path: Path, baseline_dpi: int) -> int:
    """Compute max DPI for an image-based page (raster) by using its
    intrinsic size and baseline DPI."""
    max_px = _get_max_preview_pixels()
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            source_width, source_height = img.size
            page_width_in = source_width / baseline_dpi
            page_height_in = source_height / baseline_dpi
            max_in = max(page_width_in, page_height_in)
            if max_in <= 0:
                return MAX_RENDER_DPI
            dpi_by_px = int(max_px // max_in)
            return max(MIN_RENDER_DPI, min(MAX_RENDER_DPI, max(1, dpi_by_px)))
    except Exception:
        return MAX_RENDER_DPI


@pdf_bp.get("/uploads/list")
def list_uploads():  # type: ignore[override]
    upload_folder: Path = current_app.config["UPLOAD_FOLDER"]
    files = []
    thumbs_dir = upload_folder / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    try:
        for p in sorted(upload_folder.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.is_file():
                name = p.name
                # skip backups and processed/retouch folders
                if name.startswith(".") or p.parent.name in ("backups", "processed", "retouch"):
                    continue
                file_entry = {
                    "name": name,
                    "size_kb": round(p.stat().st_size / 1024, 2),
                    "mtime": p.stat().st_mtime,
                    "url": url_for("core.serve_upload", filename=name),
                }
                # Generate thumbnail for images if possible
                try:
                    ext = p.suffix.lower()
                    if ext in ALLOWED_IMAGE_EXTENSIONS and Image is not None:
                        thumb_name = f"{name}.thumb.png"
                        thumb_path = thumbs_dir / thumb_name
                        if not thumb_path.exists():
                            try:
                                with Image.open(p) as img:
                                    img.thumbnail((200, 200))
                                    img.save(thumb_path, format="PNG")
                            except Exception:
                                current_app.logger.exception("Failed to create thumbnail for %s", p)
                        if thumb_path.exists():
                            file_entry["thumb_url"] = url_for("core.serve_upload", filename=f"thumbs/{thumb_name}")
                except Exception:
                    current_app.logger.exception("Error while preparing thumbnail", exc_info=True)
                files.append(file_entry)
    except Exception as exc:  # pragma: no cover - best effort
        current_app.logger.exception("Failed to list uploads", exc_info=exc)
        return jsonify({"files": []})
    # format mtime into iso for readability
    for f in files:
        try:
            from datetime import datetime

            f["mtime"] = datetime.fromtimestamp(f["mtime"]).isoformat(sep=" ", timespec="seconds")
        except Exception:
            pass
    return jsonify({"files": files})


@pdf_bp.get("/uploads/load/<path:filename>")
def load_from_uploads(filename: str):  # type: ignore[override]
    upload_folder: Path = current_app.config["UPLOAD_FOLDER"]
    # prevent path traversal
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        return jsonify({"error": "Invalid filename"}), 400

    candidate = (upload_folder / filename).resolve()
    try:
        if not candidate.exists() or not str(candidate).startswith(str(upload_folder.resolve())):
            return jsonify({"error": "File not found"}), 404
    except Exception:
        return jsonify({"error": "Invalid file path"}), 400

    ext = candidate.suffix.lower()
    if _is_image_extension(ext):
        # create token and render image page
        token = uuid.uuid4().hex
        try:
            rendered = render_image_page(
                candidate, token, upload_folder, dpi=DEFAULT_PREVIEW_DPI, baseline_dpi=DEFAULT_PREVIEW_DPI, force=True
            )
        except Exception as exc:
            current_app.logger.exception("Failed to render image from uploads", exc_info=exc)
            return jsonify({"error": "Failed to render image"}), 500
        store = _get_pdf_store()
        store.add(
            token,
            PdfDocument(
                path=str(candidate),
                total_pages=1,
                name=filename,
                kind="image",
                dpi=rendered.dpi,
                width_px=rendered.width_px,
                height_px=rendered.height_px,
            ),
        )
        payload = {"token": token, "page": 1, "total_pages": 1, "filename": filename}
        payload.update(
            {
                "image_url": url_for("core.serve_upload", filename=rendered.filename),
                "image_dpi": rendered.dpi,
                "image_width_px": rendered.width_px,
                "image_height_px": rendered.height_px,
            }
        )
        return jsonify(payload)
    elif _is_pdf_extension(ext):
        # register pdf token and render first page
        if fitz is None:
            return jsonify({"error": "PyMuPDF not available"}), 503
        token = uuid.uuid4().hex
        pdf_path = candidate
        try:
            with fitz.open(pdf_path) as document:
                total_pages = document.page_count
        except Exception as exc:
            current_app.logger.exception("Failed to open pdf from uploads", exc_info=exc)
            return jsonify({"error": "Invalid PDF file"}), 400
        store = _get_pdf_store()
        store.add(token, PdfDocument(path=str(pdf_path), total_pages=total_pages, name=filename, kind="pdf"))
        try:
            rendered = render_pdf_page(
                pdf_path, 1, token, upload_folder, dpi=DEFAULT_PREVIEW_DPI, baseline_dpi=DEFAULT_PREVIEW_DPI
            )
        except RuntimeError:
            return _pymupdf_unavailable_response()
        payload = {"token": token, "page": 1, "total_pages": total_pages, "filename": filename}
        payload.update(_build_page_payload(rendered))
        return jsonify(payload)
    else:
        return jsonify({"error": "Unsupported file type"}), 400


def _extract_image_dpi(image: Image.Image) -> int:
    raw_dpi = image.info.get("dpi") if hasattr(image, "info") else None
    if isinstance(raw_dpi, (list, tuple)) and raw_dpi:
        try:
            dpi_value = int(round(raw_dpi[0]))
            if dpi_value > 0:
                return dpi_value
        except (TypeError, ValueError):
            pass
    if isinstance(raw_dpi, (int, float)) and raw_dpi > 0:
        return int(round(raw_dpi))
    return DEFAULT_IMAGE_DPI


def _validate_upload(file: FileStorage | None):
    if file is None:
        return "No file part"

    filename = secure_filename(file.filename or "")
    if not filename:
        return "No selected file"

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return "Nieobsługiwany typ pliku. Dozwolone: PDF, PNG, JPG, WEBP, TIFF, BMP."

    return None


def _pymupdf_unavailable_response():
    return (
        jsonify({"error": "PyMuPDF (fitz) nie jest dostępny na serwerze"}),
        503,
    )


def _pillow_unavailable_response():
    return (
        jsonify({"error": "Pillow (PIL) nie jest dostępny na serwerze"}),
        503,
    )


def _handle_pdf_upload(file: FileStorage, filename: str, upload_folder: Path):
    if fitz is None:
        return _pymupdf_unavailable_response()

    token = uuid.uuid4().hex
    stored_filename = f"{token}.pdf"
    pdf_path = upload_folder / stored_filename
    file.save(pdf_path)

    with fitz.open(pdf_path) as document:
        total_pages = document.page_count

    store = _get_pdf_store()
    store.add(
        token,
        PdfDocument(path=str(pdf_path), total_pages=total_pages, name=filename, kind="pdf"),
    )

    try:
        # Compute applied DPI with pixel-based clamping to protect the server
        requested = DEFAULT_PREVIEW_DPI
        normalized = _normalize_dpi(requested)
        max_allowed = _compute_max_dpi_for_pdf(pdf_path, 1)
        applied_dpi = min(normalized, max_allowed)
        clamped = applied_dpi != requested

        rendered = render_pdf_page(
            pdf_path,
            1,
            token,
            upload_folder,
            dpi=applied_dpi,
            baseline_dpi=DEFAULT_PREVIEW_DPI,
        )
    except RuntimeError:
        return _pymupdf_unavailable_response()

    payload = {
        "token": token,
        "page": 1,
        "total_pages": total_pages,
        "filename": filename,
    }
    payload.update(_build_page_payload(rendered))
    payload.update({"requested_dpi": requested, "applied_dpi": rendered.dpi, "clamped": clamped})

    return jsonify(payload)


def _handle_image_upload(file: FileStorage, filename: str, upload_folder: Path):
    if Image is None or UnidentifiedImageError is None:
        return _pillow_unavailable_response()

    ext = Path(filename).suffix.lower()
    token = uuid.uuid4().hex
    source_filename = f"{token}_source{ext}"
    source_path = upload_folder / source_filename

    try:
        file.save(source_path)
        with Image.open(source_path) as img:
            img.load()
            baseline_dpi = _normalize_dpi(_extract_image_dpi(img))
    except UnidentifiedImageError:
        source_path.unlink(missing_ok=True)
        return jsonify({"error": "Nieprawidłowy plik graficzny"}), 400
    except Exception:
        current_app.logger.exception("Nie udało się przetworzyć przesłanego obrazu")
        source_path.unlink(missing_ok=True)
        return jsonify({"error": "Nie udało się wczytać pliku graficznego"}), 400

    try:
        rendered = render_image_page(
            source_path,
            token,
            upload_folder,
            dpi=baseline_dpi,
            baseline_dpi=baseline_dpi,
            force=True,
        )
    except RuntimeError:
        source_path.unlink(missing_ok=True)
        return _pillow_unavailable_response()
    except ValueError:
        source_path.unlink(missing_ok=True)
        return jsonify({"error": "Unable to render page"}), 400

    store = _get_pdf_store()
    store.add(
        token,
        PdfDocument(
            path=str(source_path),
            total_pages=1,
            name=filename,
            kind="image",
            dpi=baseline_dpi,
            width_px=rendered.width_px,
            height_px=rendered.height_px,
        ),
    )

    payload = {
        "token": token,
        "page": 1,
        "total_pages": 1,
        "filename": filename,
    }
    payload.update(_build_page_payload(rendered))

    return jsonify(payload)


@pdf_bp.post("/upload")
def upload_file():
    upload_folder: Path = current_app.config["UPLOAD_FOLDER"]
    file = request.files.get("file")
    error = _validate_upload(file)
    if error:
        return jsonify({"error": error})

    assert file is not None  # for type-checkers
    filename = secure_filename(file.filename or "")
    ext = Path(filename).suffix.lower()

    if _is_pdf_extension(ext):
        return _handle_pdf_upload(file, filename, upload_folder)
    if _is_image_extension(ext):
        return _handle_image_upload(file, filename, upload_folder)

    return jsonify({"error": "Nieobsługiwany typ pliku"}), 400


@pdf_bp.get("/page/<token>/<int:page_num>")
def get_page(token: str, page_num: int):  # type: ignore[override]
    store = _get_pdf_store()
    metadata = store.get(token)
    if metadata is None:
        return jsonify({"error": "Unknown document"}), 404

    document_path = Path(metadata.path)
    if not document_path.exists():
        store.remove(token)
        return jsonify({"error": "Document unavailable"}), 404

    if page_num < 1 or page_num > metadata.total_pages:
        return jsonify({"error": "Page out of range"}), 400

    upload_folder: Path = current_app.config["UPLOAD_FOLDER"]

    if metadata.kind == "image":
        baseline_dpi = metadata.dpi or DEFAULT_IMAGE_DPI
        try:
            requested = baseline_dpi
            normalized = _normalize_dpi(requested)
            max_allowed = _compute_max_dpi_for_image(document_path, baseline_dpi)
            applied_dpi = min(normalized, max_allowed)
            clamped = applied_dpi != requested

            rendered = render_image_page(
                document_path,
                token,
                upload_folder,
                dpi=applied_dpi,
                baseline_dpi=baseline_dpi,
            )
        except RuntimeError:
            return _pillow_unavailable_response()
        except ValueError:
            return jsonify({"error": "Unable to render page"}), 400
    else:
        try:
            requested = DEFAULT_PREVIEW_DPI
            normalized = _normalize_dpi(requested)
            max_allowed = _compute_max_dpi_for_pdf(document_path, page_num)
            applied_dpi = min(normalized, max_allowed)
            clamped = applied_dpi != requested

            rendered = render_pdf_page(
                document_path,
                page_num,
                token,
                upload_folder,
                dpi=applied_dpi,
                baseline_dpi=DEFAULT_PREVIEW_DPI,
            )
        except RuntimeError:
            return _pymupdf_unavailable_response()
        except ValueError:
            return jsonify({"error": "Unable to render page"}), 400

    payload = {
        "page": page_num,
        "total_pages": metadata.total_pages,
    }
    payload.update(_build_page_payload(rendered))
    payload.update({"requested_dpi": requested, "applied_dpi": rendered.dpi, "clamped": clamped})
    return jsonify(payload)


@pdf_bp.get("/page/<token>/<int:page_num>/export")
def export_page(token: str, page_num: int):  # type: ignore[override]
    store = _get_pdf_store()
    metadata = store.get(token)
    if metadata is None:
        return jsonify({"error": "Unknown document"}), 404

    document_path = Path(metadata.path)
    if not document_path.exists():
        store.remove(token)
        return jsonify({"error": "Document unavailable"}), 404

    if page_num < 1 or page_num > metadata.total_pages:
        return jsonify({"error": "Page out of range"}), 400

    dpi_param = request.args.get("dpi", type=int)
    requested_dpi = dpi_param if dpi_param is not None else DEFAULT_PREVIEW_DPI
    normalized = _normalize_dpi(dpi_param)

    # Compute pixel-based clamping limit
    if metadata.kind == "image":
        baseline_dpi = metadata.dpi or DEFAULT_IMAGE_DPI
        max_allowed = _compute_max_dpi_for_image(document_path, baseline_dpi)
    else:
        max_allowed = _compute_max_dpi_for_pdf(document_path, page_num)

    applied_dpi = min(normalized, max_allowed)
    clamped = requested_dpi is not None and applied_dpi != requested_dpi

    force = request.args.get("force", "0").lower() in {"1", "true", "yes"}

    upload_folder: Path = current_app.config["UPLOAD_FOLDER"]

    if metadata.kind == "image":
        baseline_dpi = metadata.dpi or DEFAULT_IMAGE_DPI
        try:
            rendered = render_image_page(
                document_path,
                token,
                upload_folder,
                dpi=applied_dpi,
                baseline_dpi=baseline_dpi,
                force=force,
            )
        except RuntimeError:
            return _pillow_unavailable_response()
        except ValueError:
            return jsonify({"error": "Unable to render page"}), 400
    else:
        try:
            rendered = render_pdf_page(
                document_path,
                page_num,
                token,
                upload_folder,
                dpi=applied_dpi,
                baseline_dpi=DEFAULT_PREVIEW_DPI,
                force=force,
            )
        except RuntimeError:
            return _pymupdf_unavailable_response()
        except ValueError:
            return jsonify({"error": "Unable to render page"}), 400

    download_url = url_for("core.serve_upload", filename=rendered.filename)
    response_payload = {
        "download_url": download_url,
        "filename": rendered.filename,
        "image_dpi": rendered.dpi,
        "image_width_px": rendered.width_px,
        "image_height_px": rendered.height_px,
        "page": page_num,
        "total_pages": metadata.total_pages,
        "max_render_dpi": MAX_RENDER_DPI,
        "min_render_dpi": MIN_RENDER_DPI,
        "requested_dpi": requested_dpi,
        "applied_dpi": rendered.dpi,
        "clamped": clamped,
    }
    if clamped:
        response_payload["clamped_dpi"] = rendered.dpi

    return jsonify(response_payload)
