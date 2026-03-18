from __future__ import annotations

import base64
import io
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

import cv2
import numpy as np
from flask import Blueprint, current_app, jsonify, request, url_for
from PIL import Image

from ..services.annotation_loader import detect_annotation_format, load_annotations, validate_coco_annotations
from ..services.ignore_store import IgnoreRegionStore
from ..services.processing_history import ProcessingHistoryStore
from ..services.symbol_detection import available_detectors, create_detector
from ..services.symbol_detection.base import DetectionResult, SymbolDetection, SymbolDetector
from ..utils.ignore_filter import filter_detections_by_polygons, filter_detections_with_mask

symbol_detection_bp = Blueprint("symbol_detection", __name__, url_prefix="/api/symbols")

JsonDict = Dict[str, Any]


def _history_store() -> ProcessingHistoryStore:
    return current_app.extensions["processing_history"]


def _upload_folder() -> Path:
    return current_app.config["UPLOAD_FOLDER"]


def _processed_folder() -> Path:
    return current_app.config["PROCESSED_FOLDER"]


def _detector_cache() -> Dict[str, SymbolDetector]:
    cache: Dict[str, SymbolDetector] = current_app.extensions.setdefault("symbol_detectors_cache", {})
    return cache


def _ignore_store() -> IgnoreRegionStore:
    return current_app.extensions["ignore_store"]


def _ignore_filter_threshold() -> float:
    value = current_app.config.get("IGNORE_FILTER_IOU", 0.3)
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 0.3


def _entry_timestamp(entry: JsonDict) -> str:
    for key in ("updatedAt", "createdAt"):
        stamp = entry.get(key)
        if isinstance(stamp, str):
            return stamp
    return ""


def _entry_image_shape(entry: JsonDict) -> tuple[int, int] | None:
    image_meta = entry.get("image") if isinstance(entry.get("image"), Mapping) else {}
    if not isinstance(image_meta, Mapping):
        return None
    try:
        height = int(image_meta.get("height"))
        width = int(image_meta.get("width"))
    except (TypeError, ValueError):
        return None
    if height <= 0 or width <= 0:
        return None
    return height, width


def _build_ignore_lookup(payload: JsonDict, source_context: JsonDict) -> JsonDict:
    lookup: JsonDict = {}

    entry_id = payload.get("ignoreEntryId")
    if entry_id:
        lookup["entryId"] = str(entry_id)

    history_ids = []
    for candidate in (
        payload.get("ignoreHistoryId"),
        payload.get("historyId"),
        source_context.get("historyId"),
        source_context.get("history_id"),
    ):
        if candidate not in (None, ""):
            history_ids.append(str(candidate))
    if history_ids:
        lookup["historyIds"] = set(history_ids)

    source_meta = payload.get("ignoreSource") if isinstance(payload.get("ignoreSource"), Mapping) else {}
    kind = source_meta.get("kind") or source_meta.get("type")
    if not kind:
        kind = payload.get("sourceKind") or payload.get("sourceType")
    if kind:
        lookup["sourceKind"] = str(kind)

    source_id = source_meta.get("id") or source_meta.get("sourceId")
    if not source_id:
        source_id = payload.get("sourceId") or payload.get("documentId")
    if source_id:
        lookup["sourceId"] = str(source_id)

    filenames = []
    for candidate in (payload.get("ignoreFilename"), source_context.get("filename")):
        if isinstance(candidate, str) and candidate:
            filenames.append(candidate)
    if filenames:
        lookup["filenames"] = set(filenames)

    image_urls = []
    for candidate in (payload.get("imageUrl"), source_context.get("imageUrl"), source_context.get("url")):
        if isinstance(candidate, str) and candidate:
            image_urls.append(candidate)
    if image_urls:
        lookup["imageUrls"] = set(image_urls)

    return lookup


def _score_ignore_entry(entry: JsonDict, lookup: JsonDict) -> int:
    score = 0
    history_ids = lookup.get("historyIds")
    image_meta = entry.get("image") if isinstance(entry.get("image"), Mapping) else {}
    entry_history = None
    if isinstance(image_meta, Mapping):
        raw_history = image_meta.get("historyId") or image_meta.get("history_id")
        if raw_history not in (None, ""):
            entry_history = str(raw_history)
    if history_ids and entry_history and entry_history in history_ids:
        score += 5

    source_meta = entry.get("source") if isinstance(entry.get("source"), Mapping) else {}
    if isinstance(source_meta, Mapping):
        target_kind = lookup.get("sourceKind")
        if target_kind and source_meta.get("kind") and str(source_meta.get("kind")).lower() == str(target_kind).lower():
            score += 2

        target_id = lookup.get("sourceId")
        if target_id and source_meta.get("id") and str(source_meta.get("id")) == str(target_id):
            score += 2

    filenames = lookup.get("filenames")
    if filenames and isinstance(image_meta, Mapping):
        entry_filename = image_meta.get("filename")
        if isinstance(entry_filename, str) and entry_filename in filenames:
            score += 1

    image_urls = lookup.get("imageUrls")
    if image_urls and isinstance(image_meta, Mapping):
        entry_url = image_meta.get("url")
        if isinstance(entry_url, str) and entry_url in image_urls:
            score += 1

    return score


def _lookup_has_criteria(lookup: JsonDict) -> bool:
    if not lookup:
        return False
    if lookup.get("entryId"):
        return True
    keys = ("historyIds", "sourceKind", "sourceId", "filenames", "imageUrls")
    return any(lookup.get(key) for key in keys)


def _select_ignore_entry(store: IgnoreRegionStore, lookup: JsonDict) -> JsonDict | None:
    if not _lookup_has_criteria(lookup):
        return None

    entry_id = lookup.get("entryId")
    if entry_id:
        return store.get_entry(str(entry_id))

    entries = store.list_entries()
    best: JsonDict | None = None
    best_score = -1
    for entry in entries:
        score = _score_ignore_entry(entry, lookup)
        if score <= 0:
            continue
        if best is None:
            best = entry
            best_score = score
            continue
        if score > best_score:
            best = entry
            best_score = score
            continue
        if score == best_score and _entry_timestamp(entry) > _entry_timestamp(best):
            best = entry

    return best


def _normalize_payload_polygons(regions: Iterable[JsonDict] | None, image_shape: tuple[int, int]) -> list[JsonDict]:
    if not regions or not image_shape:
        return []
    img_h, img_w = image_shape
    normalized: list[JsonDict] = []

    for region in regions:
        if not isinstance(region, Mapping):
            continue
        region_type = str(region.get("type") or "polygon").lower()
        points = region.get("points") or []
        if region_type == "rect" and len(points) >= 2:
            try:
                (x1, y1), (x2, y2) = points[0], points[-1]
            except Exception:  # pragma: no cover - malformed input
                continue
            left, right = min(x1, x2), max(x1, x2)
            top, bottom = min(y1, y2), max(y1, y2)
            points = [[left, top], [right, top], [right, bottom], [left, bottom]]

        if len(points) < 3:
            continue

        try:
            raw_points = [[float(pt[0]), float(pt[1])] for pt in points]
        except (TypeError, ValueError):
            continue

        max_coord = max(
            max((pt[0] for pt in raw_points), default=0.0),
            max((pt[1] for pt in raw_points), default=0.0),
        )

        if max_coord <= 1.0:
            scaled = [[pt[0] * img_w, pt[1] * img_h] for pt in raw_points]
        elif max_coord <= 100.0:
            scaled = [[(pt[0] / 100.0) * img_w, (pt[1] / 100.0) * img_h] for pt in raw_points]
        else:
            scaled = raw_points

        normalized.append({"type": "polygon", "points": scaled})

    return normalized


def _extract_entry_polygons(entry: JsonDict) -> list[JsonDict]:
    regions = entry.get("ignoreRegions") if isinstance(entry.get("ignoreRegions"), list) else []
    polygons: list[JsonDict] = []
    for region in regions:
        if not isinstance(region, Mapping):
            continue
        if str(region.get("type")).lower() != "polygon":
            continue
        points = region.get("points") or []
        if len(points) < 3:
            continue
        try:
            polygon = [[float(pt[0]), float(pt[1])] for pt in points]
        except (TypeError, ValueError):
            continue
        polygons.append({"type": "polygon", "points": polygon})
    return polygons


def _scale_polygons_to_target(
    polygons: list[JsonDict],
    source_shape: tuple[int, int] | None,
    target_shape: tuple[int, int],
) -> list[JsonDict]:
    if not polygons or not source_shape:
        return polygons
    src_h, src_w = source_shape
    tgt_h, tgt_w = target_shape
    if src_h <= 0 or src_w <= 0 or (src_h == tgt_h and src_w == tgt_w):
        return polygons
    scale_x = tgt_w / float(src_w)
    scale_y = tgt_h / float(src_h)
    scaled: list[JsonDict] = []
    for region in polygons:
        pts = region.get("points") or []
        scaled_pts = [[pt[0] * scale_x, pt[1] * scale_y] for pt in pts]
        scaled.append({"type": "polygon", "points": scaled_pts})
    return scaled


def _load_ignore_mask(entry: JsonDict, image_shape: tuple[int, int]) -> np.ndarray | None:
    storage = entry.get("storage") if isinstance(entry.get("storage"), Mapping) else {}
    if not isinstance(storage, Mapping):
        return None
    mask_rel = storage.get("mask")
    if not isinstance(mask_rel, str) or not mask_rel:
        return None

    mask_path = (_upload_folder() / mask_rel).resolve()
    if not mask_path.exists():
        return None

    try:
        mask_image = Image.open(mask_path).convert("L")
    except Exception as exc:  # pragma: no cover - corrupt mask
        current_app.logger.warning("Nie udalo sie wczytac maski ignorow %s: %s", mask_path, exc)
        return None

    target_w = int(image_shape[1])
    target_h = int(image_shape[0])
    if mask_image.size != (target_w, target_h):
        mask_image = mask_image.resize((target_w, target_h), Image.NEAREST)

    return np.array(mask_image, dtype=np.uint8) > 0


def _load_stored_ignore_regions(
    payload: JsonDict,
    source_context: JsonDict,
    image_shape: tuple[int, int],
) -> tuple[list[JsonDict], np.ndarray | None, JsonDict | None]:
    lookup = _build_ignore_lookup(payload, source_context)
    store = _ignore_store()
    entry = _select_ignore_entry(store, lookup) if store else None
    if not entry:
        return [], None, None

    polygons = _extract_entry_polygons(entry)
    polygons = _scale_polygons_to_target(polygons, _entry_image_shape(entry), image_shape)
    mask = _load_ignore_mask(entry, image_shape)
    return polygons, mask, entry


def _apply_ignore_filters(
    payload: JsonDict,
    source_context: JsonDict,
    response_payload: JsonDict,
    image_shape: tuple[int, int],
):
    inline_raw = payload.get("ignoreRegions") or payload.get("ignore_regions")
    inline_polygons = _normalize_payload_polygons(inline_raw if isinstance(inline_raw, list) else None, image_shape)
    stored_polygons, mask_array, entry = _load_stored_ignore_regions(payload, source_context, image_shape)

    has_payload_filters = bool(mask_array is not None or inline_polygons or stored_polygons)
    if not has_payload_filters:
        return

    threshold = _ignore_filter_threshold()
    detections = response_payload.get("detections", [])
    filtered = detections
    removed_total = 0

    if mask_array is not None:
        filtered, removed = filter_detections_with_mask(filtered, mask_array, threshold)
        removed_total += removed

    combined_polygons = inline_polygons + stored_polygons
    if combined_polygons:
        filtered, removed = filter_detections_by_polygons(filtered, combined_polygons, image_shape, threshold)
        removed_total += removed

    response_payload["detections"] = filtered
    response_payload["count"] = len(filtered)
    response_payload["filteredByIgnore"] = {
        "removed": removed_total,
        "threshold": threshold,
        "maskApplied": mask_array is not None,
        "inlineRegions": len(inline_polygons),
        "storedRegions": len(stored_polygons),
    }

    if entry:
        response_payload["filteredByIgnore"].update(
            {
                "entryId": entry.get("id"),
                "ignoreLabel": entry.get("label"),
            }
        )


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(val) for key, val in value.items()}
    if isinstance(value, Iterable):
        return [_normalize_value(item) for item in value]
    return str(value)


def _serialize_detection(index: int, detection: SymbolDetection) -> JsonDict:
    identifier = None
    meta = detection.metadata or {}
    if isinstance(meta, Mapping):
        candidate = meta.get("id")
        identifier = str(candidate) if isinstance(candidate, (str, int)) else None
    if not identifier:
        label_part = detection.label or "symbol"
        identifier = f"{label_part}-{index + 1:04d}"

    box = detection.box
    payload: JsonDict = {
        "id": identifier,
        "label": detection.label,
        "score": float(detection.score),
        "rotation": float(detection.rotation),
        "box": {
            "x": float(box.x),
            "y": float(box.y),
            "width": float(box.width),
            "height": float(box.height),
        },
        "bbox": [float(box.x), float(box.y), float(box.width), float(box.height)],
        "metadata": _normalize_value(meta),
    }
    return payload


def _serialize_summary(result: DetectionResult) -> JsonDict | None:
    summary = result.summary
    if summary is None:
        return None
    payload: JsonDict = {
        "latencyMs": float(summary.latency_ms),
    }
    if summary.raw_output is not None:
        payload["rawOutput"] = _normalize_value(summary.raw_output)
    return payload


def _get_detector(name: str) -> SymbolDetector:
    key = name.lower()
    cache = _detector_cache()
    detector = cache.get(key)
    if detector is None:
        detector = create_detector(name)
        cache[key] = detector
    return detector


def _decode_base64_image(image_data: str) -> np.ndarray | None:
    try:
        encoded = image_data.split(",", 1)[1] if "," in image_data else image_data
        img_bytes = base64.b64decode(encoded)
        image = Image.open(io.BytesIO(img_bytes))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        array = np.array(image)
        if array.ndim == 2:
            return array
        return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
    except Exception as exc:  # pragma: no cover - guardrail
        current_app.logger.error("Failed to decode base64 image: %s", exc)
        return None


def _resolve_history_file(entry: JsonDict) -> Path | None:
    storage = entry.get("storage")
    filename: str | None = None
    if isinstance(storage, dict):
        candidate = storage.get("filename")
        if isinstance(candidate, str) and candidate:
            filename = candidate
    if not filename:
        payload = entry.get("payload")
        if isinstance(payload, dict):
            candidate = payload.get("filename")
            if isinstance(candidate, str) and candidate:
                filename = candidate
    if not filename:
        return None
    path = Path(filename)
    if not path.is_absolute():
        path = (_upload_folder() / filename).resolve()
    return path if path.exists() else None


def _resolve_image_path(image_url: str) -> Path | None:
    from urllib.parse import urlparse

    parsed = urlparse(image_url)
    path = parsed.path if parsed.scheme else image_url

    if path.startswith("/uploads/"):
        relative = path[len("/uploads/") :]
    else:
        relative = path.lstrip("/")
        if relative.startswith("uploads/"):
            relative = relative[len("uploads/") :]

    candidate = (_upload_folder() / relative).resolve()
    if candidate.exists():
        return candidate

    static_base = Path(current_app.static_folder)
    if path.startswith("/static/"):
        static_candidate = static_base / path[len("/static/") :]
        if static_candidate.exists():
            return static_candidate
    if relative.startswith("static/"):
        static_candidate = static_base / relative[len("static/") :]
        if static_candidate.exists():
            return static_candidate

    if parsed.scheme in {"http", "https"}:
        fallback = Path(path)
        if fallback.exists():
            return fallback

    return None


def _load_image_from_reference(image_url: str | None, history_id: str | None) -> tuple[np.ndarray | None, JsonDict]:
    if history_id:
        store = _history_store()
        entry = store.get_entry(str(history_id))
        if entry:
            file_path = _resolve_history_file(entry)
            if file_path and file_path.exists():
                image = cv2.imread(str(file_path), cv2.IMREAD_UNCHANGED)
                if image is not None:
                    context: JsonDict = {
                        "source": "history",
                        "historyId": str(history_id),
                        "filename": file_path.name,
                    }
                    return image, context
    if image_url:
        file_path = _resolve_image_path(str(image_url))
        if file_path and file_path.exists():
            image = cv2.imread(str(file_path), cv2.IMREAD_UNCHANGED)
            if image is not None:
                context = {
                    "source": "url",
                    "imageUrl": image_url,
                    "filename": file_path.name,
                }
                return image, context
    return None, {}


def _prepare_source_context(image: np.ndarray, base: JsonDict) -> JsonDict:
    context = dict(base)
    context["imageShape"] = [int(dim) for dim in image.shape]
    return context


def _serialize_result(detector: SymbolDetector, result: DetectionResult, source: JsonDict) -> JsonDict:
    detections = [_serialize_detection(index, detection) for index, detection in enumerate(result.detections)]
    payload: JsonDict = {
        "detector": {
            "name": detector.name,
            "version": detector.version,
        },
        "count": len(detections),
        "detections": detections,
        "source": source,
    }
    summary = _serialize_summary(result)
    if summary is not None:
        payload["summary"] = summary
    return payload


def _store_detection_history(payload: JsonDict) -> JsonDict:
    processed_dir = _processed_folder() / "symbol-detections"
    processed_dir.mkdir(parents=True, exist_ok=True)

    result_id = uuid.uuid4().hex
    filename = processed_dir / f"symbols_{result_id}.json"

    stored_payload = {
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "detector": payload.get("detector"),
        "count": payload.get("count"),
        "detections": payload.get("detections"),
        "summary": payload.get("summary"),
        "source": payload.get("source"),
    }

    with filename.open("w", encoding="utf-8") as handle:
        json.dump(_normalize_value(stored_payload), handle, ensure_ascii=False, indent=2)

    relative = filename.relative_to(_upload_folder())
    created_at = stored_payload["createdAt"]
    detector_info = stored_payload.get("detector") or {}
    detector_name = detector_info.get("name") if isinstance(detector_info, Mapping) else None
    detector_version = detector_info.get("version") if isinstance(detector_info, Mapping) else None

    preview_url: str | None = None
    source_label: str | None = None
    source_payload = stored_payload.get("source") or {}

    history_id = None
    if isinstance(source_payload, Mapping):
        history_id = source_payload.get("historyId") or source_payload.get("history_id")

    if history_id:
        store = _history_store()
        source_entry = store.get_entry(str(history_id))
        if source_entry:
            preview_url = source_entry.get("url") or None
            if not preview_url:
                storage = source_entry.get("storage")
                if isinstance(storage, Mapping):
                    filename_token = storage.get("filename")
                    if isinstance(filename_token, str) and filename_token:
                        preview_url = url_for("core.serve_upload", filename=filename_token)
            source_label = source_entry.get("label") if isinstance(source_entry.get("label"), str) else None

    if not preview_url and isinstance(source_payload, Mapping):
        candidate = source_payload.get("imageUrl") or source_payload.get("image_url") or source_payload.get("url")
        if isinstance(candidate, str) and candidate:
            preview_url = candidate

        if not source_label:
            label_candidate = source_payload.get("label") or source_payload.get("filename")
            if isinstance(label_candidate, str) and label_candidate:
                source_label = label_candidate

    if preview_url and not preview_url.startswith("http") and not preview_url.startswith("/"):
        # Normalize relative paths to served uploads
        preview_path = Path(preview_url)
        if not preview_path.is_absolute():
            preview_url = url_for("core.serve_upload", filename=preview_path.as_posix())

    entry: JsonDict = {
        "id": f"symbols-{result_id}",
        "url": url_for("core.serve_upload", filename=relative.as_posix()),
        "label": f"Detekcja symboli ({created_at})",
        "type": "symbol-detection",
        "meta": {
            "createdAt": created_at,
            "typeLabel": "Detekcja symboli",
            "detector": detector_name,
            "detectorVersion": detector_version,
            "detections": stored_payload.get("count"),
        },
        "storage": {
            "type": "processed",
            "filename": relative.as_posix(),
        },
        "payload": {
            "filename": relative.as_posix(),
            "count": stored_payload.get("count"),
            "detector": stored_payload.get("detector"),
            "summary": stored_payload.get("summary"),
            "source": stored_payload.get("source"),
        },
    }

    if preview_url:
        entry["previewUrl"] = preview_url
        entry["meta"]["previewUrl"] = preview_url
        entry["payload"]["previewUrl"] = preview_url
    if source_label:
        entry["meta"]["sourceLabel"] = source_label

    store = _history_store()
    store.upsert_entry(entry)
    return entry


@symbol_detection_bp.get("/detectors")
def list_detectors():  # type: ignore[override]
    detectors = [{"name": name} for name in available_detectors()]
    return jsonify({"detectors": detectors, "count": len(detectors)})


@symbol_detection_bp.post("/detect")
def detect_symbols():  # type: ignore[override]
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400

    detectors = tuple(available_detectors())
    env_default = os.environ.get("TALK_ELECTRONIC_DETECTOR", "").strip().lower()
    default_detector = env_default if env_default and env_default in {n.lower() for n in detectors} else (detectors[0] if detectors else None)
    requested_name = payload.get("detector") or payload.get("detectorName") or default_detector
    if requested_name is None:
        return jsonify({"error": "No detectors registered"}), 503

    detector_name = str(requested_name).strip()
    if not detector_name:
        return jsonify({"error": "Detector name is required"}), 400

    if detector_name.lower() not in {name.lower() for name in detectors}:
        return jsonify({"error": f"Unknown detector: {detector_name}"}), 400

    image_data = payload.get("imageData") or payload.get("image_data")
    image_url = payload.get("imageUrl") or payload.get("image")
    history_id = payload.get("historyId")

    source_context: JsonDict = {}
    image: np.ndarray | None = None

    if isinstance(image_data, str) and image_data.strip():
        image = _decode_base64_image(image_data)
        if image is not None:
            source_context = {"source": "inline"}

    if image is None:
        reference_image, reference_context = _load_image_from_reference(image_url, history_id)
        image = reference_image
        source_context = reference_context

    if image is None:
        return jsonify({"error": "Image could not be loaded"}), 404

    image_dimensions = (int(image.shape[0]), int(image.shape[1]))
    source_context = _prepare_source_context(image, source_context)
    return_summary = bool(payload.get("returnSummary", True))

    try:
        detector = _get_detector(detector_name)
        detection_result = detector.detect(image, return_summary=return_summary)
    except Exception as exc:  # pragma: no cover - guardrail
        current_app.logger.error("Symbol detection failed: %s", exc, exc_info=True)
        return jsonify({"error": "Detection failure"}), 500

    response_payload = _serialize_result(detector, detection_result, source_context)

    try:
        _apply_ignore_filters(payload, source_context, response_payload, image_dimensions)
    except Exception as exc:  # pragma: no cover - guardrail
        current_app.logger.exception("Error applying ignore filters: %s", exc)

    history_entry: JsonDict | None = None
    if bool(payload.get("storeHistory")):
        history_entry = _store_detection_history(response_payload)
        response_payload["historyEntry"] = history_entry

    return jsonify(response_payload), 200


@symbol_detection_bp.route("/load-annotations", methods=["POST"])
def load_annotations_endpoint():
    """
    Ładuje anotacje z pliku JSON (Label Studio lub COCO).

    Automatycznie wykrywa i konwertuje rotated rectangles do formatu segmentacji.

    Request JSON:
    {
        "annotationFile": "path/to/annotations.json",  // Ścieżka względna lub bezwzględna
        "validate": true  // Opcjonalne: waliduj format (domyślnie true)
    }

    Response JSON:
    {
        "success": true,
        "data": {...},  // Dane COCO
        "info": {
            "format": "label_studio" | "yolov8_obb" | "coco_standard",
            "conversionPerformed": true,
            "rotatedCount": 42,
            "totalAnnotations": 100,
            "message": "Automatycznie przekonwertowano 42 rotated rectangles"
        }
    }
    """
    payload = request.get_json() or {}
    annotation_file_path = payload.get("annotationFile") or payload.get("annotation_file")
    should_validate = payload.get("validate", True)

    if not annotation_file_path:
        return jsonify({"success": False, "error": "Pole 'annotationFile' jest wymagane"}), 400

    # Rozwiąż ścieżkę (względną lub bezwzględną)
    annotation_path = Path(annotation_file_path)
    if not annotation_path.is_absolute():
        # Szukaj w katalogu data/annotations/
        base_path = Path(current_app.root_path).parent / "data" / "annotations"
        annotation_path = (base_path / annotation_file_path).resolve()

    # Sprawdź czy plik istnieje
    if not annotation_path.exists():
        return jsonify({"success": False, "error": f"Plik nie istnieje: {annotation_path}"}), 404

    try:
        # Wykryj format PRZED konwersją (do komunikatu)
        with open(annotation_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        format_info = detect_annotation_format(raw_data)

        # Załaduj i automatycznie konwertuj
        current_app.logger.info(f"Ładowanie anotacji z: {annotation_path}")
        coco_data = load_annotations(annotation_path)

        # Opcjonalna walidacja
        validation_errors = []
        if should_validate:
            is_valid, errors = validate_coco_annotations(coco_data)
            if not is_valid:
                validation_errors = errors
                current_app.logger.warning(f"Wykryto {len(errors)} błędów walidacji: {errors}")

        # Przygotuj komunikat dla użytkownika
        message_parts = []
        if format_info["needs_conversion"]:
            message_parts.append(
                f"✅ Automatycznie przekonwertowano {format_info['rotated_count']} "
                f"rotated rectangles do formatu segmentacji"
            )
        else:
            message_parts.append("✅ Anotacje już w standardowym formacie COCO")

        if validation_errors:
            message_parts.append(f"⚠️  Znaleziono {len(validation_errors)} ostrzeżeń walidacji")

        response = {
            "success": True,
            "data": coco_data,
            "info": {
                "format": format_info["format"],
                "conversionPerformed": format_info["needs_conversion"],
                "rotatedCount": format_info["rotated_count"],
                "totalAnnotations": format_info["total_count"],
                "message": " | ".join(message_parts),
                "filePath": str(annotation_path),
            },
        }

        if validation_errors:
            response["info"]["validationErrors"] = validation_errors

        current_app.logger.info(
            f"Pomyślnie załadowano anotacje: {format_info['total_count']} anotacji, "
            f"konwersja: {format_info['needs_conversion']}"
        )

        return jsonify(response), 200

    except FileNotFoundError as e:
        current_app.logger.error(f"Plik nie znaleziony: {e}")
        return jsonify({"success": False, "error": str(e)}), 404

    except json.JSONDecodeError as e:
        current_app.logger.error(f"Błąd parsowania JSON: {e}")
        return jsonify({"success": False, "error": f"Nieprawidłowy format JSON: {e}"}), 400

    except Exception as e:
        current_app.logger.error(f"Błąd podczas ładowania anotacji: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"Błąd wewnętrzny: {str(e)}"}), 500
