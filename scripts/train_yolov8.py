"""Utility script to kick off YOLOv8 training once annotated data is available."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def resolve_paths(data_config: str, project_dir: str) -> tuple[Path, Path]:
    data_path = Path(data_config).expanduser().resolve()
    project_path = Path(project_dir).expanduser().resolve()
    return data_path, project_path


def check_environment() -> None:
    try:
        import ultralytics  # noqa: F401  # type: ignore
    except ImportError as exc:  # pragma: no cover - informative exit
        raise SystemExit(
            "Ultralytics package is missing. Install with `pip install ultralytics` before training."
        ) from exc


def build_command(model: str, data: Path, project: Path, epochs: int, batch: int) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "ultralytics",
        "cfg=train",
        f"model={model}",
        f"data={data}",
        f"project={project}",
        f"epochs={epochs}",
        f"batch={batch}",
    ]
    return command


def main() -> None:
    parser = argparse.ArgumentParser(description="Train YOLOv8 on Talk electronics symbols")
    parser.add_argument("--model", default="yolov8n-seg.pt", help="Base model checkpoint to finetune")
    parser.add_argument("--data", default="configs/yolov8_symbols.yaml", help="Path to dataset config")
    parser.add_argument("--project", default="runs/yolo", help="Output directory for YOLO experiments")
    parser.add_argument("--epochs", type=int, default=100, help="Number of training epochs")
    parser.add_argument("--batch", type=int, default=16, help="Batch size for training")
    args = parser.parse_args()

    data_path, project_path = resolve_paths(args.data, args.project)

    if not data_path.exists():
        raise SystemExit(f"Dataset config not found at {data_path}")

    project_path.mkdir(parents=True, exist_ok=True)

    check_environment()
    command = build_command(args.model, data_path, project_path, args.epochs, args.batch)

    print("Launching YOLOv8 training:")
    print(" ".join(command))

    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
