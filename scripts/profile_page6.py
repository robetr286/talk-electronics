from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

import cv2


def _ensure_repo_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


_ensure_repo_on_path()

from talk_electronic.services.line_detection import LineDetectionConfig, detect_lines  # noqa: E402


def profile_scales(image_path: Path, scales: Sequence[float]) -> None:
    image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise RuntimeError(f"Nie wczytałem obrazu: {image_path}")

    print(f"Wejściowy obraz: shape={image.shape}, dtype={image.dtype}")

    for scale in scales:
        config = LineDetectionConfig(processing_scale=scale)
        result = detect_lines(image, binary=False, config=config)
        metadata = result.metadata
        timings = metadata.get("timings_ms", {})
        print(f"\n=== processing_scale={scale:.2f} ===")
        print(f"working_shape: {metadata.get('working_shape')}")
        print(f"elapsed_ms: {metadata.get('elapsed_ms', 0.0):.2f}")
        print(f"skeleton_ms: {timings.get('skeleton_ms', 0.0):.2f}")
        print(f"graph_from_skeleton_ms: {timings.get('graph_from_skeleton_ms', 0.0):.2f}")
        print(f"assemble_candidates_ms: {timings.get('assemble_candidates_ms', 0.0):.2f}")
        print(f"segments: {metadata.get('merged_segments')}")
        print(f"nodes: {metadata.get('nodes')}")
        print(f"skeleton_pixels: {metadata.get('skeleton_pixels')}")


if __name__ == "__main__":
    target = Path("uploads/06134e04bf894b50941da0ef8b26d7f5_page_6.png")
    profile_scales(target, scales=[0.75, 0.6, 0.5])
