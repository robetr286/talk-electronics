from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import Blueprint, current_app, jsonify, request, url_for

from ..services.ignore_store import IgnoreRegionStore

try:  # Pillow is optional during runtime; mask generation is skipped if unavailable
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - optional dependency
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore

JsonDict = Dict[str, Any]

ignore_bp = Blueprint("ignore_regions", __name__, url_prefix="/api/ignore-regions")
MUTATION_HEADER_DEFAULT = "X-Ignore-Token"
TIMESTAMP_TIMESPEC = "milliseconds"


class PayloadValidationError(ValueError):
    """Raised when the incoming payload cannot be processed."""


def _require_mutation_permission():
    """Validate that the caller can mutate ignore regions.

    If the config does not specify IGNORE_REGIONS_TOKEN we assume the
    environment is trusted (tests/local dev) and allow the request.
    """

    expected_token = current_app.config.get("IGNORE_REGIONS_TOKEN")
    if not expected_token:
        return None

    header_name = current_app.config.get("IGNORE_REGIONS_HEADER", MUTATION_HEADER_DEFAULT)
    provided = request.headers.get(header_name)

    if provided is None:
        # allow Authorization: Bearer <token> or legacy X-Api-Key headers
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            provided = authorization.split(" ", 1)[1]
        provided = provided or request.headers.get("X-Api-Key")

    if provided != expected_token:
        return jsonify({"error": "Brak uprawnień do modyfikacji stref ignorowanych"}), 403

    return None


# ---------------------------------------------------------------------------
# Helpers resolving application components
# ---------------------------------------------------------------------------


def _ignore_store() -> IgnoreRegionStore:
    return current_app.extensions["ignore_store"]


def _upload_folder() -> Path:
    return current_app.config["UPLOAD_FOLDER"]


def _relative_to_upload(path: Path | None) -> Optional[str]:
    if path is None:
        return None
    try:
        return path.relative_to(_upload_folder()).as_posix()
    except ValueError:
        return None


def _make_entry_id() -> str:
    return f"ignore-{uuid.uuid4().hex[:12]}"


def _existing_storage_path(entry: JsonDict, key: str) -> Optional[str]:
    storage = entry.get("storage") if isinstance(entry.get("storage"), dict) else {}
    if not isinstance(storage, dict):
        return None
    value = storage.get(key)
    return value if isinstance(value, str) else None


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _sanitize_point(point: Iterable[Any], width: int, height: int) -> Optional[List[float]]:
    try:
        x_raw, y_raw = point
        x = float(x_raw)
        y = float(y_raw)
    except Exception:
        return None
    if not (width > 0 and height > 0):
        return [x, y]
    return [
        _clamp(x, 0.0, float(width)),
        _clamp(y, 0.0, float(height)),
    ]


def _sanitize_points(points: Iterable[Iterable[Any]], width: int, height: int) -> List[List[float]]:
    sanitized: List[List[float]] = []
    for point in points or []:
        sanitized_point = _sanitize_point(point, width, height)
        if sanitized_point is not None:
            sanitized.append(sanitized_point)
    return sanitized


def _rect_to_polygon(points: Iterable[Iterable[Any]], width: int, height: int) -> Optional[List[List[float]]]:
    sanitized = _sanitize_points(points, width, height)
    if len(sanitized) < 2:
        return None
    (x1, y1), (x2, y2) = sanitized[0], sanitized[-1]
    left = min(x1, x2)
    right = max(x1, x2)
    top = min(y1, y2)
    bottom = max(y1, y2)
    if right - left <= 0 or bottom - top <= 0:
        return None
    return [
        [left, top],
        [right, top],
        [right, bottom],
        [left, bottom],
    ]


def _normalize_regions(objects: List[JsonDict], image_size: Tuple[int, int]) -> Tuple[List[JsonDict], List[JsonDict]]:
    """Return (polygon_like_regions, brush_like_regions)."""

    height, width = image_size
    polygon_regions: List[JsonDict] = []
    brush_regions: List[JsonDict] = []

    for index, obj in enumerate(objects):
        obj_type = (obj or {}).get("type")
        if obj_type not in {"rect", "poly", "polygon", "brush"}:
            continue

        if obj_type == "rect":
            polygon = _rect_to_polygon(obj.get("points", []), width, height)
            if not polygon:
                continue
            polygon_regions.append(
                {
                    "type": "polygon",
                    "points": polygon,
                    "source": {"type": "rect", "index": index},
                }
            )
            continue

        if obj_type in {"poly", "polygon"}:
            polygon = _sanitize_points(obj.get("points", []), width, height)
            if len(polygon) < 3:
                continue
            polygon_regions.append(
                {
                    "type": "polygon",
                    "points": polygon,
                    "source": {"type": "poly", "index": index},
                }
            )
            continue

        if obj_type == "brush":
            points = _sanitize_points(obj.get("points", []), width, height)
            if not points:
                continue
            size = int(obj.get("brushSize") or obj.get("brush_size") or 10)
            brush_regions.append(
                {
                    "type": "brush",
                    "points": points,
                    "brushSize": max(1, size),
                    "source": {"type": "brush", "index": index},
                }
            )

    return polygon_regions, brush_regions


# ---------------------------------------------------------------------------
# Mask/JSON persistence helpers
# ---------------------------------------------------------------------------


def _draw_brush(draw: Any, region: JsonDict) -> None:
    points = region.get("points") or []
    size = max(1, int(region.get("brushSize") or 10))
    tuples = [tuple(pt) for pt in points]
    if not tuples:
        return
    if len(tuples) == 1:
        x, y = tuples[0]
        radius = size / 2.0
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=255)
        return
    draw.line(tuples, fill=255, width=size, joint="curve")  # type: ignore[arg-type]
    radius = size / 2.0
    for x, y in (tuples[0], tuples[-1]):
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=255)


def _write_mask(
    entry_id: str,
    polygon_regions: List[JsonDict],
    brush_regions: List[JsonDict],
    image_size: Tuple[int, int],
) -> Optional[Path]:
    if Image is None or ImageDraw is None:
        return None
    height, width = image_size
    if width <= 0 or height <= 0:
        return None

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for region in polygon_regions:
        pts = region.get("points") or []
        if len(pts) >= 3:
            draw.polygon([tuple(pt) for pt in pts], fill=255)
    for region in brush_regions:
        _draw_brush(draw, region)

    mask_path = _ignore_store().masks_dir / f"{entry_id}.png"
    mask.save(mask_path)
    return mask_path


def _write_entry_json(entry_id: str, payload: JsonDict) -> Path:
    json_path = _ignore_store().json_dir / f"{entry_id}.json"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return json_path


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _bool_from_query(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y"}


def _serialize_entry(entry: JsonDict, include_payload: bool) -> JsonDict:
    data = dict(entry)
    if not include_payload:
        data.pop("objects", None)
        data.pop("ignoreRegions", None)
    storage = data.get("storage") or {}
    if isinstance(storage, dict):
        data["storageUrls"] = {
            "json": _build_download_url(storage.get("json")),
            "mask": _build_download_url(storage.get("mask")),
        }
    return data


def _build_download_url(relative_path: Optional[str]) -> Optional[str]:
    if not relative_path:
        return None
    return url_for("core.serve_upload", filename=relative_path)


def _validate_regions_payload(
    payload: JsonDict,
) -> Tuple[List[JsonDict], List[JsonDict], List[JsonDict], Tuple[int, int]]:
    if not isinstance(payload, dict):
        raise PayloadValidationError("Invalid JSON payload")

    objects = _parse_objects(payload)
    if not objects:
        raise PayloadValidationError("Pole 'objects' lub 'ignoreRegions' jest wymagane")

    image_shape = _parse_image_shape(payload)
    if image_shape is None:
        raise PayloadValidationError("Brak informacji o rozdzielczości obrazu (imageShape)")

    polygon_regions, brush_regions = _normalize_regions(objects, image_shape)
    if not polygon_regions and not brush_regions:
        raise PayloadValidationError("Brak poprawnych stref do zapisania")

    return objects, polygon_regions, brush_regions, image_shape


def _build_entry_json_blob(
    entry_id: str,
    image_shape: Tuple[int, int],
    objects: List[JsonDict],
    regions: List[JsonDict],
    created_at: str,
    updated_at: str,
) -> JsonDict:
    payload = {
        "id": entry_id,
        "imageShape": [image_shape[0], image_shape[1]],
        "objects": objects,
        "ignoreRegions": regions,
        "createdAt": created_at,
        "updatedAt": updated_at,
    }
    # Backwards compatibility for early adopters that inspected underscore version.
    payload["ignore_regions"] = regions
    return payload


# ---------------------------------------------------------------------------
# Payload parsing helpers
# ---------------------------------------------------------------------------


def _parse_image_shape(payload: JsonDict) -> Optional[Tuple[int, int]]:
    candidates = []
    for key in ("imageShape", "image_shape"):
        if key in payload:
            candidates.append(payload[key])
    image_meta = payload.get("image") or payload.get("imageMeta") or {}
    if isinstance(image_meta, dict) and {"height", "width"} <= image_meta.keys():
        candidates.append([image_meta.get("height"), image_meta.get("width")])
    for candidate in candidates:
        if isinstance(candidate, (list, tuple)) and len(candidate) >= 2:
            try:
                height = int(candidate[0])
                width = int(candidate[1])
            except (TypeError, ValueError):
                continue
            if height > 0 and width > 0:
                return height, width
    return None


def _parse_objects(payload: JsonDict) -> Optional[List[JsonDict]]:
    for key in ("objects", "ignoreRegions", "regions"):
        candidate = payload.get(key)
        if isinstance(candidate, list) and candidate:
            return [obj for obj in candidate if isinstance(obj, dict)]
    return None


def _build_entry_payload(
    entry_id: str,
    payload: JsonDict,
    objects: List[JsonDict],
    polygon_regions: List[JsonDict],
    brush_regions: List[JsonDict],
    image_size: Tuple[int, int],
    json_rel_path: Optional[str],
    mask_rel_path: Optional[str],
    created_at: str,
    updated_at: Optional[str] = None,
    existing_entry: Optional[JsonDict] = None,
) -> JsonDict:
    existing_source = (
        existing_entry.get("source")
        if isinstance(existing_entry, dict) and isinstance(existing_entry.get("source"), dict)
        else {}
    )
    existing_image = (
        existing_entry.get("image")
        if isinstance(existing_entry, dict) and isinstance(existing_entry.get("image"), dict)
        else {}
    )

    source_meta = payload.get("source") if isinstance(payload.get("source"), dict) else existing_source
    image_meta = payload.get("image") if isinstance(payload.get("image"), dict) else existing_image
    history_id = (
        payload.get("historyId")
        or source_meta.get("historyId")
        or image_meta.get("historyId")
        or existing_source.get("historyId")
    )
    existing_label = existing_entry.get("label") if isinstance(existing_entry, dict) else None
    label = payload.get("label") or source_meta.get("label") or existing_label or f"Ignore regions {created_at}"

    entry: JsonDict = {
        "id": entry_id,
        "label": label,
        "createdAt": created_at,
        "updatedAt": updated_at or created_at,
        "source": source_meta,
        "image": {
            "height": image_size[0],
            "width": image_size[1],
            "historyId": history_id,
            "filename": image_meta.get("filename"),
            "url": payload.get("imageUrl") or image_meta.get("url"),
        },
        "counts": {
            "objects": len(objects),
            "regions": len(polygon_regions) + len(brush_regions),
        },
        "objects": objects,
        "ignoreRegions": polygon_regions + brush_regions,
        "storage": {
            "json": json_rel_path,
            "mask": mask_rel_path,
        },
    }
    return entry


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@ignore_bp.post("")
def create_ignore_entry():  # type: ignore[override]
    permission_error = _require_mutation_permission()
    if permission_error:
        return permission_error

    payload = request.get_json(silent=True) or {}
    try:
        objects, polygon_regions, brush_regions, image_shape = _validate_regions_payload(payload)
    except PayloadValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    entry_id = _make_entry_id()
    mask_path = _write_mask(entry_id, polygon_regions, brush_regions, image_shape)
    created_at = datetime.now(timezone.utc).isoformat(timespec=TIMESTAMP_TIMESPEC)
    combined_regions = polygon_regions + brush_regions
    json_payload = _build_entry_json_blob(entry_id, image_shape, objects, combined_regions, created_at, created_at)
    json_path = _write_entry_json(entry_id, json_payload)

    entry = _build_entry_payload(
        entry_id,
        payload,
        objects,
        polygon_regions,
        brush_regions,
        image_shape,
        _relative_to_upload(json_path),
        _relative_to_upload(mask_path),
        created_at,
        created_at,
    )
    _ignore_store().upsert_entry(entry)
    response_entry = _serialize_entry(entry, include_payload=True)
    return jsonify({"entry": response_entry}), 201


@ignore_bp.get("")
def list_ignore_entries():  # type: ignore[override]
    entries = _ignore_store().list_entries()
    include_payload = _bool_from_query(request.args.get("includePayload"), default=False)
    source_kind = request.args.get("sourceKind")
    source_id = request.args.get("sourceId")
    history_id = request.args.get("historyId")
    limit = request.args.get("limit", type=int)

    def _matches(entry: JsonDict) -> bool:
        source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
        image_meta = entry.get("image") if isinstance(entry.get("image"), dict) else {}
        if source_kind and str(source.get("kind", "")).lower() != source_kind.lower():
            return False
        if source_id and str(source.get("id", "")) != source_id:
            return False
        if history_id:
            hist = image_meta.get("historyId") or source.get("historyId")
            if str(hist) != history_id:
                return False
        return True

    filtered = [entry for entry in entries if _matches(entry)]
    filtered.sort(key=lambda item: item.get("createdAt", ""), reverse=True)

    if limit is not None and limit >= 0:
        filtered = filtered[:limit]

    serialized = [_serialize_entry(entry, include_payload) for entry in filtered]
    return jsonify({"items": serialized, "count": len(serialized)})


@ignore_bp.get("/<entry_id>")
def get_ignore_entry(entry_id: str):  # type: ignore[override]
    entry = _ignore_store().get_entry(entry_id)
    if not entry:
        return jsonify({"error": "Nie znaleziono"}), 404
    return jsonify({"entry": _serialize_entry(entry, include_payload=True)})


@ignore_bp.put("/<entry_id>")
def update_ignore_entry(entry_id: str):  # type: ignore[override]
    permission_error = _require_mutation_permission()
    if permission_error:
        return permission_error

    existing = _ignore_store().get_entry(entry_id)
    if not existing:
        return jsonify({"error": "Nie znaleziono"}), 404

    payload = request.get_json(silent=True) or {}
    try:
        objects, polygon_regions, brush_regions, image_shape = _validate_regions_payload(payload)
    except PayloadValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    mask_path = _write_mask(entry_id, polygon_regions, brush_regions, image_shape)
    updated_at = datetime.now(timezone.utc).isoformat(timespec=TIMESTAMP_TIMESPEC)
    created_at = existing.get("createdAt") or existing.get("created_at") or updated_at

    combined_regions = polygon_regions + brush_regions
    json_payload = _build_entry_json_blob(entry_id, image_shape, objects, combined_regions, created_at, updated_at)
    json_path = _write_entry_json(entry_id, json_payload)

    json_rel = _relative_to_upload(json_path)
    mask_rel = _relative_to_upload(mask_path) or _existing_storage_path(existing, "mask")

    entry = _build_entry_payload(
        entry_id,
        payload,
        objects,
        polygon_regions,
        brush_regions,
        image_shape,
        json_rel,
        mask_rel,
        created_at,
        updated_at,
        existing_entry=existing,
    )
    _ignore_store().upsert_entry(entry)
    return jsonify({"entry": _serialize_entry(entry, include_payload=True)})


@ignore_bp.delete("/<entry_id>")
def delete_ignore_entry(entry_id: str):  # type: ignore[override]
    permission_error = _require_mutation_permission()
    if permission_error:
        return permission_error

    entry = _ignore_store().remove_entry(entry_id)
    if entry is None:
        return jsonify({"error": "Nie znaleziono"}), 404

    storage = entry.get("storage") if isinstance(entry.get("storage"), dict) else {}
    for key in ("json", "mask"):
        rel_path = storage.get(key)
        if isinstance(rel_path, str):
            target = _upload_folder() / rel_path
            try:
                target.unlink(missing_ok=True)
            except OSError:
                current_app.logger.warning("Nie udało się usunąć pliku %s", target)

    return jsonify({"removed": entry_id})
