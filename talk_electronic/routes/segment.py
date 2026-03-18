from __future__ import annotations

import json
import time
import uuid
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
from flask import Blueprint, current_app, jsonify, request, url_for

from ..services.edge_connector_store import EdgeConnectorStore
from ..services.line_detection import (
    JunctionDetectorConfig,
    JunctionPatchExportConfig,
    LineDetectionConfig,
    LineDetectionResult,
    detect_lines,
    line_detection_result_from_dict,
)
from ..services.netlist import NetlistResult, generate_netlist, netlist_result_from_dict
from ..services.netlist_export import (
    SpiceValidationResult,
    generate_spice_netlist,
    parse_component_instances,
    validate_spice_components,
)
from .edge_connectors import _roi_from_geometry

segment_bp = Blueprint("segment", __name__, url_prefix="/api/segment")

JsonDict = Dict[str, Any]


def _history_store():
    return current_app.extensions["processing_history"]


def _edge_connector_store() -> EdgeConnectorStore | None:
    return current_app.extensions.get("edge_connector_store")


def _upload_folder() -> Path:
    return current_app.config["UPLOAD_FOLDER"]


def _processed_folder() -> Path:
    return current_app.config["PROCESSED_FOLDER"]


def _roi_metrics() -> Dict[str, int]:
    store = current_app.extensions.setdefault("roi_metrics", {})
    # Ensure expected keys exist
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
    return store  # type: ignore[return-value]


def _error_response(message: str, code: str, status: int):
    return jsonify({"error": message, "errorCode": code}), status


@segment_bp.post("/lines")
def segment_lines():  # type: ignore[override]
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error_response("Nieprawidłowe dane wejściowe", "INVALID_PAYLOAD", 400)

    metrics = _roi_metrics()

    image_ref = payload.get("imageUrl") or payload.get("image")
    history_id = payload.get("historyId")
    binary_flag = bool(payload.get("binary", False))
    store_history = bool(payload.get("storeHistory", False))
    debug_flag = bool(payload.get("debug", False))
    config_overrides = payload.get("config", {})

    if not image_ref and not history_id:
        return _error_response("Wymagany jest imageUrl lub historyId", "MISSING_IMAGE_REF", 400)

    image = _load_image(image_ref, history_id)
    if image is None:
        metrics["load_error"] += 1
        current_app.logger.warning(
            "Segment request failed to load image (history_id=%s, ref=%s)", history_id, image_ref
        )
        return _error_response("Nie udało się wczytać obrazu", "IMAGE_NOT_FOUND", 404)

    # Accept ROI from payload (x,y,width,height or x,y,w,h) or derive from geometry
    roi_raw = payload.get("roi") or payload.get("roi_abs") or payload.get("roiAbs")
    if not roi_raw:
        roi_raw = _roi_from_geometry(payload.get("geometry"))

    roi: dict | None = None
    if isinstance(roi_raw, dict):
        try:
            rx = int(round(float(roi_raw.get("x"))))
            ry = int(round(float(roi_raw.get("y"))))
            rw = int(round(float(roi_raw.get("width") if roi_raw.get("width") is not None else roi_raw.get("w"))))
            rh = int(round(float(roi_raw.get("height") if roi_raw.get("height") is not None else roi_raw.get("h"))))
            if rw > 0 and rh > 0:
                # Clip to image bounds
                img_h, img_w = image.shape[0], image.shape[1]
                x0 = max(0, rx)
                y0 = max(0, ry)
                x1 = min(img_w, x0 + rw)
                y1 = min(img_h, y0 + rh)
                if x1 > x0 and y1 > y0:
                    roi = {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
        except Exception:
            roi = None

    # Log whether ROI was provided + update counters
    metrics["total"] += 1
    if roi:
        metrics["roi_used"] += 1
        current_app.logger.info("Segment request using ROI: %s (history_id=%s)", roi, history_id)
    else:
        metrics["roi_missing"] += 1
        current_app.logger.info("Segment request with no ROI (history_id=%s)", history_id)

    # If ROI given, crop the image before processing and record input shape
    original_shape = None
    if roi:
        original_shape = (int(image.shape[0]), int(image.shape[1]))
        try:
            x = int(roi["x"])
            y = int(roi["y"])
            w = int(roi["width"])
            h = int(roi["height"])
            t_crop_start = time.perf_counter()
            cropped = image[y : y + h, x : x + w]
            t_crop = (time.perf_counter() - t_crop_start) * 1000.0
            if cropped is not None and cropped.size != 0:
                current_app.logger.info(
                    "Cropped image from %sx%s to %sx%s (crop time %.2f ms)",
                    original_shape[1],
                    original_shape[0],
                    int(cropped.shape[1]),
                    int(cropped.shape[0]),
                    t_crop,
                )
                metrics["roi_crop_ok"] += 1
                image = cropped
            else:
                current_app.logger.warning("ROI crop produced empty result: %s", roi)
                metrics["roi_crop_empty"] += 1
        except Exception as exc:  # pragma: no cover - defensive
            metrics["roi_crop_error"] += 1
            current_app.logger.debug("Failed to crop image for ROI, continuing with full image: %s", exc)

    config = _build_config(config_overrides, debug_flag)

    try:
        t_detect_start = time.perf_counter()
        result = detect_lines(image, binary=binary_flag, config=config)
        t_detect = (time.perf_counter() - t_detect_start) * 1000.0
        # Log detection timing and input/output shapes
        in_h, in_w = image.shape[0], image.shape[1]
        current_app.logger.info(
            "detect_lines completed (elapsed %.2f ms) on image %sx%s; result lines=%s",
            t_detect,
            in_w,
            in_h,
            getattr(result, "lines", None) or 0,
        )
        current_app.logger.info(
            "ROI metrics: total=%s used=%s missing=%s crop_ok=%s crop_empty=%s crop_error=%s",
            metrics.get("total"),
            metrics.get("roi_used"),
            metrics.get("roi_missing"),
            metrics.get("roi_crop_ok"),
            metrics.get("roi_crop_empty"),
            metrics.get("roi_crop_error"),
        )
    except Exception as exc:  # pragma: no cover - guardrail
        current_app.logger.error("Line detection failed: %s", exc, exc_info=True)
        return _error_response("Błąd segmentacji linii", "SEGMENTATION_FAILED", 500)

    # Attach roi info into result metadata if used
    if roi:
        result.metadata = result.metadata or {}
        result.metadata["roi"] = roi
        if original_shape:
            result.metadata["input_shape_before_crop"] = original_shape

    response_payload: JsonDict = {
        "result": _result_to_response(result),
    }

    if store_history:
        entry = _store_segmentation_result(result)
        if entry is not None:
            response_payload["historyEntry"] = entry

    return jsonify(response_payload), 200


@segment_bp.post("/netlist")
def build_netlist():  # type: ignore[override]
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error_response("Nieprawidłowe dane wejściowe", "INVALID_PAYLOAD", 400)

    history_id = payload.get("historyId")
    symbol_history_id = payload.get("symbolHistoryId") or payload.get("symbolDetectionHistoryId")
    symbol_payload = payload.get("symbols") or payload.get("symbolDetections")
    store_history = bool(payload.get("storeHistory", False))
    lines_payload = payload.get("lines")
    connector_history_hint = payload.get("edgeConnectorHistoryId") or payload.get("edgeConnectorHistoryID")

    serialized: Dict[str, Any] | None = None
    source_label: str | None = None

    if isinstance(lines_payload, dict):
        serialized = lines_payload
        source_label = "inline"
    elif history_id:
        store = _history_store()
        entry = store.get_entry(str(history_id))
        if entry is None:
            return _error_response("Nie znaleziono wyniku segmentacji", "SEGMENT_HISTORY_NOT_FOUND", 404)
        file_path = _resolve_history_file(entry)
        if file_path is None:
            return _error_response("Brak pliku z danymi segmentacji", "SEGMENT_FILE_MISSING", 404)
        try:
            with file_path.open("r", encoding="utf-8") as fp:
                serialized = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return _error_response("Nie można odczytać pliku segmentacji", "SEGMENT_FILE_READ_ERROR", 500)
        source_label = entry.get("id") or str(history_id)
    else:
        return _error_response("Wymagany jest wynik segmentacji (lines lub historyId)", "MISSING_LINES", 400)

    assert serialized is not None
    line_result = line_detection_result_from_dict(serialized)
    if not line_result.lines:
        return _error_response("Brak odcinków w dostarczonych danych", "NO_LINES", 400)

    netlist = generate_netlist(line_result)
    if history_id:
        source = netlist.metadata.setdefault("source", {})
        source["historyId"] = str(history_id)
    if source_label:
        source = netlist.metadata.setdefault("source", {})
        source.setdefault("label", source_label)

    symbol_payload = _resolve_symbol_payload(symbol_payload, symbol_history_id)
    if symbol_payload is not None:
        _attach_symbol_metadata(netlist, symbol_payload, symbol_history_id)

    history_candidates = _collect_edge_connector_history_ids(
        serialized,
        netlist.metadata.get("source"),
        history_id=str(history_id) if history_id else None,
        connector_history_id=str(connector_history_hint) if connector_history_hint else None,
    )
    if history_candidates:
        _attach_edge_connectors(netlist, history_candidates)

    response_payload: Dict[str, Any] = {
        "netlist": netlist.to_dict(),
    }

    if store_history:
        entry = _store_netlist_result(netlist)
        response_payload["historyEntry"] = entry

    return jsonify(response_payload), 200


@segment_bp.post("/netlist/spice")
def export_spice_netlist():  # type: ignore[override]
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error_response("Nieprawidłowe dane wejściowe", "INVALID_PAYLOAD", 400)

    store_history = bool(payload.get("storeHistory", False))
    history_id = payload.get("historyId")
    netlist_payload = payload.get("netlist")

    netlist_dict: Dict[str, Any] | None = None
    if isinstance(netlist_payload, dict):
        netlist_dict = netlist_payload
    elif history_id:
        netlist_dict = _load_netlist_from_history(str(history_id))
        if netlist_dict is None:
            return _error_response("Nie znaleziono zapisanej netlisty", "NETLIST_HISTORY_NOT_FOUND", 404)
    else:
        return _error_response("Wymagane jest pole netlist lub historyId", "MISSING_NETLIST", 400)

    try:
        netlist = netlist_result_from_dict(netlist_dict)
    except Exception as exc:  # pragma: no cover - defensive guard
        current_app.logger.error("Nie można zbudować obiektu NetlistResult: %s", exc, exc_info=True)
        return _error_response("Nieprawidłowa struktura netlisty", "INVALID_NETLIST", 400)

    if not netlist.nodes:
        return _error_response("Netlista nie zawiera węzłów", "NETLIST_EMPTY", 400)

    components_payload = payload.get("components") or payload.get("componentAssignments") or payload.get("assignments")
    try:
        components = parse_component_instances(components_payload)
    except ValueError as exc:
        return _error_response(str(exc), "INVALID_COMPONENTS", 400)

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        source_meta = netlist.metadata.get("source")
        if isinstance(source_meta, dict):
            title = source_meta.get("label") or source_meta.get("id")
    if not title:
        title = "Talk_electronic generated circuit"

    ground_alias = payload.get("groundAlias")
    if not isinstance(ground_alias, str) or not ground_alias:
        ground_alias = "0"

    validation: SpiceValidationResult | None = None
    try:
        validation = validate_spice_components(netlist, components, ground_alias=ground_alias)
    except Exception as exc:  # pragma: no cover - guardrail
        current_app.logger.error("Nie udało się zwalidować komponentów SPICE: %s", exc, exc_info=True)
        return _error_response("Błąd walidacji komponentów", "SPICE_VALIDATION_ERROR", 500)

    if validation and validation.errors:
        return _error_response("; ".join(validation.errors), "SPICE_COMPONENT_ERRORS", 400)

    try:
        spice_text = generate_spice_netlist(
            netlist,
            components,
            title=title,
            ground_alias=ground_alias,
            validate=False,
        )
    except ValueError as exc:
        return _error_response(str(exc), "SPICE_GENERATION_ERROR", 400)

    if validation and validation.warnings:
        lines = spice_text.rstrip("\n").splitlines()
        end_line = ".end"
        if lines and lines[-1].strip().lower() == ".end":
            end_line = lines.pop()
        warn_lines = [f"* WARN: {warning}" for warning in validation.warnings]
        lines.extend(warn_lines)
        lines.append(end_line)
        spice_text = "\n".join(lines) + "\n"

    response_payload: Dict[str, Any] = {
        "spice": spice_text,
        "metadata": {
            "title": title,
            "componentCount": len(components),
            "groundAlias": ground_alias,
            "source": netlist.metadata.get("source", {}),
            "warnings": validation.warnings if validation else [],
        },
    }

    if store_history:
        history_entry = _store_spice_result(spice_text, title=title, source=netlist.metadata.get("source"))
        response_payload["historyEntry"] = history_entry

    return jsonify(response_payload), 200


def _load_image(image_url: str | None, history_id: str | None) -> Any:
    """Load image from a reference which may be:
    - a history entry (history_id)
    - a path/URL (/uploads/..., /static/..., or absolute path)
    - a data URL (data:image/png;base64,...)
    Returns OpenCV image or None on failure.
    """
    if history_id:
        store = _history_store()
        entry = store.get_entry(history_id)
        if entry is None:
            return None
        image_url = _extract_filename_from_entry(entry)

    if not image_url:
        return None

    # Support data URLs inline (data:image/png;base64,....)
    if isinstance(image_url, str) and image_url.startswith("data:"):
        try:
            import base64

            import numpy as np

            # Split header and payload
            header, b64data = image_url.split(",", 1)
            decoded = base64.b64decode(b64data)
            arr = np.frombuffer(decoded, dtype=np.uint8)
            image = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
            if image is None:
                current_app.logger.error("cv2.imdecode returned None for data URL")
                return None
            return image
        except Exception as exc:  # pragma: no cover - defensive
            current_app.logger.error("Failed to decode data URL image: %s", exc, exc_info=True)
            return None

    path = _resolve_image_path(image_url)
    if path is None or not path.exists():
        return None

    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    return image


def _extract_filename_from_entry(entry: JsonDict) -> str | None:
    storage = entry.get("storage")
    if isinstance(storage, dict):
        filename = storage.get("filename")
        if isinstance(filename, str):
            return filename
    payload = entry.get("payload")
    if isinstance(payload, dict):
        filename = payload.get("filename")
        if isinstance(filename, str):
            return filename
    return None


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

    candidate = _upload_folder() / relative
    if candidate.exists():
        return candidate

    if path.startswith("/static/"):
        static_relative = path[len("/static/") :]
        static_candidate = Path(current_app.static_folder) / static_relative
        if static_candidate.exists():
            return static_candidate

    if relative.startswith("static/"):
        static_candidate = Path(current_app.static_folder) / relative[len("static/") :]
        if static_candidate.exists():
            return static_candidate

    if parsed.scheme and parsed.netloc:
        fallback = Path(path)
        if fallback.exists():
            return fallback
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


def _load_netlist_from_history(history_id: str) -> Dict[str, Any] | None:
    store = _history_store()
    entry = store.get_entry(history_id)
    if entry is None:
        return None
    file_path = _resolve_history_file(entry)
    if file_path is None:
        return None
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):  # pragma: no cover - defensive
        return None


def _load_symbol_detection_from_history(history_id: str) -> Dict[str, Any] | None:
    store = _history_store()
    entry = store.get_entry(history_id)
    if entry is None:
        return None
    file_path = _resolve_history_file(entry)
    if file_path is None:
        return None
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):  # pragma: no cover - defensive
        return None


def _resolve_symbol_payload(
    inline_payload: Dict[str, Any] | None,
    history_id: str | None,
) -> Dict[str, Any] | None:
    if isinstance(inline_payload, dict):
        return inline_payload
    if not history_id:
        return None
    return _load_symbol_detection_from_history(str(history_id))


def _attach_symbol_metadata(
    netlist: NetlistResult,
    symbol_payload: Dict[str, Any],
    history_id: str | None = None,
) -> None:
    detections = symbol_payload.get("detections")
    if not isinstance(detections, list):
        detections = []
    detector_value = symbol_payload.get("detector")
    detector_info = detector_value if isinstance(detector_value, dict) else detector_value
    summary_value = symbol_payload.get("summary")
    summary = summary_value if isinstance(summary_value, dict) else summary_value

    metadata_entry: Dict[str, Any] = {
        "count": symbol_payload.get("count", len(detections)),
        "detector": detector_info,
        "summary": summary,
        "detections": detections,
    }
    if history_id:
        metadata_entry["historyId"] = str(history_id)
    source_hint = symbol_payload.get("source")
    if isinstance(source_hint, dict):
        metadata_entry["source"] = source_hint

    netlist.metadata["symbols"] = metadata_entry


def _collect_edge_connector_history_ids(
    serialized_lines: Dict[str, Any] | None,
    netlist_source_meta: Dict[str, Any] | None,
    *,
    history_id: str | None,
    connector_history_id: str | None,
) -> List[str]:
    candidates: List[str] = []

    def _push(value: Any) -> None:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized and normalized not in candidates:
                candidates.append(normalized)

    _push(history_id)
    _push(connector_history_id)

    if serialized_lines and isinstance(serialized_lines, dict):
        meta = serialized_lines.get("metadata")
        if isinstance(meta, dict):
            _push(meta.get("historyId"))
            _push(meta.get("history_id"))
            _push(meta.get("sourceHistoryId"))
            nested = meta.get("source")
            if isinstance(nested, dict):
                _push(nested.get("historyId"))
                _push(nested.get("id"))
        source_payload = serialized_lines.get("source")
        if isinstance(source_payload, dict):
            _push(source_payload.get("historyId"))
            _push(source_payload.get("id"))

    if isinstance(netlist_source_meta, dict):
        _push(netlist_source_meta.get("historyId"))
        _push(netlist_source_meta.get("id"))

    return candidates


def _attach_edge_connectors(netlist: NetlistResult, history_candidates: List[str]) -> None:
    store = _edge_connector_store()
    if store is None:
        return

    normalized = {candidate.strip().lower() for candidate in history_candidates if candidate.strip()}
    current_app.logger.debug(
        "[segment] _attach_edge_connectors: history_candidates=%s normalized=%s",
        history_candidates,
        sorted(list(normalized)),
    )
    if not normalized:
        current_app.logger.debug("[segment] _attach_edge_connectors: no normalized candidates, skipping")
        return

    entries = store.list_entries()
    current_app.logger.debug("[segment] _attach_edge_connectors: store contains %d entries", len(entries))
    matched: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_history = entry.get("historyId")
        if not isinstance(entry_history, str) or entry_history.strip().lower() not in normalized:
            continue
        entry_id = entry.get("id")
        payload = None
        if isinstance(entry_id, str) and entry_id:
            payload = store.load_payload(entry_id)
        matched.append(_serialize_edge_connector_entry(entry, payload))

    current_app.logger.debug(
        "[segment] _attach_edge_connectors: matched_count=%d matched_ids=%s",
        len(matched),
        [m.get("id") for m in matched],
    )

    summary: Dict[str, Any] = {
        "count": len(matched),
        "historyCandidates": history_candidates,
        "items": matched,
    }
    if matched:
        summary["historyId"] = matched[0].get("historyId")
        pages = sorted({item.get("page") for item in matched if item.get("page")})
        if pages:
            summary["pages"] = pages
        edge_ids = sorted({item.get("edgeId") for item in matched if item.get("edgeId")})
        if edge_ids:
            summary["edgeIds"] = edge_ids

    netlist.metadata["edgeConnectors"] = summary


def _serialize_edge_connector_entry(entry: Dict[str, Any], payload: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else entry.get("source")
    raw_meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else entry.get("metadata")
    if not raw_meta and isinstance(payload.get("meta"), dict):
        raw_meta = payload.get("meta")

    metadata = raw_meta or {}
    if "roi_abs" not in metadata and "roi" not in metadata:
        roi_candidate = _roi_from_geometry(payload.get("geometry"))
        if roi_candidate:
            metadata = dict(metadata)
            metadata["roi_abs"] = roi_candidate

    return {
        "id": entry.get("id"),
        "edgeId": payload.get("edgeId") or entry.get("edgeId"),
        "page": payload.get("page") or entry.get("page"),
        "label": payload.get("label") or entry.get("label"),
        "netName": payload.get("netName") or entry.get("netName"),
        "sheetId": payload.get("sheetId") or entry.get("sheetId"),
        "note": payload.get("note") or entry.get("note"),
        "historyId": payload.get("historyId") or entry.get("historyId"),
        "geometry": payload.get("geometry"),
        "source": source or {},
        "metadata": metadata or {},
        "createdAt": entry.get("createdAt") or payload.get("createdAt"),
        "updatedAt": entry.get("updatedAt") or payload.get("updatedAt"),
    }


def _store_spice_result(spice_text: str, *, title: str, source: Dict[str, Any] | None = None) -> JsonDict:
    processed_dir = _processed_folder() / "spice"
    processed_dir.mkdir(parents=True, exist_ok=True)

    result_id = uuid.uuid4().hex
    filename = processed_dir / f"spice_{result_id}.cir"
    filename.write_text(spice_text, encoding="utf-8")

    relative = filename.relative_to(_upload_folder())
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    entry: JsonDict = {
        "id": f"spice-{result_id}",
        "url": url_for("core.serve_upload", filename=relative.as_posix()),
        "label": f"SPICE ({created_at})",
        "type": "spice-netlist",
        "meta": {
            "createdAt": created_at,
            "typeLabel": "Eksport SPICE",
            "title": title,
            "lineCount": spice_text.count("\n"),
        },
        "storage": {
            "type": "processed",
            "filename": relative.as_posix(),
        },
        "payload": {
            "title": title,
            "source": source or {},
        },
    }

    store = _history_store()
    store.upsert_entry(entry)
    return entry


def _build_config(overrides: Dict[str, Any], debug_flag: bool) -> LineDetectionConfig:
    config = LineDetectionConfig()

    defaults = current_app.config.get("LINE_DETECTION_DEFAULTS") or {}
    color_presets = current_app.config.get("LINE_DETECTION_COLOR_PRESETS") or {}
    if isinstance(defaults, dict):
        _apply_config_values(config, defaults)

    _apply_color_preset(
        config,
        config.color_preset,
        user_presets=defaults.get("color_presets") if isinstance(defaults, dict) else None,
        global_presets=color_presets,
    )

    preset_override = _extract_color_preset(overrides)
    if preset_override:
        user_presets = overrides.get("color_presets") if isinstance(overrides, dict) else None
        _apply_color_preset(
            config,
            preset_override,
            user_presets=user_presets,
            global_presets=color_presets,
        )

    _apply_config_values(config, overrides)

    if debug_flag and not config.debug_dir:
        debug_dir = _processed_folder() / "line-debug" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        config.debug_dir = debug_dir

    return config


def _apply_config_values(config: LineDetectionConfig, values: Dict[str, Any]) -> None:
    if not isinstance(values, dict):
        return

    for field_info in fields(LineDetectionConfig):
        name = field_info.name
        if name not in values:
            continue
        value = values[name]
        if isinstance(field_info.default, tuple) and isinstance(value, list):
            value = tuple(value)
        if name == "debug_dir" and isinstance(value, str):
            value = Path(value)
        if name == "junction_patch_export" and isinstance(value, dict):
            value = JunctionPatchExportConfig(**value)
        if name == "junction_detector" and isinstance(value, dict):
            value = JunctionDetectorConfig(**value)
        setattr(config, name, value)


def _apply_color_preset(
    config: LineDetectionConfig,
    preset_name: Optional[str],
    *,
    user_presets: Optional[Dict[str, Any]] = None,
    global_presets: Optional[Dict[str, Any]] = None,
) -> None:
    if not preset_name:
        return

    for source in (user_presets, global_presets):
        if not isinstance(source, dict):
            continue
        preset = source.get(preset_name)
        if isinstance(preset, dict):
            _apply_config_values(config, preset)
            config.color_preset = preset_name
            return


def _extract_color_preset(values: Dict[str, Any] | None) -> Optional[str]:
    if not isinstance(values, dict):
        return None
    preset = values.get("color_preset") or values.get("colorPreset")
    return preset if isinstance(preset, str) and preset else None


def _store_segmentation_result(result: LineDetectionResult) -> JsonDict | None:
    processed_dir = _processed_folder() / "segments"
    processed_dir.mkdir(parents=True, exist_ok=True)

    result_id = uuid.uuid4().hex
    filename = processed_dir / f"lines_{result_id}.json"
    data = result.to_dict()
    with filename.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

    relative = filename.relative_to(_upload_folder())
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry = {
        "id": f"lines-{result_id}",
        "url": url_for("core.serve_upload", filename=relative.as_posix()),
        "label": f"Segmentacja linii ({created_at})",
        "type": "line-segmentation",
        "meta": {
            "createdAt": created_at,
            "typeLabel": "Segmentacja linii",
            "lines": len(result.lines),
            "nodes": len(result.nodes),
        },
        "storage": {
            "type": "processed",
            "filename": relative.as_posix(),
        },
        "payload": {
            "lines": len(result.lines),
            "nodes": len(result.nodes),
            "elapsedMs": result.metadata.get("elapsed_ms"),
        },
    }

    skeleton_meta = result.metadata.get("skeleton_metadata")
    if isinstance(skeleton_meta, dict):
        binary_before = skeleton_meta.get("binary_pixels_before")
        binary_after = skeleton_meta.get("binary_pixels_after")
        skeleton_pixels = skeleton_meta.get("skeleton_pixels")
    else:
        binary_before = None
        binary_after = None
        skeleton_pixels = None

    if result.metadata.get("skeleton_pixels") is not None:
        entry["meta"]["skeletonPixels"] = result.metadata["skeleton_pixels"]
    elif skeleton_pixels is not None:
        entry["meta"]["skeletonPixels"] = skeleton_pixels

    if binary_before is not None:
        entry["meta"]["binaryPixelsBefore"] = binary_before
    if binary_after is not None:
        entry["meta"]["binaryPixelsAfter"] = binary_after

    input_shape = result.metadata.get("input_shape")
    if input_shape is not None:
        entry["meta"]["inputShape"] = input_shape

    confidence_meta = result.metadata.get("confidence")
    if isinstance(confidence_meta, dict):
        entry["meta"]["flaggedSegments"] = len(confidence_meta.get("low_confidence", []))
        entry.setdefault("payload", {})["confidence"] = confidence_meta

    entry["payload"]["metadata"] = result.metadata

    store = _history_store()
    store.upsert_entry(entry)
    return entry


def _result_to_response(result: LineDetectionResult) -> JsonDict:
    data = result.to_dict()
    upload_folder = _upload_folder()
    debug_urls: list[str] = []

    for artifact in result.debug_artifacts:
        try:
            relative = Path(artifact).resolve().relative_to(upload_folder)
        except ValueError:
            continue
        debug_urls.append(url_for("core.serve_upload", filename=relative.as_posix()))

    data["debugArtifacts"] = debug_urls
    data["debug_artifacts"] = debug_urls
    return data


def _store_netlist_result(result: NetlistResult) -> JsonDict:
    processed_dir = _processed_folder() / "netlists"
    processed_dir.mkdir(parents=True, exist_ok=True)

    result_id = uuid.uuid4().hex
    filename = processed_dir / f"netlist_{result_id}.json"
    data = result.to_dict()
    with filename.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

    relative = filename.relative_to(_upload_folder())
    created_at = datetime.utcnow().isoformat(timespec="seconds")
    components = result.metadata.get("connected_components")
    meta_components = components if isinstance(components, list) else []

    entry = {
        "id": f"netlist-{result_id}",
        "url": url_for("core.serve_upload", filename=relative.as_posix()),
        "label": f"Netlista ({created_at})",
        "type": "netlist",
        "meta": {
            "createdAt": created_at,
            "typeLabel": "Netlista połączeń",
            "nodeCount": result.metadata.get("node_count"),
            "edgeCount": result.metadata.get("edge_count"),
            "components": len(meta_components),
            "essentialNodes": result.metadata.get("node_classification", {}).get("essential"),
        },
        "storage": {
            "type": "processed",
            "filename": relative.as_posix(),
        },
        "payload": {
            "netlist": result.metadata.get("netlist"),
            "nodeLabels": result.metadata.get("node_labels"),
            "connectedComponents": meta_components,
            "cycles": result.metadata.get("cycles"),
            "nodeClassification": result.metadata.get("node_classification"),
            "essentialNodeLabels": result.metadata.get("essential_node_labels"),
        },
    }

    store = _history_store()
    store.upsert_entry(entry)
    return entry
