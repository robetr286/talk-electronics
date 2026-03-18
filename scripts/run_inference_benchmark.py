#!/usr/bin/env python3
"""Minimal benchmarking harness for registered symbol detectors."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable, List

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from talk_electronic.services.symbol_detection import (  # noqa: E402
    YoloV8SegDetector,
    available_detectors,
    create_detector,
    register_detector,
)
from talk_electronic.services.symbol_detection.noop import NoOpSymbolDetector  # noqa: E402
from talk_electronic.services.symbol_detection.simple import SimpleThresholdDetector  # noqa: E402
from talk_electronic.services.symbol_detection.template_matching import TemplateMatchingDetector  # noqa: E402

# Register built-in detectors for convenience when running as a script.
try:
    register_detector(NoOpSymbolDetector.name, NoOpSymbolDetector)
except ValueError:
    pass

for detector_cls in (SimpleThresholdDetector, TemplateMatchingDetector, YoloV8SegDetector):
    try:
        register_detector(detector_cls.name, detector_cls)
    except ValueError:
        pass


def _iter_images(image_dir: Path) -> Iterable[np.ndarray]:
    image_paths: List[Path] = sorted(
        path for path in image_dir.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
    for path in image_paths:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            continue
        yield image


def benchmark(detector_name: str, samples: Iterable[np.ndarray], warmup: int, runs: int) -> float:
    detector = create_detector(detector_name)

    images = list(samples)
    if not images:
        images = [np.zeros((512, 512, 3), dtype=np.uint8)]

    for _ in range(warmup):
        for image in images:
            detector.detect(image, return_summary=False)

    start = time.perf_counter()
    for _ in range(runs):
        for image in images:
            detector.detect(image, return_summary=False)
    elapsed = time.perf_counter() - start
    total_inferences = runs * len(images)
    return (elapsed / total_inferences) * 1000.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a simple inference benchmark for symbol detectors")
    parser.add_argument("detector", type=str, help="Registered detector name")
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=Path("data/sample_benchmark"),
        help="Directory with test images (defaults to data/sample_benchmark)",
    )
    parser.add_argument("--warmup", type=int, default=1, help="Warmup iterations")
    parser.add_argument("--runs", type=int, default=3, help="Benchmark iterations")
    parser.add_argument("--list", action="store_true", help="List available detectors and exit")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.list:
        print("Available detectors:")
        for name in available_detectors():
            print(f" - {name}")
        return 0

    if args.image_dir.exists():
        images = list(_iter_images(args.image_dir))
        if not images:
            print(f"No PNG/JPEG files found in {args.image_dir}, using fallback blank image.")
    else:
        print(f"Image directory not found: {args.image_dir}, using fallback blank image.")
        images = []

    latency_ms = benchmark(args.detector, images, warmup=max(0, args.warmup), runs=max(1, args.runs))
    print(f"Detector {args.detector} average latency: {latency_ms:.2f} ms")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
