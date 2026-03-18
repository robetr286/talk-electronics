#!/usr/bin/env python
"""
Batch generator syntetycznych schematów elektronicznych.

Automatycznie generuje wiele schematów z różnymi parametrami:
- Losowa liczba komponentów (5-20)
- Różne seedy dla reprodukowalności
- Konfigurowalna liczba schematów do wygenerowania

Usage:
    python scripts/synthetic/batch_generate.py --num-schematics 50
    python scripts/synthetic/batch_generate.py --num-schematics 100 --min-components 10 --max-components 30
"""

import argparse
import json
import random
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Batch generate synthetic electronic schematics")
    parser.add_argument("--num-schematics", type=int, default=50, help="Number of schematics to generate (default: 50)")
    parser.add_argument(
        "--min-components", type=int, default=5, help="Minimum number of components per schematic (default: 5)"
    )
    parser.add_argument(
        "--max-components", type=int, default=20, help="Maximum number of components per schematic (default: 20)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/synthetic/images_raw",
        help="Output directory for generated images (default: data/synthetic/images_raw)",
    )
    parser.add_argument(
        "--metadata-dir",
        type=str,
        default="data/synthetic/annotations",
        help="Output directory for metadata JSON files (default: data/synthetic/annotations)",
    )
    parser.add_argument("--start-seed", type=int, default=1, help="Starting seed for random generation (default: 1)")
    parser.add_argument("--width", type=int, default=1000, help="Canvas width in pixels (default: 1000)")
    parser.add_argument("--height", type=int, default=800, help="Canvas height in pixels (default: 800)")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")

    return parser.parse_args()


def generate_schematic(
    index: int,
    num_components: int,
    seed: int,
    output_path: Path,
    metadata_path: Path,
    width: int,
    height: int,
    dry_run: bool = False,
) -> bool:
    """
    Generate a single schematic using generate_schematic.py.

    Args:
        index: Schematic index (for naming)
        num_components: Number of components to generate
        seed: Random seed
        output_path: Path to save PNG image
        metadata_path: Path to save JSON metadata
        width: Canvas width
        height: Canvas height
        dry_run: If True, print command without executing

    Returns:
        True if successful, False otherwise
    """
    cmd = [
        "python",  # Use python from PATH (respects active conda env)
        "scripts/synthetic/generate_schematic.py",
        "--output",
        str(output_path),
        "--metadata",
        str(metadata_path),
        "--components",
        str(num_components),
        "--seed",
        str(seed),
        "--width",
        str(width),
        "--height",
        str(height),
    ]

    if dry_run:
        print(f"[DRY RUN] {' '.join(cmd)}")
        return True

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error generating schematic {index:03d}: {e}")
        print(f"   stdout: {e.stdout}")
        print(f"   stderr: {e.stderr}")
        return False


def create_metadata_summary(output_dir: Path, metadata_dir: Path, schematics_info: List[Dict], args) -> None:
    """
    Create a summary JSON file with generation metadata.

    Args:
        output_dir: Directory with generated images
        metadata_dir: Directory with metadata JSON files
        schematics_info: List of dicts with info about each schematic
        args: Command line arguments
    """
    summary = {
        "generation_date": datetime.now().isoformat(),
        "total_schematics": len(schematics_info),
        "parameters": {
            "min_components": args.min_components,
            "max_components": args.max_components,
            "canvas_width": args.width,
            "canvas_height": args.height,
            "start_seed": args.start_seed,
        },
        "schematics": schematics_info,
        "statistics": {
            "total_components": sum(s["num_components"] for s in schematics_info),
            "avg_components_per_schematic": (
                sum(s["num_components"] for s in schematics_info) / len(schematics_info) if schematics_info else 0
            ),
        },
    }

    summary_path = metadata_dir / "batch_metadata.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n📊 Zapisano podsumowanie: {summary_path}")


def main():
    """Main batch generation function."""
    args = parse_args()

    # Create output directories
    output_dir = Path(args.output_dir)
    metadata_dir = Path(args.metadata_dir)

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)

    print("🚀 Batch Generator Syntetycznych Schematów")
    print("=" * 60)
    print(f"Liczba schematów: {args.num_schematics}")
    print(f"Komponenty: {args.min_components}-{args.max_components}")
    print(f"Rozmiar płótna: {args.width}x{args.height}px")
    print(f"Katalog wyjściowy: {output_dir}")
    print(f"Katalog metadanych: {metadata_dir}")
    print(f"Seed początkowy: {args.start_seed}")
    if args.dry_run:
        print("⚠️  DRY RUN MODE - polecenia nie będą wykonane")
    print("=" * 60)
    print()

    # Generate random parameters for each schematic
    random.seed(args.start_seed)
    schematic_params = []

    for i in range(args.num_schematics):
        num_components = random.randint(args.min_components, args.max_components)
        seed = args.start_seed + i

        schematic_params.append({"index": i + 1, "num_components": num_components, "seed": seed})

    # Generate schematics
    successful = 0
    failed = 0
    schematics_info = []

    for params in schematic_params:
        idx = params["index"]
        output_path = output_dir / f"schematic_{idx:03d}.png"
        metadata_path = metadata_dir / f"schematic_{idx:03d}.json"

        print(
            f"[{idx}/{args.num_schematics}] Generowanie: {params['num_components']} komponentów, seed={params['seed']}"
        )

        success = generate_schematic(
            index=idx,
            num_components=params["num_components"],
            seed=params["seed"],
            output_path=output_path,
            metadata_path=metadata_path,
            width=args.width,
            height=args.height,
            dry_run=args.dry_run,
        )

        if success:
            successful += 1
            schematics_info.append(
                {
                    "id": f"schematic_{idx:03d}",
                    "num_components": params["num_components"],
                    "seed": params["seed"],
                    "image_path": str(output_path),
                    "metadata_path": str(metadata_path),
                }
            )
        else:
            failed += 1

    # Print summary
    print()
    print("=" * 60)
    print("[OK] Ukończono generowanie")
    print(f"  Sukces: {successful}/{args.num_schematics}")
    if failed > 0:
        print(f"  Błędy: {failed}/{args.num_schematics}")
    print("=" * 60)

    # Create metadata summary
    if not args.dry_run and schematics_info:
        create_metadata_summary(output_dir, metadata_dir, schematics_info, args)

        print("\n📁 Katalogi:")
        print(f"  Obrazy: {output_dir}")
        print(f"  Metadane: {metadata_dir}")
        print("\n🔄 Następny krok:")
        cmd_line = f"python scripts/synthetic/emit_annotations.py --input-dir {metadata_dir}"
        cmd_line += " --output data/synthetic/coco_annotations.json"
        print(f"  {cmd_line}")


if __name__ == "__main__":
    main()
