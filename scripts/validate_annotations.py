#!/usr/bin/env python3
"""Lightweight validation for COCO-style annotation files.

Checks include:
- categories are unique across files,
- annotations reference known images and categories,
- bounding boxes are positive and within image bounds,
- optional class mapping consistency.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from talk_electronic.services.annotation_loader import (
    detect_annotation_format,
    load_annotations,
    validate_coco_annotations,
)

jsonschema_spec = importlib.util.find_spec("jsonschema")
if jsonschema_spec is not None:  # pragma: no cover - import side effects not tested
    jsonschema = importlib.import_module("jsonschema")
else:  # pragma: no cover - optional dependency
    jsonschema = None

BBox = Tuple[float, float, float, float]


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - CLI guard
        raise SystemExit(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:  # pragma: no cover - CLI guard
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def _bbox_valid(bbox: Iterable[float], image_size: Tuple[int, int]) -> bool:
    try:
        x, y, width, height = map(float, bbox)
    except (TypeError, ValueError):
        return False
    if width <= 0 or height <= 0:
        return False
    max_x, max_y = image_size
    if x < 0 or y < 0:
        return False
    if x + width > max_x + 1e-6:
        return False
    if y + height > max_y + 1e-6:
        return False
    return True


def _index_images(payload: dict) -> Dict[int, Tuple[int, int]]:
    images = payload.get("images")
    if not isinstance(images, list):
        return {}
    index: Dict[int, Tuple[int, int]] = {}
    for entry in images:
        if not isinstance(entry, dict):
            continue
        image_id = entry.get("id")
        width = entry.get("width")
        height = entry.get("height")
        if isinstance(image_id, int) and isinstance(width, int) and isinstance(height, int):
            index[image_id] = (width, height)
    return index


def _index_categories(payload: dict) -> Dict[int, str]:
    categories = payload.get("categories")
    if not isinstance(categories, list):
        return {}
    index: Dict[int, str] = {}
    for entry in categories:
        if not isinstance(entry, dict):
            continue
        category_id = entry.get("id")
        name = entry.get("name")
        if isinstance(category_id, int) and isinstance(name, str):
            index[category_id] = name
    return index


def validate_payload(
    payload: dict,
    known_categories: Dict[int, str],
    *,
    schema: dict | None = None,
    origin: str | None = None,
) -> List[str]:
    issues: List[str] = []

    if schema is not None:
        if jsonschema is None:
            issues.append("jsonschema package not available; skipping schema validation")
        else:
            try:
                jsonschema.validate(payload, schema)
            except jsonschema.ValidationError as exc:
                issues.append(f"Schema validation error: {exc.message}")
                return issues

    image_index = _index_images(payload)
    file_categories = _index_categories(payload)
    if not file_categories:
        issues.append("No categories found")

    for category_id, name in file_categories.items():
        existing = known_categories.get(category_id)
        if existing and existing != name:
            issues.append(
                f"Category id {category_id} name mismatch: '{name}' vs '{existing}'",
            )
        known_categories.setdefault(category_id, name)

    annotations = payload.get("annotations")
    if not isinstance(annotations, list):
        issues.append("No annotations array")
        return issues

    for index, annotation in enumerate(annotations):
        if not isinstance(annotation, dict):
            issues.append(f"Annotation #{index} is not an object")
            continue
        image_id = annotation.get("image_id")
        if image_id not in image_index:
            issues.append(f"Annotation #{index} references unknown image_id={image_id}")
            continue
        category_id = annotation.get("category_id")
        if category_id not in file_categories and category_id not in known_categories:
            issues.append(f"Annotation #{index} references unknown category_id={category_id}")
        bbox = annotation.get("bbox")
        if not _bbox_valid(bbox, image_index[image_id]):
            issues.append(f"Annotation #{index} has invalid bbox={bbox}")

    is_valid_coco, coco_errors = validate_coco_annotations(payload)
    if not is_valid_coco:
        issues.extend(coco_errors)

    if origin and issues:
        issues = [f"{origin}: {msg}" for msg in issues]
    return issues


def validate_file(path: Path, known_categories: Dict[int, str], *, schema: dict | None = None) -> List[str]:
    payload = _load_json(path)
    return validate_payload(payload, known_categories, schema=schema, origin=str(path))


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate COCO-style annotation files")
    parser.add_argument("files", nargs="+", type=Path, help="Paths to annotation JSON files")
    parser.add_argument("--schema", type=Path, default=None, help="Optional JSON Schema for structural validation")
    parser.add_argument(
        "--auto-convert", action="store_true", help="Automatically convert rotated rectangles to polygons"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write converted files (defaults next to source when --auto-convert)",
    )
    parser.add_argument("--report-json", type=Path, default=None, help="Optional path to write JSON report")
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    schema_payload = None
    if args.schema:
        schema_payload = _load_json(args.schema)

    known_categories: Dict[int, str] = {}
    total_issues = 0
    report: List[Dict[str, object]] = []

    for path in args.files:
        conversion_info = None
        payload = _load_json(path)

        if args.auto_convert:
            conversion_info = detect_annotation_format(payload)
            payload = load_annotations(path)
            if args.output_dir:
                args.output_dir.mkdir(parents=True, exist_ok=True)
                target = args.output_dir / path.name
                target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            elif conversion_info and conversion_info.get("needs_conversion"):
                target = path.with_suffix(".converted.json")
                target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        issues = validate_payload(payload, known_categories, schema=schema_payload, origin=str(path))

        if issues:
            print(f"[FAIL] {path}")
            for entry in issues:
                print(f"  - {entry}")
            total_issues += len(issues)
        else:
            print(f"[OK] {path}")

        report.append(
            {
                "file": str(path),
                "issues": issues,
                "issueCount": len(issues),
                "converted": bool(args.auto_convert and conversion_info and conversion_info.get("needs_conversion")),
                "format": conversion_info.get("format") if conversion_info else None,
                "rotated": conversion_info.get("rotated_count") if conversion_info else None,
            }
        )

    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if total_issues:
        print(f"Validation completed with {total_issues} issue(s)")
        return 1
    print("Validation successful")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
