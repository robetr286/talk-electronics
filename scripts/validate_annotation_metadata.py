#!/usr/bin/env python3
"""Validate component metadata from Label Studio annotations.

Checks region_comment metadata for:
- Required fields (designator, type)
- Decimal separator (must be dot, not comma)
- Valid value formats (with units: 4.7K, 100n, etc.)
- Component-specific field validation
- Reporting issues and warnings
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Valid component types from annotation schema
VALID_COMPONENT_TYPES = {
    "resistor",
    "capacitor",
    "inductor",
    "diode",
    "transistor",
    "op_amp",
    "connector",
    "power_rail",
    "ground",
    "ic_pin",
    "net_label",
    "measurement_point",
    "misc_symbol",
    "broken_line",
    "edge_connector",
}

# Required fields per component type
REQUIRED_FIELDS = {
    "resistor": {"designator", "type"},
    "capacitor": {"designator", "type"},
    "inductor": {"designator", "type"},
    "diode": {"designator", "type"},
    "transistor": {"designator", "type"},
    "op_amp": {"designator", "type"},
    # Labels and rails don't require designator
    "net_label": {"type"},
    "power_rail": {"type"},
    "ground": {"type"},
    "broken_line": {"type", "reason", "severity"},
    "edge_connector": {"type", "edge_id", "page"},
}

# Pattern for values with units (e.g., 4.7K, 100n, 0.039u)
VALUE_PATTERN = re.compile(r"^[0-9]+\.?[0-9]*([pnumkKMG]|pF|nF|uF|µF|mF|pH|nH|uH|µH|mH|ohm|Ω)?$", re.IGNORECASE)

# Pattern to detect comma as decimal separator (error)
COMMA_DECIMAL_PATTERN = re.compile(r"\d+,\d+")

# Pattern that targets only the comma between digits; used for replacements
DECIMAL_COMMA_ONLY_PATTERN = re.compile(r"(?<=\d),(?=\d)")

EDGE_ID_PATTERN = re.compile(r"^[ABCD][0-9]{2}$")
PAGE_PATTERN = re.compile(r"^\d{1,3}$")


def fix_decimal_commas_in_text(payload: str) -> tuple[str, bool]:
    """Replace decimal commas with dots inside a string."""
    if not isinstance(payload, str) or not payload:
        return payload, False
    fixed, count = DECIMAL_COMMA_ONLY_PATTERN.subn(".", payload)
    return fixed, count > 0


def fix_decimal_commas_recursively(value: Any) -> tuple[Any, bool]:
    """Walk nested dict/list/string structures and fix decimal commas."""
    if isinstance(value, str):
        return fix_decimal_commas_in_text(value)

    if isinstance(value, list):
        changed = False
        new_list = []
        for item in value:
            fixed_item, item_changed = fix_decimal_commas_recursively(item)
            new_list.append(fixed_item)
            changed = changed or item_changed
        return (new_list if changed else value), changed

    if isinstance(value, dict):
        changed = False
        for key, item in value.items():
            fixed_item, item_changed = fix_decimal_commas_recursively(item)
            if item_changed:
                value[key] = fixed_item
                changed = True
        return value, changed

    return value, False


@dataclass
class ValidationIssue:
    """Single validation issue."""

    severity: str  # "error" or "warning"
    field: str
    message: str
    region_id: Optional[str] = None
    task_id: Optional[int] = None


@dataclass
class ValidationReport:
    """Summary of validation results."""

    total_regions: int = 0
    regions_with_metadata: int = 0
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    decimal_fixes: List[str] = field(default_factory=list)
    data_modified: bool = False
    fixed_payload: Optional[Any] = None

    def add_error(self, field: str, message: str, region_id: Optional[str] = None, task_id: Optional[int] = None):
        """Add an error to the report."""
        self.errors.append(ValidationIssue("error", field, message, region_id, task_id))

    def add_warning(self, field: str, message: str, region_id: Optional[str] = None, task_id: Optional[int] = None):
        """Add a warning to the report."""
        self.warnings.append(ValidationIssue("warning", field, message, region_id, task_id))

    def has_issues(self) -> bool:
        """Check if there are any errors or warnings."""
        return len(self.errors) > 0 or len(self.warnings) > 0

    def print_summary(self):
        """Print validation summary."""
        print(f"\n{'='*60}")
        print("Validation Summary")
        print(f"{'='*60}")
        print(f"Total regions: {self.total_regions}")
        print(f"Regions with metadata: {self.regions_with_metadata}")
        print(f"Errors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")
        if self.decimal_fixes:
            print(f"Decimal fixes applied: {len(self.decimal_fixes)}")

        if self.errors:
            print(f"\n{'='*60}")
            print("ERRORS:")
            print(f"{'='*60}")
            for issue in self.errors:
                location = f"Task {issue.task_id}, Region {issue.region_id}" if issue.task_id else "Unknown"
                print(f"[{location}] {issue.field}: {issue.message}")

        if self.warnings:
            print(f"\n{'='*60}")
            print("WARNINGS:")
            print(f"{'='*60}")
            for issue in self.warnings:
                location = f"Task {issue.task_id}, Region {issue.region_id}" if issue.task_id else "Unknown"
                print(f"[{location}] {issue.field}: {issue.message}")

        print(f"{'='*60}\n")


def parse_metadata(region_comment: str) -> Dict[str, str]:
    """
    Parse region_comment into key=value pairs.

    Example: "designator=C12 type=capacitor value=100n polarity=unknown"
    Returns: {"designator": "C12", "type": "capacitor", ...}
    """
    metadata = {}
    if not region_comment or not isinstance(region_comment, str):
        return metadata

    # Split by spaces, handle quoted values if needed
    pairs = region_comment.strip().split()
    for pair in pairs:
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        metadata[key.strip()] = value.strip()

    return metadata


def validate_metadata(
    metadata: Dict[str, str],
    region_id: Optional[str] = None,
    task_id: Optional[int] = None,
    auto_fix_decimals: bool = False,
) -> List[ValidationIssue]:
    """
    Validate component metadata dictionary.

    Returns list of validation issues.
    """
    issues = []

    if not metadata:
        issues.append(ValidationIssue("warning", "metadata", "Empty metadata", region_id, task_id))
        return issues

    # Check required field: type
    component_type = metadata.get("type")
    if not component_type:
        issues.append(ValidationIssue("error", "type", "Missing required field 'type'", region_id, task_id))
        return issues

    # Validate type value
    if component_type not in VALID_COMPONENT_TYPES:
        issues.append(
            ValidationIssue("warning", "type", f"Unknown component type: '{component_type}'", region_id, task_id)
        )

    # Check required fields for this component type
    required = REQUIRED_FIELDS.get(component_type, {"type"})
    for req_field in required:
        if req_field not in metadata:
            issues.append(
                ValidationIssue(
                    "error",
                    req_field,
                    f"Missing required field '{req_field}' for type '{component_type}'",
                    region_id,
                    task_id,
                )
            )

    # Validate value field if present
    value = metadata.get("value")
    if value:
        # Check for comma as decimal separator (common mistake)
        if COMMA_DECIMAL_PATTERN.search(value):
            if auto_fix_decimals:
                fixed_value = value.replace(",", ".")
                metadata["value"] = fixed_value
                issues.append(
                    ValidationIssue(
                        "warning",
                        "value",
                        f"Auto-fixed decimal separator: '{value}' → '{fixed_value}'",
                        region_id,
                        task_id,
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        "error",
                        "value",
                        f"Invalid decimal separator (comma): '{value}'. Use dot: {value.replace(',', '.')}",
                        region_id,
                        task_id,
                    )
                )
        # Check value format
        elif not VALUE_PATTERN.match(value) and value.lower() != "unknown":
            issues.append(
                ValidationIssue(
                    "warning",
                    "value",
                    f"Value '{value}' doesn't match expected format (e.g., 4.7K, 100n)",
                    region_id,
                    task_id,
                )
            )

    # Component-specific validation
    if component_type == "capacitor":
        polarity = metadata.get("polarity")
        if not polarity:
            issues.append(
                ValidationIssue(
                    "warning",
                    "polarity",
                    "Capacitor missing 'polarity' field (should be: unknown, polarized, or np)",
                    region_id,
                    task_id,
                )
            )
        elif polarity not in ("unknown", "polarized", "electrolytic", "np"):
            issues.append(
                ValidationIssue("warning", "polarity", f"Invalid polarity value: '{polarity}'", region_id, task_id)
            )

    elif component_type == "resistor":
        power = metadata.get("power")
        if power and power != "unknown":
            # Validate power format (e.g., 0.25W, 1W)
            if not re.match(r"^\d+\.?\d*W$", power, re.IGNORECASE):
                issues.append(
                    ValidationIssue(
                        "warning",
                        "power",
                        f"Invalid power format: '{power}' (expected: 0.25W, 1W, etc.)",
                        region_id,
                        task_id,
                    )
                )

    elif component_type == "broken_line":
        reason = metadata.get("reason", "").strip()
        severity = metadata.get("severity")
        if reason and len(reason) < 6:
            issues.append(
                ValidationIssue(
                    "warning",
                    "reason",
                    "Reason should describe problem in >=6 chars",
                    region_id,
                    task_id,
                )
            )
        allowed_severity = {"minor", "major", "critical"}
        if severity:
            normalized_severity = severity.lower()
            if normalized_severity not in allowed_severity:
                issues.append(
                    ValidationIssue(
                        "error",
                        "severity",
                        "Severity must be one of: minor, major, critical",
                        region_id,
                        task_id,
                    )
                )
            elif severity != normalized_severity:
                issues.append(
                    ValidationIssue(
                        "warning",
                        "severity",
                        "Use lowercase values (minor/major/critical)",
                        region_id,
                        task_id,
                    )
                )

    elif component_type == "edge_connector":
        edge_id = metadata.get("edge_id", "").strip()
        page = metadata.get("page", "").strip()
        note = metadata.get("note")

        if edge_id and not EDGE_ID_PATTERN.match(edge_id):
            issues.append(
                ValidationIssue(
                    "error",
                    "edge_id",
                    "edge_id must follow <letter><two digits> (A05, B12, C03, D08)",
                    region_id,
                    task_id,
                )
            )

        if page and not PAGE_PATTERN.match(page):
            issues.append(
                ValidationIssue(
                    "error",
                    "page",
                    "page must be numeric (1-999) and match visible sheet number",
                    region_id,
                    task_id,
                )
            )

        if note and len(note) < 4:
            issues.append(
                ValidationIssue(
                    "warning",
                    "note",
                    "note should describe destination sheet (>=4 chars)",
                    region_id,
                    task_id,
                )
            )

    return issues


def validate_labelstudio_export(file_path: Path, fix_decimals: bool = False) -> ValidationReport:
    """Validate Label Studio export JSON file."""

    report = ValidationReport()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        report.add_error("file", f"Failed to load JSON: {e}")
        return report

    if not isinstance(data, list):
        report.add_error("format", "Expected JSON array of tasks")
        return report

    for task in data:
        if not isinstance(task, dict):
            continue

        task_id = task.get("id")
        annotations = task.get("annotations", [])

        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue

            results = annotation.get("result", [])
            for result in results:
                if not isinstance(result, dict):
                    continue

                report.total_regions += 1

                region_id = result.get("id")
                region_value = result.get("value") or {}
                region_comment = region_value.get("region_comment")

                if region_comment and fix_decimals:
                    fixed_comment, changed = fix_decimal_commas_in_text(region_comment)
                    if changed:
                        region_value["region_comment"] = fixed_comment
                        region_comment = fixed_comment
                        report.data_modified = True
                        report.decimal_fixes.append(f"Task {task_id} Region {region_id} (region_comment)")

                if not region_comment:
                    report.add_warning("region_comment", "Region missing metadata (region_comment)", region_id, task_id)
                    continue

                report.regions_with_metadata += 1
                metadata = parse_metadata(region_comment)
                issues = validate_metadata(metadata, region_id, task_id, auto_fix_decimals=fix_decimals)

                for issue in issues:
                    if issue.severity == "error":
                        report.errors.append(issue)
                    else:
                        report.warnings.append(issue)

    if fix_decimals and report.data_modified:
        report.fixed_payload = data

    return report


def validate_coco_with_metadata(file_path: Path, fix_decimals: bool = False) -> ValidationReport:
    """
    Validate COCO-style JSON with metadata in annotations.

    Some COCO exports include custom metadata field.
    """
    report = ValidationReport()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        report.add_error("file", f"Failed to load JSON: {e}")
        return report

    if not isinstance(data, dict):
        report.add_error("format", "Expected COCO-format JSON object")
        return report

    annotations = data.get("annotations", [])

    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue

        report.total_regions += 1

        ann_id = annotation.get("id")
        metadata = annotation.get("metadata") or annotation.get("attributes")

        if not metadata:
            report.add_warning("metadata", "Annotation missing metadata", str(ann_id))
            continue

        report.regions_with_metadata += 1

        container = None
        container_key = None
        if "metadata" in annotation and annotation["metadata"] is metadata:
            container = annotation
            container_key = "metadata"
        elif "attributes" in annotation and annotation["attributes"] is metadata:
            container = annotation
            container_key = "attributes"

        if isinstance(metadata, str):
            if fix_decimals:
                fixed_metadata, changed = fix_decimal_commas_in_text(metadata)
                if changed and container and container_key:
                    container[container_key] = fixed_metadata
                    metadata = fixed_metadata
                    report.data_modified = True
                    report.decimal_fixes.append(f"Annotation {ann_id} ({container_key})")
            metadata = parse_metadata(metadata)
        elif isinstance(metadata, dict) and fix_decimals:
            _, changed = fix_decimal_commas_recursively(metadata)
            if changed:
                report.data_modified = True
                report.decimal_fixes.append(f"Annotation {ann_id} ({container_key or 'metadata dict'})")

        issues = validate_metadata(metadata, str(ann_id), auto_fix_decimals=fix_decimals)

        for issue in issues:
            if issue.severity == "error":
                report.errors.append(issue)
            else:
                report.warnings.append(issue)

    if fix_decimals and report.data_modified:
        report.fixed_payload = data

    return report


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate component metadata in annotation files")
    parser.add_argument(
        "files", nargs="+", type=Path, help="Annotation files to validate (Label Studio or COCO format)"
    )
    parser.add_argument(
        "--format",
        choices=["auto", "labelstudio", "coco"],
        default="auto",
        help="Input file format (default: auto-detect)",
    )
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument(
        "--fix-decimals",
        action="store_true",
        help="Automatically replace decimal commas with dots and rewrite files in-place",
    )

    args = parser.parse_args(argv or sys.argv[1:])

    total_report = ValidationReport()

    for file_path in args.files:
        if not file_path.exists():
            print(f"[ERROR] File not found: {file_path}")
            continue

        print(f"\nValidating: {file_path}")
        print("-" * 60)

        # Auto-detect format
        file_format = args.format
        if file_format == "auto":
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        file_format = "labelstudio"
                    elif isinstance(data, dict) and "annotations" in data:
                        file_format = "coco"
                    else:
                        print("[WARNING] Unknown format, trying Label Studio")
                        file_format = "labelstudio"
            except Exception as e:
                print(f"[ERROR] Failed to detect format: {e}")
                continue

        # Validate based on format
        if file_format == "labelstudio":
            report = validate_labelstudio_export(file_path, fix_decimals=args.fix_decimals)
        else:  # coco
            report = validate_coco_with_metadata(file_path, fix_decimals=args.fix_decimals)

        # Print file-specific summary
        if report.has_issues():
            print(f"✗ Found {len(report.errors)} errors, {len(report.warnings)} warnings")
        else:
            print("✓ No issues found")

        if args.fix_decimals and report.data_modified and report.fixed_payload is not None:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report.fixed_payload, f, ensure_ascii=False, indent=2)
            print(f"→ Auto-fixed decimal commas in {file_path} ({len(report.decimal_fixes)} occurrence(s))")
            report.fixed_payload = None

        # Merge into total report
        total_report.total_regions += report.total_regions
        total_report.regions_with_metadata += report.regions_with_metadata
        total_report.errors.extend(report.errors)
        total_report.warnings.extend(report.warnings)
        total_report.decimal_fixes.extend(report.decimal_fixes)

    # Print overall summary
    total_report.print_summary()

    # Determine exit code
    if total_report.errors:
        return 1
    if args.strict and total_report.warnings:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
