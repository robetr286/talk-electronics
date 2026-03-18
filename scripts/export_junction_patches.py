"""Narzędzie CLI do zbierania patchy junction dla treningu klasyfikatora."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from talk_electronic.services.line_detection import (  # noqa: E402
    JunctionPatchExportConfig,
    LineDetectionConfig,
    detect_lines,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Uruchamia detekcję linii na zbiorze obrazów i zapisuje patchy junction.",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        default=["data/sample_benchmark"],
        help="Pliki lub katalogi z obrazami (PNG/JPG/BMP).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/sample_benchmark/junction_patches"),
        help="Katalog, w którym zostaną zapisane patchy oraz manifest.",
    )
    parser.add_argument(
        "--patch-size",
        type=int,
        default=32,
        help="Rozmiar wycinka (piksele).",
    )
    parser.add_argument(
        "--limit-per-image",
        type=int,
        default=128,
        help="Maksymalna liczba patchy zapisywana z jednego obrazu (None = bez limitu).",
    )
    parser.add_argument(
        "--min-node-degree",
        type=int,
        default=3,
        help="Minimalna liczba połączeń węzła kwalifikującego się do eksportu (domyślnie 3).",
    )
    parser.add_argument(
        "--binary",
        action="store_true",
        help="Traktuj wejściowe obrazy jako już zbinaryzowane.",
    )
    parser.add_argument(
        "--processing-scale",
        type=float,
        default=1.0,
        help="Skalowanie obrazu przed detekcją (np. 0.5 dla szybszego przetwarzania).",
    )
    parser.add_argument(
        "--debug-dir",
        type=Path,
        default=None,
        help="Opcjonalny katalog na artefakty debugowe (np. skeleton).",
    )
    parser.add_argument(
        "--enable-color-enhancement",
        action="store_true",
        help="Podbija cienkie linie w przestrzeni kolorów przed skeletonizacją.",
    )
    parser.add_argument(
        "--color-preset",
        type=str,
        default=None,
        help="Nazwa presetu z configs/line_detection.defaults.json (np. combo, combo_tight).",
    )
    parser.add_argument(
        "--color-strength",
        type=float,
        default=None,
        help="Siła przyciemniania linii (0-1).",
    )
    parser.add_argument(
        "--color-s-threshold",
        type=int,
        default=None,
        help="Próg nasycenia HSV dla maski linii (0-255).",
    )
    parser.add_argument(
        "--color-v-threshold",
        type=int,
        default=None,
        help="Próg jasności HSV dla maski linii (0-255).",
    )
    parser.add_argument(
        "--dotted-bridge-kernel",
        nargs=2,
        type=int,
        metavar=("W", "H"),
        default=None,
        help="Rozmiar jądra (px) domykającego kropkowane linie (np. 3 3).",
    )
    parser.add_argument(
        "--dotted-bridge-iterations",
        type=int,
        default=None,
        help="Liczba iteracji domykania kropek (0 = wyłączone).",
    )
    parser.add_argument(
        "--dotted-bridge-endpoint-max-distance",
        type=int,
        default=None,
        help="Maksymalna odległość (px) do łączenia endpointów w obrębie kropki.",
    )
    parser.add_argument(
        "--dotted-bridge-component-max-area",
        type=int,
        default=None,
        help="Maksymalna powierzchnia (px) komponentu, który traktujemy jako kropkę.",
    )
    parser.add_argument(
        "--enable-graph-repair",
        action="store_true",
        help="Włącz graph-based repair łączenia endpointów przez analizę topologiczną (dotted-line-graph-repair).",
    )
    parser.add_argument(
        "--disable-graph-repair",
        action="store_true",
        help="Wyłącz graph-based repair.",
    )
    parser.add_argument(
        "--graph-repair-angle-threshold",
        type=float,
        default=None,
        help="Kąt tolerancji (stopnie) przy parowaniu endpointów w naprawie grafowej (np. 30.0).",
    )
    parser.add_argument(
        "--graph-repair-overlap",
        type=float,
        default=None,
        help="Minimalne ułamkowe pokrycie trasowania linii przez wykryte kropki (0-1).",
    )
    parser.add_argument(
        "--graph-repair-max-joins",
        type=int,
        default=None,
        help="Maksymalna liczba połączeń dodanych w jednym obrazie przez naprawę grafową.",
    )
    parser.add_argument(
        "--enable-roi-close",
        action="store_true",
        help="Włącz lokalne ROI-closing dla kropkowanych komponentów.",
    )
    parser.add_argument(
        "--disable-roi-close",
        action="store_true",
        help="Wyłącz lokalne ROI-closing.",
    )
    parser.add_argument(
        "--enable-global-endpoint-pairing",
        action="store_true",
        help="Włącz globalne łączenie endpointów dla kropkowanych regionów.",
    )
    parser.add_argument(
        "--disable-global-endpoint-pairing",
        action="store_true",
        help="Wyłącz globalne łączenie endpointów.",
    )
    return parser.parse_args()


def gather_images(sources: List[str]) -> List[Path]:
    supported = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
    files: List[Path] = []
    for raw in sources:
        path = Path(raw)
        if path.is_dir():
            for item in path.rglob("*"):
                if item.suffix.lower() in supported:
                    files.append(item)
        elif path.is_file() and path.suffix.lower() in supported:
            files.append(path)
    return sorted(files)


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Nie udało się wczytać obrazu: {path}")
    return image


def export_for_image(image_path: Path, args: argparse.Namespace) -> dict:
    image = load_image(image_path)
    junction_export = JunctionPatchExportConfig(
        enabled=True,
        output_dir=args.output_dir,
        patch_size=args.patch_size,
        default_label="unknown",
        limit_per_image=None if args.limit_per_image <= 0 else args.limit_per_image,
        min_node_degree=max(1, args.min_node_degree),
    )
    config = LineDetectionConfig(
        junction_patch_export=junction_export,
        processing_scale=args.processing_scale,
        debug_dir=args.debug_dir,
        debug_prefix=f"junction-{image_path.stem}",
    )

    if args.color_preset:
        presets = load_color_presets()
        preset = presets.get(args.color_preset)
        if preset is None:
            available = ", ".join(sorted(presets)) or "brak presetów w configs/line_detection.defaults.json"
            raise SystemExit(f"Nieznany preset '{args.color_preset}'. Dostępne: {available}")
        apply_line_config_overrides(config, preset)
        config.color_preset = args.color_preset

    if args.enable_color_enhancement:
        config.enable_color_enhancement = True
    if args.color_strength is not None:
        config.color_enhancement_strength = args.color_strength
    if args.color_s_threshold is not None:
        config.color_enhancement_saturation_threshold = args.color_s_threshold
    if args.color_v_threshold is not None:
        config.color_enhancement_value_threshold = args.color_v_threshold
    if args.dotted_bridge_kernel:
        kernel = tuple(max(1, int(value)) for value in args.dotted_bridge_kernel)
        config.dotted_line_bridge_kernel_size = kernel  # type: ignore[assignment]
    if args.dotted_bridge_iterations is not None:
        config.dotted_line_bridge_iterations = max(0, int(args.dotted_bridge_iterations))
    if args.dotted_bridge_endpoint_max_distance is not None:
        config.dotted_line_bridge_endpoint_max_distance = max(0, int(args.dotted_bridge_endpoint_max_distance))
    if args.dotted_bridge_component_max_area is not None:
        config.dotted_line_bridge_component_max_area = max(0, int(args.dotted_bridge_component_max_area))
    if args.enable_roi_close:
        config.dotted_line_bridge_enable_roi_close = True
    if args.disable_roi_close:
        config.dotted_line_bridge_enable_roi_close = False
    if args.enable_global_endpoint_pairing:
        config.dotted_line_bridge_enable_global_endpoint_pairing = True
    if args.disable_global_endpoint_pairing:
        config.dotted_line_bridge_enable_global_endpoint_pairing = False
    # graph-based repair flags
    if args.enable_graph_repair:
        config.dotted_line_graph_repair_enable = True
    if args.disable_graph_repair:
        config.dotted_line_graph_repair_enable = False
    if args.graph_repair_angle_threshold is not None:
        config.dotted_line_graph_repair_angle_threshold = float(max(0.0, args.graph_repair_angle_threshold))
    if args.graph_repair_overlap is not None:
        config.dotted_line_graph_repair_overlap_fraction = float(np.clip(args.graph_repair_overlap, 0.0, 1.0))
    if args.graph_repair_max_joins is not None:
        config.dotted_line_graph_repair_max_joins_per_image = max(0, int(args.graph_repair_max_joins))
    result = detect_lines(image, binary=args.binary, config=config)
    export_meta = result.metadata.get("junction_patch_export", {"saved": 0})
    return {
        "image": str(image_path),
        "saved": export_meta.get("saved", 0),
        "directory": export_meta.get("directory"),
    }


_COLOR_PRESET_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def load_color_presets() -> Dict[str, Dict[str, Any]]:
    global _COLOR_PRESET_CACHE
    if _COLOR_PRESET_CACHE is not None:
        return _COLOR_PRESET_CACHE

    config_path = PROJECT_ROOT / "configs" / "line_detection.defaults.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _COLOR_PRESET_CACHE = {}
        return _COLOR_PRESET_CACHE
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostyka pliku
        raise SystemExit(f"Nie udało się sparsować {config_path}: {exc}")

    presets = data.get("color_presets") if isinstance(data, dict) else None
    if isinstance(presets, dict):
        _COLOR_PRESET_CACHE = {key: value for key, value in presets.items() if isinstance(value, dict)}
    else:
        _COLOR_PRESET_CACHE = {}
    return _COLOR_PRESET_CACHE


def apply_line_config_overrides(config: LineDetectionConfig, overrides: Dict[str, Any]) -> None:
    if not isinstance(overrides, dict):
        return
    for field_info in dataclass_fields(LineDetectionConfig):
        name = field_info.name
        if name not in overrides:
            continue
        value = overrides[name]
        current = getattr(config, name)
        if isinstance(current, tuple) and isinstance(value, list):
            value = tuple(value)
        if isinstance(current, Path) and isinstance(value, str):
            value = Path(value)
        setattr(config, name, value)


def main() -> None:
    args = parse_args()
    files = gather_images(args.inputs)
    if not files:
        raise SystemExit("Brak obrazów do przetworzenia (podaj katalog lub listę plików).")

    summaries: List[dict] = []
    total = 0
    for path in files:
        summary = export_for_image(path, args)
        total += int(summary.get("saved", 0))
        summaries.append(summary)
        print(f"[junction-export] {path} -> saved={summary['saved']} dest={summary.get('directory')}")

    report_path = args.output_dir / "export_summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"total_saved": total, "entries": summaries}, indent=2), encoding="utf-8")
    print(f"Zapisano łącznie {total} patchy. Raport: {report_path}")


if __name__ == "__main__":
    main()
