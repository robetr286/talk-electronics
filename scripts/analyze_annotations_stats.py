#!/usr/bin/env python3
"""
Analyze annotation statistics from Label Studio or COCO format.

Generates reports showing:
- Number of annotations per category
- Percentage of annotations with metadata
- Missing designators analysis
- Value field completion statistics
- Summary reports in CSV/JSON format

Usage:
    python scripts/analyze_annotations_stats.py \
        --input data/annotations/labelstudio_exports/project_2025-11-06.json \
        --output reports/annotation_stats.json \
        --format labelstudio
"""

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set


@dataclass
class AnnotationStats:
    """Statistics for annotations."""

    total_regions: int = 0
    regions_with_metadata: int = 0
    regions_by_category: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    regions_with_designator: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    regions_with_value: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    unique_designators: Set[str] = field(default_factory=set)
    missing_designators: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert stats to dictionary for JSON export."""
        return {
            "summary": {
                "total_regions": self.total_regions,
                "regions_with_metadata": self.regions_with_metadata,
                "metadata_coverage_pct": round(
                    (self.regions_with_metadata / self.total_regions * 100) if self.total_regions > 0 else 0, 2
                ),
            },
            "by_category": {
                cat: {
                    "count": count,
                    "with_designator": self.regions_with_designator[cat],
                    "with_value": self.regions_with_value[cat],
                    "designator_coverage_pct": round(
                        (self.regions_with_designator[cat] / count * 100) if count > 0 else 0, 2
                    ),
                    "value_coverage_pct": round((self.regions_with_value[cat] / count * 100) if count > 0 else 0, 2),
                }
                for cat, count in sorted(self.regions_by_category.items(), key=lambda x: -x[1])
            },
            "designators": {
                "unique_count": len(self.unique_designators),
                "examples": sorted(list(self.unique_designators))[:20],  # First 20
            },
            "missing_designators": self.missing_designators[:50],  # First 50
        }

    def print_summary(self):
        """Print human-readable summary."""
        print("\n" + "=" * 70)
        print("ANNOTATION STATISTICS")
        print("=" * 70)

        print("\n📊 Overall Summary:")
        print(f"   Total regions:               {self.total_regions}")
        print(f"   Regions with metadata:       {self.regions_with_metadata}")
        metadata_pct = (self.regions_with_metadata / self.total_regions * 100) if self.total_regions > 0 else 0
        print(f"   Metadata coverage:           {metadata_pct:.1f}%")
        print(f"   Unique designators:          {len(self.unique_designators)}")

        print("\n📈 Annotations by Category:")
        print("   Category             Count    w/ Designator    w/ Value")
        print("   -------------------- ------  --------------  ----------")

        for cat in sorted(self.regions_by_category.keys(), key=lambda x: -self.regions_by_category[x]):
            count = self.regions_by_category[cat]
            with_des = self.regions_with_designator[cat]
            with_val = self.regions_with_value[cat]
            des_pct = (with_des / count * 100) if count > 0 else 0
            val_pct = (with_val / count * 100) if count > 0 else 0

            print(f"   {cat:<20} {count:>6}  {with_des:>6} ({des_pct:>5.1f}%)  {with_val:>6} ({val_pct:>5.1f}%)")

        if self.unique_designators:
            print("\n🏷️  Sample Designators (first 20):")
            for designator in sorted(list(self.unique_designators))[:20]:
                print(f"   - {designator}")

        if self.missing_designators:
            print("\n⚠️  Regions Missing Designators (first 10):")
            for item in self.missing_designators[:10]:
                cat = item.get("category", "unknown")
                region_id = item.get("region_id", "unknown")
                task_id = item.get("task_id", "unknown")
                print(f"   - Task {task_id}, Region {region_id}: {cat}")

        print("\n" + "=" * 70 + "\n")


def parse_metadata(region_comment: str) -> Dict[str, str]:
    """Parse region_comment into key=value pairs."""
    metadata = {}
    if not region_comment or not isinstance(region_comment, str):
        return metadata

    pairs = region_comment.strip().split()
    for pair in pairs:
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        metadata[key.strip()] = value.strip()

    return metadata


def analyze_labelstudio_export(file_path: Path) -> AnnotationStats:
    """Analyze Label Studio export JSON file."""
    stats = AnnotationStats()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        return stats

    if not isinstance(data, list):
        print("❌ Expected JSON array of tasks")
        return stats

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

                stats.total_regions += 1

                # Get category
                value = result.get("value", {})
                region_id = result.get("id")

                # Determine category from label type
                category = None
                if "rectanglelabels" in value:
                    labels = value.get("rectanglelabels", [])
                    category = labels[0] if labels else "unknown"
                elif "polygonlabels" in value:
                    labels = value.get("polygonlabels", [])
                    category = labels[0] if labels else "unknown"

                if not category:
                    category = "unknown"

                stats.regions_by_category[category] += 1

                # Check for metadata
                region_comment = value.get("region_comment")

                if not region_comment:
                    # Missing designator
                    stats.missing_designators.append(
                        {
                            "task_id": task_id,
                            "region_id": region_id,
                            "category": category,
                        }
                    )
                    continue

                stats.regions_with_metadata += 1

                # Parse metadata
                metadata = parse_metadata(region_comment)

                # Check for designator
                designator = metadata.get("designator")
                if designator:
                    stats.regions_with_designator[category] += 1
                    stats.unique_designators.add(designator)
                else:
                    # Missing designator in metadata
                    stats.missing_designators.append(
                        {
                            "task_id": task_id,
                            "region_id": region_id,
                            "category": category,
                            "has_metadata": True,
                        }
                    )

                # Check for value
                if metadata.get("value"):
                    stats.regions_with_value[category] += 1

    return stats


def analyze_coco_format(file_path: Path) -> AnnotationStats:
    """Analyze COCO format JSON file."""
    stats = AnnotationStats()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        return stats

    if not isinstance(data, dict):
        print("❌ Expected COCO-format JSON object")
        return stats

    # Build category index
    categories = {cat["id"]: cat["name"] for cat in data.get("categories", [])}

    # Analyze annotations
    annotations = data.get("annotations", [])

    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue

        stats.total_regions += 1

        ann_id = annotation.get("id")
        category_id = annotation.get("category_id")
        category = categories.get(category_id, "unknown")

        stats.regions_by_category[category] += 1

        # Check for metadata/attributes
        metadata = annotation.get("metadata") or annotation.get("attributes")

        if not metadata:
            stats.missing_designators.append(
                {
                    "annotation_id": ann_id,
                    "category": category,
                }
            )
            continue

        stats.regions_with_metadata += 1

        # Parse metadata if it's a string
        if isinstance(metadata, str):
            metadata = parse_metadata(metadata)

        # Check for designator
        designator = metadata.get("designator")
        if designator:
            stats.regions_with_designator[category] += 1
            stats.unique_designators.add(designator)
        else:
            stats.missing_designators.append(
                {
                    "annotation_id": ann_id,
                    "category": category,
                    "has_metadata": True,
                }
            )

        # Check for value
        if metadata.get("value"):
            stats.regions_with_value[category] += 1

    return stats


def export_to_csv(stats: AnnotationStats, output_path: Path):
    """Export statistics to CSV format."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Write header
        writer.writerow(["Category", "Total Count", "With Designator", "Designator %", "With Value", "Value %"])

        # Write data
        for cat in sorted(stats.regions_by_category.keys(), key=lambda x: -stats.regions_by_category[x]):
            count = stats.regions_by_category[cat]
            with_des = stats.regions_with_designator[cat]
            with_val = stats.regions_with_value[cat]
            des_pct = (with_des / count * 100) if count > 0 else 0
            val_pct = (with_val / count * 100) if count > 0 else 0

            writer.writerow([cat, count, with_des, f"{des_pct:.1f}", with_val, f"{val_pct:.1f}"])


def main():
    parser = argparse.ArgumentParser(description="Analyze annotation statistics")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Input annotation file")
    parser.add_argument("--output", "-o", type=Path, help="Output file for statistics (JSON or CSV)")
    parser.add_argument(
        "--format",
        choices=["auto", "labelstudio", "coco"],
        default="auto",
        help="Input file format (default: auto-detect)",
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"❌ Error: Input file not found: {args.input}")
        return 1

    # Auto-detect format
    file_format = args.format
    if file_format == "auto":
        try:
            with open(args.input, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    file_format = "labelstudio"
                elif isinstance(data, dict) and "annotations" in data:
                    file_format = "coco"
                else:
                    print("⚠️  Unknown format, trying Label Studio")
                    file_format = "labelstudio"
        except Exception as e:
            print(f"❌ Error detecting format: {e}")
            return 1

    print(f"📖 Analyzing: {args.input}")
    print(f"📋 Format: {file_format}")

    # Analyze
    if file_format == "labelstudio":
        stats = analyze_labelstudio_export(args.input)
    else:  # coco
        stats = analyze_coco_format(args.input)

    # Print summary
    stats.print_summary()

    # Export if output specified
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)

        if args.output.suffix == ".csv":
            export_to_csv(stats, args.output)
            print(f"💾 CSV report saved to: {args.output}")
        else:
            # Default to JSON
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(stats.to_dict(), f, indent=2)
            print(f"💾 JSON report saved to: {args.output}")

    return 0


if __name__ == "__main__":
    exit(main())
