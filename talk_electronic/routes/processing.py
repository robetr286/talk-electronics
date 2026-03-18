from __future__ import annotations

import base64
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

import cv2
import numpy as np
from flask import Blueprint, current_app, jsonify, request, url_for
from PIL import Image
from werkzeug.utils import secure_filename

from ..services.deskew import deskew_image as deskew_image_func
from ..services.processing_history import ProcessingHistoryStore
from ..services.retouch_buffer import RetouchBuffer

processing_bp = Blueprint("processing", __name__, url_prefix="/processing")

JsonDict = Dict[str, Any]


def _history_store() -> ProcessingHistoryStore:
    return current_app.extensions["processing_history"]


def _upload_folder() -> Path:
    return current_app.config["UPLOAD_FOLDER"]


def _processed_folder() -> Path:
    return current_app.config["PROCESSED_FOLDER"]


def _retouch_folder() -> Path:
    return current_app.config["RETOUCH_FOLDER"]


def _retouch_buffer() -> RetouchBuffer:
    return current_app.extensions["retouch_buffer"]


def _sanitize_entry(entry: JsonDict) -> JsonDict:
    cleaned = dict(entry)
    cleaned.pop("objectUrl", None)
    meta = cleaned.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}
    if "createdAt" not in meta:
        meta["createdAt"] = datetime.now(timezone.utc).isoformat()
    cleaned["meta"] = meta
    storage = cleaned.get("storage")
    if storage is not None and not isinstance(storage, dict):
        cleaned["storage"] = {}
    return cleaned


def _delete_entry_file(entry: JsonDict) -> bool:
    storage = entry.get("storage")
    if not isinstance(storage, dict):
        return False
    filename = storage.get("filename")
    if not isinstance(filename, str) or not filename:
        return False
    target = (_upload_folder() / filename).resolve()
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False


def _json_list_response(entries: Iterable[JsonDict]):
    return jsonify({"entries": list(entries)})


def _normalize_types_param(raw_values: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for value in raw_values:
        if not value:
            continue
        token = value.strip()
        if token:
            normalized.add(token)
    return normalized


def _resolve_scope_types(scope: str | None) -> set[str] | None:
    if not scope:
        return None
    normalized = scope.strip().lower()
    scope_map = {
        "image-processing": {"crop", "upload", "processed", "page", "retouch"},
        "symbol-detection": {"symbol-detection"},
        "line-segmentation": {"line-segmentation", "netlist", "spice-netlist"},
    }
    return scope_map.get(normalized)


@processing_bp.get("/history")
def list_history():  # type: ignore[override]
    store = _history_store()
    entries = store.list_entries()

    type_filters = _normalize_types_param(request.args.getlist("type"))
    csv_param = request.args.get("types")
    if csv_param:
        type_filters.update(_normalize_types_param(csv_param.split(",")))

    scope_types = _resolve_scope_types(request.args.get("scope"))
    allowed_types: set[str] | None = None
    if scope_types:
        allowed_types = set(scope_types)
    if type_filters:
        allowed_types = type_filters if allowed_types is None else allowed_types.intersection(type_filters)

    if allowed_types is not None:
        entries = [entry for entry in entries if entry.get("type") in allowed_types]

    return _json_list_response(entries)


@processing_bp.post("/history")
def upsert_history_entry():  # type: ignore[override]
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400

    entry = _sanitize_entry(payload)
    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not entry_id:
        entry["id"] = f"manual-{uuid.uuid4().hex}"

    if "label" not in entry:
        entry["label"] = "Fragment schematu"

    store = _history_store()
    saved = store.upsert_entry(entry)
    return jsonify({"entry": saved}), 201


@processing_bp.delete("/history/<entry_id>")
def delete_history_entry(entry_id: str):  # type: ignore[override]
    store = _history_store()
    removed = store.remove_entry(entry_id)
    if removed is None:
        return jsonify({"error": "Entry not found"}), 404
    file_removed = _delete_entry_file(removed)
    return jsonify({"success": True, "file_removed": file_removed})


@processing_bp.delete("/history")
def clear_history():  # type: ignore[override]
    store = _history_store()

    type_filters = _normalize_types_param(request.args.getlist("type"))
    csv_param = request.args.get("types")
    if csv_param:
        type_filters.update(_normalize_types_param(csv_param.split(",")))
    scope_types = _resolve_scope_types(request.args.get("scope"))

    allowed_types: set[str] | None = None
    if scope_types:
        allowed_types = set(scope_types)
    if type_filters:
        allowed_types = type_filters if allowed_types is None else allowed_types.intersection(type_filters)

    if allowed_types is None:
        removed_entries = store.clear()
    else:
        existing_entries = store.list_entries()
        target_ids = [entry.get("id") for entry in existing_entries if entry.get("type") in allowed_types]
        removed_entries = store.remove_entries(target_ids)

    deleted_files = sum(1 for entry in removed_entries if _delete_entry_file(entry))
    return jsonify({"success": True, "removed": len(removed_entries), "files_removed": deleted_files})


def _allowed_extension(filename: str) -> bool:
    allowed = {".png", ".jpg", ".jpeg", ".webp"}
    suffix = Path(filename).suffix.lower()
    return suffix in allowed or suffix == ""


def _build_import_entry(file_path: Path, original_name: str) -> JsonDict:
    created_at = datetime.now(timezone.utc).isoformat()
    size_kb = round(file_path.stat().st_size / 1024, 2)
    safe_name = original_name or "Fragment obrazu"
    label = f"{safe_name} ({size_kb} KB)"
    filename = file_path.name
    entry = {
        "id": f"upload-{uuid.uuid4().hex}",
        "url": url_for("core.serve_upload", filename=filename),
        "label": label,
        "type": "upload",
        "meta": {
            "createdAt": created_at,
            "typeLabel": "Import z dysku",
            "filename": safe_name,
            "sizeKb": size_kb,
        },
        "storage": {
            "type": "upload",
            "filename": filename,
        },
        "payload": {
            "filename": filename,
            "originalName": safe_name,
            "sizeBytes": file_path.stat().st_size,
        },
    }
    return entry


@processing_bp.post("/import")
def import_fragment():  # type: ignore[override]
    file_storage = request.files.get("file")
    if file_storage is None or not file_storage.filename:
        return jsonify({"error": "Brak pliku"}), 400

    if not _allowed_extension(file_storage.filename):
        return jsonify({"error": "Nieobsługiwany format pliku"}), 400

    safe_name = secure_filename(file_storage.filename)
    suffix = Path(safe_name).suffix.lower() or ".png"
    stored_filename = f"import_{uuid.uuid4().hex}{suffix}"
    destination = _upload_folder() / stored_filename
    file_storage.save(destination)

    entry = _build_import_entry(destination, file_storage.filename)
    store = _history_store()
    store.upsert_entry(entry)
    return jsonify({"entry": entry}), 201


def _parse_metadata(raw: str | None) -> JsonDict:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_processed_entry(file_path: Path, metadata: JsonDict) -> JsonDict:
    created_at = metadata.get("createdAt")
    if not isinstance(created_at, str) or not created_at:
        created_at = datetime.utcnow().isoformat()

    try:
        created_dt = datetime.fromisoformat(created_at)
        human_time = created_dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        human_time = created_at

    relative_path = file_path.relative_to(_upload_folder())
    size_kb = round(file_path.stat().st_size / 1024, 2)
    meta = metadata.get("meta") if isinstance(metadata.get("meta"), dict) else {}
    meta = {**meta}
    meta.setdefault("createdAt", created_at)
    meta.setdefault("typeLabel", "Wynik obróbki")
    meta["sizeKb"] = size_kb
    if "filter" not in meta and isinstance(metadata.get("filter"), str):
        meta["filter"] = metadata["filter"]
    if "threshold" not in meta and isinstance(metadata.get("threshold"), (int, float)):
        meta["threshold"] = metadata["threshold"]
    if "thresholdLabel" not in meta and isinstance(metadata.get("thresholdLabel"), str):
        meta["thresholdLabel"] = metadata["thresholdLabel"]
    if "filterKey" not in meta and isinstance(metadata.get("filterKey"), str):
        meta["filterKey"] = metadata["filterKey"]
    if "sourceId" not in meta and isinstance(metadata.get("sourceId"), str):
        meta["sourceId"] = metadata["sourceId"]

    stats = metadata.get("stats") if isinstance(metadata.get("stats"), dict) else None

    entry = {
        "id": f"processed-{uuid.uuid4().hex}",
        "url": url_for("core.serve_upload", filename=relative_path.as_posix()),
        "label": f"Wynik obróbki ({human_time})",
        "type": "processed",
        "meta": meta,
        "storage": {
            "type": "processed",
            "filename": relative_path.as_posix(),
        },
        "payload": {
            "sourceId": metadata.get("sourceId"),
            "stats": stats,
        },
    }
    if stats is not None:
        entry["stats"] = stats
    return entry


@processing_bp.post("/save-result")
def save_processed_result():  # type: ignore[override]
    file_storage = request.files.get("file")
    if file_storage is None:
        return jsonify({"error": "Brak pliku do zapisania"}), 400

    metadata = _parse_metadata(request.form.get("metadata"))

    processed_dir = _processed_folder()
    processed_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = processed_dir / f"processed_{uuid.uuid4().hex}.png"
    file_storage.save(stored_filename)

    entry = _build_processed_entry(stored_filename, metadata)
    store = _history_store()
    store.upsert_entry(entry)
    return jsonify({"entry": entry}), 201


def _build_retouch_entry(file_path: Path, metadata: JsonDict) -> JsonDict:
    created_at = metadata.get("createdAt")
    if not isinstance(created_at, str) or not created_at:
        created_at = datetime.utcnow().isoformat()

    try:
        created_dt = datetime.fromisoformat(created_at)
        human_time = created_dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        human_time = created_at

    relative_path = file_path.relative_to(_upload_folder())
    size_kb = round(file_path.stat().st_size / 1024, 2)

    meta = metadata.get("meta") if isinstance(metadata.get("meta"), dict) else {}
    meta = {**meta}
    meta.setdefault("createdAt", created_at)
    meta.setdefault("typeLabel", "Materiał do retuszu")
    meta["sizeKb"] = size_kb

    if "sourceId" not in meta and isinstance(metadata.get("sourceId"), str):
        meta["sourceId"] = metadata["sourceId"]
    if "processedId" not in meta and isinstance(metadata.get("processedId"), str):
        meta["processedId"] = metadata["processedId"]
    if "filter" not in meta and isinstance(metadata.get("filter"), str):
        meta["filter"] = metadata["filter"]
    if "threshold" not in meta and isinstance(metadata.get("threshold"), (int, float)):
        meta["threshold"] = metadata["threshold"]
    if "thresholdLabel" not in meta and isinstance(metadata.get("thresholdLabel"), str):
        meta["thresholdLabel"] = metadata["thresholdLabel"]

    stats = metadata.get("stats") if isinstance(metadata.get("stats"), dict) else None

    entry = {
        "id": f"retouch-{uuid.uuid4().hex}",
        "url": url_for("core.serve_upload", filename=relative_path.as_posix()),
        "label": f"Retusz ({human_time})",
        "type": "retouch-source",
        "meta": meta,
        "storage": {
            "type": "retouch",
            "filename": relative_path.as_posix(),
        },
        "payload": {
            "sourceId": metadata.get("sourceId"),
            "processedId": metadata.get("processedId"),
            "stats": stats,
        },
    }
    if stats is not None:
        entry["stats"] = stats
    return entry


@processing_bp.post("/send-to-retouch")
def send_to_retouch():  # type: ignore[override]
    file_storage = request.files.get("file")
    if file_storage is None:
        return jsonify({"error": "Brak pliku"}), 400

    filename = file_storage.filename or "retouch.png"
    if not _allowed_extension(filename):
        return jsonify({"error": "Nieobsługiwany format pliku"}), 400

    metadata = _parse_metadata(request.form.get("metadata"))

    safe_name = secure_filename(filename)
    suffix = Path(safe_name).suffix.lower() or ".png"
    retouch_dir = _retouch_folder()
    retouch_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = retouch_dir / f"retouch_{uuid.uuid4().hex}{suffix}"
    file_storage.save(stored_filename)

    # Odczytaj plik i zakoduj na base64, aby gwarantować dostępność
    try:
        with open(stored_filename, "rb") as f:
            image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode("utf-8")
        data_url = f"data:image/png;base64,{image_base64}"
    except Exception as e:
        current_app.logger.error(f"Błąd kodowania obrazu na base64: {e}")
        data_url = None

    entry = _build_retouch_entry(stored_filename, metadata)
    # Jeśli udało się zakodować, zwróć `dataUrl` jako główne źródło (`url`) i
    # zachowaj oryginalny adres serwera w `serverUrl`.
    # Dzięki temu front-end będzie preferował dataUrl i nie będzie próbować
    # pobierać plików z /uploads/*, co wcześniej powodowało 404.
    if data_url:
        entry["dataUrl"] = data_url
        # przenieś oryginalny adres serwera do serverUrl (zachowujemy dla pobierania/diagnozy)
        if isinstance(entry.get("url"), str) and entry.get("url"):
            entry["serverUrl"] = entry["url"]
        entry["url"] = data_url

    buffer = _retouch_buffer()
    previous = buffer.get_entry()
    buffer.set_entry(entry)
    if previous:
        _delete_entry_file(previous)
    return jsonify({"entry": entry}), 201


@processing_bp.get("/retouch-buffer")
def get_retouch_buffer():  # type: ignore[override]
    entry = _retouch_buffer().get_entry()
    if not entry:
        return jsonify({"error": "Brak materiału do retuszu"}), 404
    return jsonify({"entry": entry})


@processing_bp.delete("/retouch-buffer")
def clear_retouch_buffer():  # type: ignore[override]
    buffer = _retouch_buffer()
    entry = buffer.get_entry()
    buffer.clear()
    if entry:
        _delete_entry_file(entry)
    return jsonify({"success": True})


def _decode_base64_image(data_url: str) -> np.ndarray | None:
    """Dekoduje base64 data URL do numpy array (OpenCV format)."""
    try:
        if "," in data_url:
            header, encoded = data_url.split(",", 1)
        else:
            encoded = data_url
        img_bytes = base64.b64decode(encoded)
        img = Image.open(io.BytesIO(img_bytes))
        # Konwersja do RGB jeśli potrzeba
        if img.mode != "RGB":
            img = img.convert("RGB")
        # OpenCV używa BGR
        img_array = np.array(img)
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        return img_bgr
    except Exception as e:
        current_app.logger.error(f"Błąd dekodowania obrazu base64: {e}")
        return None


def _apply_remove_small_objects(img: np.ndarray, min_size: int = 100) -> np.ndarray:
    """Usuwa małe izolowane obiekty (connected components)."""
    # Konwersja do grayscale jeśli trzeba
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Binaryzacja
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

    # Znajdź komponenty
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

    # Utwórz maskę - zachowaj tylko duże komponenty
    mask = np.zeros_like(binary)
    for i in range(1, num_labels):  # Pomijamy tło (0)
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= min_size:
            mask[labels == i] = 255

    return mask


def _apply_morphology_opening(img: np.ndarray, kernel_size: int = 3) -> np.ndarray:
    """Morfologia: opening (erozja → dylatacja) - usuwa szumy."""
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    return opened


def _apply_morphology_closing(img: np.ndarray, kernel_size: int = 3) -> np.ndarray:
    """Morfologia: closing (dylatacja → erozja) - wypełnia dziury."""
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    return closed


def _apply_median_filter(img: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """Filtr medianowy - wygładza zachowując krawędzie."""
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # kernel_size musi być nieparzysty
    if kernel_size % 2 == 0:
        kernel_size += 1

    filtered = cv2.medianBlur(gray, kernel_size)
    return filtered


def _apply_advanced_denoise(img: np.ndarray, h: int = 10) -> np.ndarray:
    """Zaawansowane usuwanie szumów (fastNlMeansDenoising)."""
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    denoised = cv2.fastNlMeansDenoising(gray, None, h=h, templateWindowSize=7, searchWindowSize=21)
    return denoised


def _save_result_to_retouch_folder(img: np.ndarray) -> str:
    """Zapisuje obraz do folderu retouch i zwraca URL."""
    retouch_dir = _retouch_folder()
    retouch_dir.mkdir(parents=True, exist_ok=True)

    filename = f"auto_clean_{uuid.uuid4().hex}.png"
    file_path = retouch_dir / filename

    cv2.imwrite(str(file_path), img)

    relative_path = file_path.relative_to(_upload_folder())
    result_url = url_for("core.serve_upload", filename=relative_path.as_posix())
    return result_url


@processing_bp.post("/auto-clean")
def auto_clean():  # type: ignore[override]
    """Automatyczne czyszczenie artefaktów z obrazu."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Nieprawidłowy format danych"}), 400

    filter_type = payload.get("filterType")
    image_data = payload.get("imageData")
    params = payload.get("params", {})

    if not filter_type or not image_data:
        return jsonify({"error": "Brak wymaganych parametrów (filterType, imageData)"}), 400

    # Dekoduj obraz
    img = _decode_base64_image(image_data)
    if img is None:
        return jsonify({"error": "Nie można zdekodować obrazu"}), 400

    # Zastosuj wybrany filtr z parametrami użytkownika
    try:
        if filter_type == "remove-small":
            min_size = params.get("minSize", 100)
            current_app.logger.info(f"Applying remove-small with minSize={min_size}")
            result = _apply_remove_small_objects(img, min_size=min_size)
        elif filter_type == "morphology-open":
            kernel_size = params.get("kernelSize", 3)
            current_app.logger.info(f"Applying morphology-open with kernelSize={kernel_size}")
            result = _apply_morphology_opening(img, kernel_size=kernel_size)
        elif filter_type == "morphology-close":
            kernel_size = params.get("kernelSize", 3)
            current_app.logger.info(f"Applying morphology-close with kernelSize={kernel_size}")
            result = _apply_morphology_closing(img, kernel_size=kernel_size)
        elif filter_type == "median":
            kernel_size = params.get("kernelSize", 5)
            current_app.logger.info(f"Applying median filter with kernelSize={kernel_size}")
            result = _apply_median_filter(img, kernel_size=kernel_size)
        elif filter_type == "denoise":
            h = params.get("h", 10)
            current_app.logger.info(f"Applying denoise with h={h}")
            result = _apply_advanced_denoise(img, h=h)
        else:
            return jsonify({"error": f"Nieznany filtr: {filter_type}"}), 400

        # Zapisz wynik
        result_url = _save_result_to_retouch_folder(result)

        return (
            jsonify(
                {
                    "success": True,
                    "resultUrl": result_url,
                    "filter": filter_type,
                    "params": params,
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Błąd podczas automatycznego czyszczenia: {e}")
        return jsonify({"error": f"Błąd przetwarzania: {str(e)}"}), 500


# ============================================================================
# v7 - DESKEW ENDPOINT (Prostowanie obrazu)
# ============================================================================


def _load_image_from_url_or_file(image_source: str) -> np.ndarray | None:
    """Helper do wczytania obrazu z URL lub ścieżki pliku."""
    try:
        # Usuń parametry query string (np. ?v=timestamp)
        if "?" in image_source:
            image_source = image_source.split("?")[0]

        # Obsługa pełnych URL-i (http://...)
        if image_source.startswith("http://") or image_source.startswith("https://"):
            # Wyciągnij ścieżkę po domenie
            from urllib.parse import urlparse

            parsed = urlparse(image_source)
            image_source = parsed.path  # Teraz mamy /uploads/filename.png

        # Obsługa lokalnych ścieżek (zaczynających się od /)
        if image_source.startswith("/"):
            # Usuń leading /uploads/ jeśli istnieje
            if image_source.startswith("/uploads/"):
                # /uploads/processed/file.png -> processed/file.png
                # /uploads/retouch/file.png -> retouch/file.png
                # /uploads/file.png -> file.png
                relative_path = image_source[len("/uploads/") :]

                # Sprawdź w podfolderach
                if relative_path.startswith("processed/"):
                    filename = relative_path[len("processed/") :]
                    file_path = _processed_folder() / filename
                elif relative_path.startswith("retouch/"):
                    filename = relative_path[len("retouch/") :]
                    file_path = _retouch_folder() / filename
                else:
                    # Bezpośrednio w uploads (renderowane strony PDF)
                    filename = relative_path
                    file_path = _upload_folder() / filename
            else:
                # Ścieżka nie zaczyna się od /uploads/
                # Spróbuj wszystkich folderów
                filename = Path(image_source).name
                file_path = None
                for folder in [_upload_folder(), _processed_folder(), _retouch_folder()]:
                    candidate = folder / filename
                    if candidate.exists():
                        file_path = candidate
                        break

                if file_path is None:
                    current_app.logger.error(f"Nie znaleziono pliku: {filename}")
                    return None

            if not file_path.exists():
                current_app.logger.error(f"Plik nie istnieje: {file_path}")
                return None

            # Wczytaj obraz
            current_app.logger.info(f"Wczytywanie obrazu: {file_path}")
            img = cv2.imread(str(file_path))

            if img is None:
                current_app.logger.error(f"cv2.imread zwrócił None dla: {file_path}")
                return None

            return img
        else:
            current_app.logger.error(f"Nieobsługiwany format URL: {image_source}")
            return None

    except Exception as e:
        current_app.logger.error(f"Błąd wczytywania obrazu: {e}", exc_info=True)
        return None


def _save_deskew_result(image: np.ndarray) -> str:
    """Zapisz obraz do folderu retouch i zwróć URL."""
    filename = f"deskew-{uuid.uuid4().hex[:12]}.png"
    file_path = _retouch_folder() / filename
    cv2.imwrite(str(file_path), image)
    return url_for("static", filename=f"../uploads/retouch/{filename}")


@processing_bp.route("/deskew", methods=["POST"])
def deskew_endpoint():  # type: ignore[override]
    """
    Endpoint do prostowania przekrzywionego obrazu.

    Request JSON:
        - imageUrl: URL obrazu do analizy
        - manualAngle (opcjonalnie): Ręczny kąt obrotu (-45 do +45)

    Response JSON:
        - success: True/False
        - detectedAngle: Wykryty kąt przekrzywienia (stopnie)
        - correctionAngle: Zastosowany kąt korekcji
        - previewUrl: URL podglądu wyprostowanego obrazu
        - width: Szerokość wyniku (px)
        - height: Wysokość wyniku (px)
    """
    try:
        data = request.get_json() or {}
        current_app.logger.info("=" * 60)
        current_app.logger.info("DESKEW endpoint called")
        current_app.logger.info("=" * 60)

        image_url = data.get("imageUrl") or data.get("image_url")
        manual_angle = data.get("manualAngle") or data.get("manual_angle")

        current_app.logger.info(f"Image URL: {image_url}")
        current_app.logger.info(f"Manual angle: {manual_angle}")

        if not image_url and not data.get("imageData"):
            return jsonify({"error": "Brak parametru imageUrl lub imageData"}), 400

        # Wczytaj obraz — obsłuż również data URL (imageData)
        img = None
        if data.get("imageData"):
            img = _decode_base64_image(data.get("imageData"))
            current_app.logger.info("Deskew: użyto imageData (data URL) do wczytania obrazu")
        else:
            img = _load_image_from_url_or_file(image_url)

        if img is None:
            # Zwróć informację o nieudanym wczytaniu (w przypadku imageData nie ma sensu wypisywać URL)
            if data.get("imageData"):
                return jsonify({"error": "Nie można wczytać obrazu z imageData"}), 400
            else:
                return jsonify({"error": f"Nie można wczytać obrazu: {image_url}"}), 400

        # Prostowanie
        if manual_angle is not None:
            manual_angle = float(manual_angle)
            # Ogranicz do rozsądnego zakresu
            manual_angle = max(-45, min(45, manual_angle))

        rotated, correction_angle = deskew_image_func(img, manual_angle=manual_angle)

        # Zapisz wynik
        result_url = _save_deskew_result(rotated)

        detected = -correction_angle if manual_angle is None else manual_angle

        return (
            jsonify(
                {
                    "success": True,
                    "detectedAngle": round(detected, 2),
                    "correctionAngle": round(correction_angle, 2),
                    "previewUrl": result_url,
                    "width": int(rotated.shape[1]),
                    "height": int(rotated.shape[0]),
                    "mode": "manual" if manual_angle is not None else "auto",
                }
            ),
            200,
        )

    except Exception as e:
        try:
            current_app.logger.error(f"Błąd podczas deskew: {e}", exc_info=True)
        except Exception:
            import sys

            sys.stderr.buffer.write(b"Error in deskew endpoint (logger failed)\n")
        return jsonify({"error": f"Błąd prostowania: {str(e)}"}), 500
