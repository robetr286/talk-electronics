from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import Blueprint, current_app, jsonify, request, url_for

from ..services.edge_connector_store import EdgeConnectorStore

JsonDict = Dict[str, Any]

edge_connectors_bp = Blueprint("edge_connectors", __name__, url_prefix="/api/edge-connectors")
TIMESTAMP_TIMESPEC = "milliseconds"
EDGE_ID_PATTERN = re.compile(r"^[ABCD][0-9]{2}$")
PAGE_PATTERN = re.compile(r"^\d{1,3}$")


def _error_response(message: str, code: str, status: int):
    return jsonify({"error": message, "errorCode": code}), status


class ConnectorValidationError(ValueError):
    """Raised when incoming payload is invalid."""


def _edge_store() -> EdgeConnectorStore:
    return current_app.extensions["edge_connector_store"]


def _upload_folder():
    return current_app.config["UPLOAD_FOLDER"]


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec=TIMESTAMP_TIMESPEC)


def _relative_to_upload(path) -> Optional[str]:
    if path is None:
        return None
    try:
        return path.relative_to(_upload_folder()).as_posix()
    except ValueError:
        return None


def _require_mutation_permission():
    expected = current_app.config.get("EDGE_CONNECTORS_TOKEN") or current_app.config.get("IGNORE_REGIONS_TOKEN")
    if not expected:
        return None
    header_name = current_app.config.get("EDGE_CONNECTORS_HEADER", "X-Edge-Token")
    provided = request.headers.get(header_name)
    if provided is None:
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            provided = authorization.split(" ", 1)[1]
        provided = provided or request.headers.get("X-Api-Key")
    if provided != expected:
        return _error_response("Brak uprawnień do modyfikacji konektorów", "FORBIDDEN", 403)
    return None


def _validate_geometry(payload: JsonDict) -> JsonDict:
    geometry = payload.get("geometry")
    if not isinstance(geometry, dict):
        raise ConnectorValidationError("Pole 'geometry' jest wymagane (dict)")
    geom_type = geometry.get("type")
    points = geometry.get("points")
    if geom_type not in {"polygon", "rect", "polyline"}:
        raise ConnectorValidationError("Pole 'geometry.type' musi być polygon/rect/polyline")
    if not isinstance(points, list) or len(points) < 2:
        raise ConnectorValidationError("Pole 'geometry.points' musi zawierać co najmniej 2 punkty")
    return {"type": geom_type, "points": points}


def _roi_from_geometry(geometry: Optional[JsonDict]) -> Optional[Dict[str, int]]:
    if not geometry or not isinstance(geometry, dict):
        return None
    points = geometry.get("points")
    if not isinstance(points, list) or len(points) < 2:
        return None
    xs = []
    ys = []
    for pt in points:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        try:
            x_val = int(round(float(pt[0])))
            y_val = int(round(float(pt[1])))
        except (TypeError, ValueError):
            continue
        xs.append(x_val)
        ys.append(y_val)
    if not xs or not ys:
        return None
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return {"x": min_x, "y": min_y, "w": max(max_x - min_x, 1), "h": max(max_y - min_y, 1)}


def _validate_payload(payload: JsonDict) -> JsonDict:
    if not isinstance(payload, dict):
        raise ConnectorValidationError("Nieprawidłowy JSON")

    edge_id = payload.get("edgeId") or payload.get("edge_id")
    page = payload.get("page")
    if not isinstance(edge_id, str) or not EDGE_ID_PATTERN.match(edge_id):
        raise ConnectorValidationError("edgeId musi mieć format A05/B12/C03/D08")
    if not isinstance(page, str) or not PAGE_PATTERN.match(page):
        raise ConnectorValidationError("page musi być liczbą (1-999)")

    geometry = _validate_geometry(payload)

    data: JsonDict = {
        "edgeId": edge_id,
        "page": page,
        "note": payload.get("note") or None,
        "sheetId": payload.get("sheetId") or None,
        "netName": payload.get("netName") or None,
        "historyId": payload.get("historyId") or None,
        "label": payload.get("label") or edge_id,
        "source": payload.get("source") if isinstance(payload.get("source"), dict) else {},
        "geometry": geometry,
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }
    return data


def _build_entry(
    entry_id: str, data: JsonDict, created_at: str, updated_at: Optional[str], storage_path: Optional[str]
) -> JsonDict:
    entry = {
        "id": entry_id,
        "edgeId": data["edgeId"],
        "page": data["page"],
        "label": data.get("label") or data["edgeId"],
        "note": data.get("note"),
        "sheetId": data.get("sheetId"),
        "netName": data.get("netName"),
        "historyId": data.get("historyId"),
        "source": data.get("source") or {},
        "metadata": data.get("metadata") or {},
        "createdAt": created_at,
        "updatedAt": updated_at or created_at,
        "storage": {"json": storage_path},
    }
    return entry


def _serialize_entry(entry: JsonDict, include_payload: bool) -> JsonDict:
    data = dict(entry)
    storage = data.get("storage") or {}
    if isinstance(storage, dict):
        data["storageUrls"] = {"json": _build_download_url(storage.get("json"))}
    if not include_payload:
        data.pop("payload", None)
    return data


def _build_download_url(relative_path: Optional[str]) -> Optional[str]:
    if not relative_path:
        return None
    return url_for("core.serve_upload", filename=relative_path)


def _combine_entry_with_payload(entry: JsonDict, payload: Optional[JsonDict]) -> JsonDict:
    data = dict(entry)
    if payload:
        data["payload"] = payload
    return data


def _load_entry(entry_id: str) -> Optional[JsonDict]:
    store = _edge_store()
    entry = store.get_entry(entry_id)
    if entry is None:
        return None
    payload = store.load_payload(entry_id)
    return _combine_entry_with_payload(entry, payload)


@edge_connectors_bp.get("/")
def list_connectors():
    include_payload = request.args.get("includePayload") == "1"
    entries = [_serialize_entry(entry, include_payload=False) for entry in _edge_store().list_entries()]
    if include_payload:
        for item in entries:
            payload = _edge_store().load_payload(item["id"])
            if payload:
                item["payload"] = payload
    return jsonify({"items": entries})


@edge_connectors_bp.get("/<entry_id>")
def get_connector(entry_id: str):
    entry = _load_entry(entry_id)
    if entry is None:
        return jsonify({"error": "Nie znaleziono konektora"}), 404
    return jsonify(entry)


@edge_connectors_bp.post("/")
def create_connector():
    permission = _require_mutation_permission()
    if permission is not None:
        return permission
    try:
        payload = _validate_payload(request.get_json(silent=True) or {})
    except ConnectorValidationError as exc:
        return _error_response(str(exc), "INVALID_CONNECTOR", 400)

    entry_id = f"edge-{uuid.uuid4().hex[:12]}"
    created_at = _timestamp()
    full_payload = dict(payload)
    full_payload.update({"id": entry_id, "createdAt": created_at, "updatedAt": created_at})

    store = _edge_store()
    json_path = store.save_payload(entry_id, full_payload)
    rel_path = _relative_to_upload(json_path)
    entry = _build_entry(entry_id, payload, created_at, created_at, rel_path)
    store.upsert_entry(entry)
    return jsonify(_combine_entry_with_payload(entry, full_payload)), 201


@edge_connectors_bp.put("/<entry_id>")
@edge_connectors_bp.patch("/<entry_id>")
def update_connector(entry_id: str):
    permission = _require_mutation_permission()
    if permission is not None:
        return permission
    store = _edge_store()
    existing = store.get_entry(entry_id)
    if existing is None:
        return _error_response("Nie znaleziono konektora", "CONNECTOR_NOT_FOUND", 404)
    try:
        payload = _validate_payload(request.get_json(silent=True) or {})
    except ConnectorValidationError as exc:
        return _error_response(str(exc), "INVALID_CONNECTOR", 400)

    created_at = existing.get("createdAt") or _timestamp()
    updated_at = _timestamp()

    full_payload = dict(payload)
    full_payload.update({"id": entry_id, "createdAt": created_at, "updatedAt": updated_at})

    json_path = store.save_payload(entry_id, full_payload)
    rel_path = _relative_to_upload(json_path)
    entry = _build_entry(entry_id, payload, created_at, updated_at, rel_path)
    store.upsert_entry(entry)
    return jsonify(_combine_entry_with_payload(entry, full_payload))


@edge_connectors_bp.delete("/<entry_id>")
def delete_connector(entry_id: str):
    permission = _require_mutation_permission()
    if permission is not None:
        return permission
    removed = _edge_store().remove_entry(entry_id)
    if removed is None:
        return _error_response("Nie znaleziono konektora", "CONNECTOR_NOT_FOUND", 404)
    return jsonify({"status": "deleted", "id": entry_id})


@edge_connectors_bp.get("/detect")
def detect_connectors():
    """Prosty endpoint detekcji: jeśli podano `token` i istnieje odpowiadający plik preview,
    uruchamia heurystyczny detektor prostokątnych kształtów przy krawędziach obrazu.
    W przeciwnym razie zwraca deterministyczny mock.
    """
    page = request.args.get("page") or "1"
    token = request.args.get("token") or None
    try:
        shrink = float(request.args.get("shrink", 0))
    except (TypeError, ValueError):
        shrink = 0.0
    shrink = max(0.0, min(shrink, 0.15))

    # Spróbuj znaleźć plik preview odpowiadający tokenowi (np. {token}_page_{page}.png) lub _source
    detection_reason = None
    debug_info = None
    if token:
        from pathlib import Path

        import cv2

        upload_folder = _upload_folder()
        candidates = [
            Path(upload_folder) / f"{token}_page_{page}.png",
            Path(upload_folder) / f"{token}_page_{page}.jpg",
            Path(upload_folder) / f"{token}_page_{page}.jpeg",
            Path(upload_folder) / f"{token}_source.png",
            Path(upload_folder) / f"{token}_source.jpg",
            Path(upload_folder) / f"{token}_source.jpeg",
        ]
        for p in candidates:
            if p.exists():
                try:
                    img = cv2.imread(str(p))
                    if img is None:
                        detection_reason = "invalid_image"
                        continue
                    h, w = img.shape[:2]
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    blur = cv2.GaussianBlur(gray, (5, 5), 0)
                    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    contour_count = len(contours)

                    # wybierz największy sensowny kontur (poluzowane progi + bez wymogu krawędzi)
                    best = None
                    best_area = 0
                    for cnt in contours:
                        area = cv2.contourArea(cnt)
                        if area < 50 or area > w * h * 0.95:
                            continue
                        if area > best_area:
                            best = cnt
                            best_area = area

                    fallback_reason = None

                    if best is None:
                        # Spróbuj wyznaczyć box po prostu z obszaru niebiałego; jeśli dalej nic, zwróć cały obraz.
                        inv = 255 - th
                        non_zero = cv2.findNonZero(inv)
                        if non_zero is not None:
                            x, y, bw, bh = cv2.boundingRect(non_zero)
                            fallback_reason = "mask_bbox"
                        else:
                            x, y, bw, bh = 0, 0, w, h
                            fallback_reason = "full_image_bbox"
                    else:
                        x, y, bw, bh = cv2.boundingRect(best)

                    if bw > 0 and bh > 0:
                        # Opcjonalne zmniejszenie ramki (shrink) dla testów UX
                        if shrink > 0:
                            dx = int(round(bw * shrink))
                            dy = int(round(bh * shrink))
                            if dx > 0 or dy > 0:
                                x = max(0, x + dx)
                                y = max(0, y + dy)
                                bw = max(1, bw - 2 * dx)
                                bh = max(1, bh - 2 * dy)

                        poly = [
                            [int(x), int(y)],
                            [int(x + bw), int(y)],
                            [int(x + bw), int(y + bh)],
                            [int(x), int(y + bh)],
                        ]
                        now_ts = _timestamp()
                        item = {
                            "id": f"detect-{uuid.uuid4().hex[:8]}",
                            "edgeId": "A01",
                            "page": str(page),
                            "label": "heuristic_detected",
                            "payload": {
                                "edgeId": "A01",
                                "page": str(page),
                                "geometry": {"type": "rect", "points": poly},
                                "source": {"token": token, "file": p.name},
                                "meta": {
                                    "roi_abs": {"x": int(x), "y": int(y), "w": int(bw), "h": int(bh)},
                                    "roi_rel": {
                                        "x": round(x / w, 4) if w else 0,
                                        "y": round(y / h, 4) if h else 0,
                                        "w": round(bw / w, 4) if w else 0,
                                        "h": round(bh / h, 4) if h else 0,
                                    },
                                    "shrink": shrink,
                                    +"image_size": [int(w), int(h)],
                                },
                            },
                            "createdAt": now_ts,
                            "updatedAt": now_ts,
                        }
                        reason = "heuristic"
                        if fallback_reason:
                            reason = fallback_reason
                        debug_info = {
                            "reason": reason,
                            "contours": contour_count,
                            "image_size": [w, h],
                            "file": p.name,
                            "shrink": shrink,
                        }
                        return jsonify({"items": [item], "reason": reason, "debug": debug_info})

                    detection_reason = "no_contours"
                    debug_info = {
                        "reason": detection_reason,
                        "contours": contour_count,
                        "image_size": [w, h],
                        "file": p.name,
                        "shrink": shrink,
                    }
                except Exception as exc:
                    detection_reason = "error"
                    current_app.logger.exception("Heuristic detection failed: %s", exc)
                    break
        if detection_reason is None:
            detection_reason = "no_image"

    # Fallback: deterministyczny mock
    mock_item = {
        "id": f"detect-{uuid.uuid4().hex[:8]}",
        "edgeId": "A01",
        "page": str(page),
        "label": "mock_detected",
        "payload": {
            "edgeId": "A01",
            "page": str(page),
            "geometry": {"type": "rect", "points": [[10, 10], [120, 10], [120, 40], [10, 40]]},
            "source": {"token": token} if token else {},
        },
        "createdAt": _timestamp(),
        "updatedAt": _timestamp(),
    }

    response: JsonDict = {"items": [mock_item]}
    if detection_reason:
        response["reason"] = detection_reason
    if debug_info:
        response["debug"] = debug_info

    return jsonify(response)
