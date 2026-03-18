from __future__ import annotations

import csv
import math
import time
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass, field
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from talk_electronic.services.skeleton import SkeletonConfig, SkeletonEngine

LinePoint = Tuple[int, int]

NODE_MERGE_TOLERANCE = 4.0
MIN_EDGE_LENGTH = 8.0
NEIGHBOR_OFFSETS: Tuple[Tuple[int, int], ...] = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)

JUNCTION_LABELS: Tuple[str, ...] = ("dot_present", "no_dot", "unknown")


@dataclass(slots=True)
class JunctionPatchExportConfig:
    """Ustawienia eksportu wycinków skrzyżowań linii."""

    enabled: bool = False
    output_dir: Path = Path("data/sample_benchmark/junction_patches")
    patch_size: int = 32
    min_node_degree: int = 3
    default_label: str = "unknown"
    limit_per_image: Optional[int] = None
    manifest_name: str = "manifest.csv"


@dataclass(slots=True)
class JunctionDetectorConfig:
    """Ustawienia inference dla JunctionDetector."""

    enabled: bool = False
    model_path: Path = Path("models/junction_classifier.onnx")
    provider: str = "CPUExecutionProvider"
    threshold_dot_present: float = 0.55
    threshold_no_dot: float = 0.55
    min_node_degree: int = 3
    patch_size: int = 32
    cache_size: int = 256


@dataclass(slots=True)
class LineDetectionConfig:
    """Konfiguracja kroków wykrywania linii."""

    gaussian_kernel_size: Tuple[int, int] = (5, 5)
    gaussian_sigma: float = 0.0
    use_adaptive_threshold: bool = False
    adaptive_block_size: int = 21
    adaptive_c: int = 10
    binary_threshold: int = 140
    morph_kernel_size: Tuple[int, int] = (3, 3)
    morph_iterations: int = 1
    enable_skeletonize: bool = True
    hough_rho: float = 1.0
    hough_theta: float = math.pi / 180.0
    hough_threshold: int = 50
    min_line_length: int = 25
    max_line_gap: int = 10
    debug_dir: Optional[Path] = None
    debug_prefix: str = "line-det"
    skeleton_config: SkeletonConfig = field(default_factory=SkeletonConfig)
    node_merge_tolerance: float = NODE_MERGE_TOLERANCE
    min_edge_length: float = MIN_EDGE_LENGTH
    processing_scale: float = 1.0
    junction_patch_export: Optional[JunctionPatchExportConfig] = None
    junction_detector: Optional[JunctionDetectorConfig] = None
    enable_color_enhancement: bool = False
    color_enhancement_strength: float = 0.6
    color_enhancement_saturation_threshold: int = 72
    color_enhancement_value_threshold: int = 235
    color_preset: Optional[str] = None
    dotted_line_bridge_kernel_size: Tuple[int, int] = (3, 3)
    dotted_line_bridge_iterations: int = 0
    dotted_line_bridge_saturation_threshold: int = 48
    dotted_line_bridge_value_threshold: int = 210
    # endpoint-based bridging (to specifically connect small dot gaps)
    dotted_line_bridge_endpoint_max_distance: int = 36
    dotted_line_bridge_component_min_area: int = 3
    dotted_line_bridge_component_max_area: int = 500
    dotted_line_bridge_enable_hough: bool = False
    dotted_line_bridge_enable_global_endpoint_pairing: bool = True
    dotted_line_bridge_enable_roi_close: bool = True
    # Graph-based repair options (option A)
    dotted_line_graph_repair_enable: bool = True
    # Conservative defaults: prefer few, safe joins to avoid false positives
    # tightened overlap fraction to require more coverage by dotted candidates
    dotted_line_graph_repair_angle_threshold: float = 12.0
    dotted_line_graph_repair_overlap_fraction: float = 0.5
    dotted_line_graph_repair_max_joins_per_image: int = 10
    # maximum number of graph nodes allowed for graph-repair; if exceeded,
    # the algorithm will skip heavy repairs to avoid timeouts
    dotted_line_graph_repair_max_nodes: int = 500
    # Text / label masking — conservative heurystyka wykrywająca skupiska drobnych
    # komponentów (np. linie tekstu / etykiety) i wyłączająca naprawy przebiegające
    # przez takie obszary.
    enable_text_masking: bool = True
    text_mask_min_component_area: int = 1
    text_mask_max_component_area: int = 500
    text_mask_components_threshold: int = 2
    text_mask_min_width_height_ratio: float = 1.8
    text_mask_expand_px: int = 4


@dataclass(slots=True)
class LineSegment:
    """Pojedynczy odcinek linii wykryty na obrazie."""

    id: str
    start: LinePoint
    end: LinePoint
    length: float
    angle_deg: float
    confidence: float = 0.0
    confidence_label: str = "unknown"

    def to_tuple(self) -> Tuple[int, int, int, int]:
        return (*self.start, *self.end)


@dataclass(slots=True)
class LineNode:
    """Węzeł (punkt przecięcia) grafu linii."""

    id: str
    position: LinePoint
    attached_segments: List[str] = field(default_factory=list)
    classification: str = "unspecified"
    junction_state: str = "unspecified"
    junction_label: str = "unknown"
    junction_confidence: float = 0.0


class JunctionDetector:
    """Lekki wrapper inferencyjny nad modelem junction classifier."""

    def __init__(self, config: JunctionDetectorConfig):
        self.config = config
        self._session = None
        self._input_name: Optional[str] = None
        self._output_name: Optional[str] = None
        self._available = False
        self._load_error: Optional[str] = None
        self._cache: OrderedDict[Tuple[int, int], Tuple[str, float]] = OrderedDict()
        model_path = Path(config.model_path) if config.model_path else None
        if not model_path or not model_path.exists():
            self._load_error = f"Brak pliku modelu: {model_path}"
            return
        try:
            import onnxruntime as ort  # type: ignore
        except ImportError as exc:  # pragma: no cover - zależność opcjonalna
            self._load_error = f"onnxruntime niedostępny: {exc}"
            return
        try:
            providers = [config.provider] if config.provider else None
            self._session = ort.InferenceSession(str(model_path), providers=providers)
            inputs = self._session.get_inputs()
            outputs = self._session.get_outputs()
            if not inputs or not outputs:
                raise RuntimeError("Nieprawidłowy model ONNX (brak I/O)")
            self._input_name = inputs[0].name
            self._output_name = outputs[0].name
            self._available = True
        except Exception as exc:  # pragma: no cover - ścieżka błędna
            self._load_error = f"Nie udało się zainicjalizować JunctionDetector: {exc}"

    def annotate_nodes(self, *, image: np.ndarray, nodes: Sequence[LineNode]) -> Dict[str, Any]:
        extractor = _build_junction_patch_extractor(image, self.config.patch_size)
        min_degree = max(3, int(self.config.min_node_degree))
        processed = 0
        states = Counter()
        for node in nodes:
            if len(node.attached_segments) < min_degree:
                node.junction_state = "not_applicable"
                continue
            label, confidence = self._classify_node(node, extractor)
            state = self._label_to_state(label, confidence)
            node.junction_label = label
            node.junction_confidence = confidence
            node.junction_state = state
            processed += 1
            states[state] += 1
        summary: Dict[str, Any] = {
            "processed": processed,
            "states": dict(states),
            "model_path": str(self.config.model_path),
            "available": self._available,
        }
        if self._load_error:
            summary["error"] = self._load_error
        return summary

    def _classify_node(
        self,
        node: LineNode,
        extractor: Callable[[LinePoint], np.ndarray],
    ) -> Tuple[str, float]:
        key = (int(node.position[0]), int(node.position[1]))
        cache_enabled = self.config.cache_size > 0
        if cache_enabled and key in self._cache:
            return self._cache[key]
        patch = extractor(node.position)
        label, confidence = self._predict(patch)
        if cache_enabled:
            self._cache[key] = (label, confidence)
            while len(self._cache) > self.config.cache_size:
                self._cache.popitem(last=False)
        return label, confidence

    def _predict(self, patch: np.ndarray) -> Tuple[str, float]:
        normalized = patch.astype(np.float32) / 255.0
        if self._available and self._session and self._input_name and self._output_name:
            input_tensor = normalized.reshape(1, 1, normalized.shape[0], normalized.shape[1])
            outputs = self._session.run([self._output_name], {self._input_name: input_tensor})
            logits = outputs[0][0]
            probabilities = _softmax(logits)
            index = int(np.argmax(probabilities))
            if 0 <= index < len(JUNCTION_LABELS):
                label = JUNCTION_LABELS[index]
            else:
                label = "unknown"
            confidence = float(probabilities[index])
            return label, confidence
        return self._heuristic_prediction(normalized)

    def _heuristic_prediction(self, normalized_patch: np.ndarray) -> Tuple[str, float]:
        h, w = normalized_patch.shape
        h_mid = max(0, h // 2 - 1)
        w_mid = max(0, w // 2 - 1)
        center = normalized_patch[h_mid : min(h, h_mid + 2), w_mid : min(w, w_mid + 2)]
        center_mean = float(center.mean()) if center.size else float(normalized_patch.mean())
        global_mean = float(normalized_patch.mean())
        contrast = center_mean - global_mean
        if contrast >= 0.08:
            return "dot_present", min(0.95, 0.5 + contrast)
        if global_mean <= 0.2:
            return "no_dot", 0.6
        return "unknown", 0.35

    def _label_to_state(self, label: str, confidence: float) -> str:
        if label == "dot_present" and confidence >= self.config.threshold_dot_present:
            return "auto_connected"
        if label == "no_dot" and confidence >= self.config.threshold_no_dot:
            return "blocked"
        return "needs_review"


@dataclass(slots=True)
class SegmentCandidate:
    start: Tuple[float, float]
    end: Tuple[float, float]
    priority: int = 0


@dataclass(slots=True)
class LineDetectionResult:
    """Struktura danych zwracana po wykryciu linii."""

    lines: List[LineSegment] = field(default_factory=list)
    nodes: List[LineNode] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    debug_artifacts: List[Path] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializuje wynik do słownika gotowego do JSON."""

        return {
            "lines": [
                {
                    "id": line.id,
                    "start": line.start,
                    "end": line.end,
                    "length": line.length,
                    "angle_deg": line.angle_deg,
                    "confidence": line.confidence,
                    "confidence_label": line.confidence_label,
                }
                for line in self.lines
            ],
            "nodes": [
                {
                    "id": node.id,
                    "position": node.position,
                    "attached_segments": node.attached_segments,
                    "classification": node.classification,
                    "junction_state": node.junction_state,
                    "junction_label": node.junction_label,
                    "junction_confidence": node.junction_confidence,
                }
                for node in self.nodes
            ],
            "metadata": self.metadata,
            "debug_artifacts": [str(path) for path in self.debug_artifacts],
        }


def detect_lines(
    image: np.ndarray,
    *,
    binary: bool = False,
    config: Optional[LineDetectionConfig] = None,
) -> LineDetectionResult:
    """Wykrywa linie w podanym obrazie, budując graf z jednopikselowego szkieletu."""

    if image is None:
        raise ValueError("Parameter 'image' must contain numpy array")

    cfg = config or LineDetectionConfig()

    # basic timing/metadata holders
    start_ts = time.perf_counter()
    metadata: Dict[str, Any] = {"elapsed_ms": 0.0}
    stage_timings: Dict[str, float] = {}

    # operational scale and working copies (we resize for faster inference
    # when requested and keep a single 'effective_cfg' reference used by
    # downstream helpers)
    processing_scale = float(getattr(cfg, "processing_scale", 1.0))
    effective_cfg: LineDetectionConfig = cfg
    if not math.isclose(processing_scale, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        interp = cv2.INTER_AREA if processing_scale < 1.0 else cv2.INTER_LINEAR
        effective_image = cv2.resize(
            image, dsize=(0, 0), fx=processing_scale, fy=processing_scale, interpolation=interp
        )
    else:
        effective_image = image.copy()

    prepared = _prepare_image(effective_image, binary=binary, config=effective_cfg)

    debug_artifacts: List[Path] = []

    if effective_cfg.debug_dir:
        debug_artifacts.extend(
            _save_debug_images(
                effective_cfg.debug_dir,
                effective_cfg.debug_prefix,
                {
                    "prepared": prepared,
                },
            )
        )

    skeleton_engine = SkeletonEngine(effective_cfg.skeleton_config)
    stage_start = time.perf_counter()
    skeleton_result = skeleton_engine.run(prepared)
    stage_timings["skeleton_ms"] = (time.perf_counter() - stage_start) * 1000.0
    skeleton_mask = (skeleton_result.skeleton > 0).astype(np.uint8)
    binary_mask = (skeleton_result.binary > 0).astype(np.uint8)
    contours, _ = cv2.findContours(binary_mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    largest_contour_area = max((cv2.contourArea(contour) for contour in contours), default=0.0)

    if effective_cfg.debug_dir:
        debug_artifacts.extend(
            _save_debug_images(
                effective_cfg.debug_dir,
                effective_cfg.debug_prefix,
                {
                    "binary": skeleton_result.binary,
                    "skeleton": skeleton_result.skeleton,
                },
            )
        )

    # Graph-based repair (option A): operate on the skeleton topology and
    # attempt to connect endpoint pairs conservatively when a dotted-region
    # candidate mask indicates a dotty gap. This approach is safer than
    # aggressive morphological fills because it verifies angle/distance and
    # overlap constraints at the graph level.
    if getattr(effective_cfg, "dotted_line_graph_repair_enable", False):
        try:
            candidates = _detect_dotted_candidates(effective_image, effective_cfg)
            general_mask = candidates[0] if candidates is not None else None
            if general_mask is not None:
                # Apply optional text/label mask to prevent repairs that cross
                # text/annotation areas — safety gate C
                if getattr(effective_cfg, "enable_text_masking", False):
                    try:
                        text_mask = _detect_text_mask(effective_image, effective_cfg)
                        if text_mask is not None and text_mask.size != 0 and cv2.countNonZero(text_mask) > 0:
                            # invert text_mask and intersect with candidate mask
                            general_mask = cv2.bitwise_and(general_mask, cv2.bitwise_not(text_mask))
                            if effective_cfg.debug_dir:
                                debug_artifacts.extend(
                                    _save_debug_images(
                                        effective_cfg.debug_dir,
                                        effective_cfg.debug_prefix,
                                        {"text_mask": (text_mask * 255).astype(np.uint8)},
                                    )
                                )
                    except Exception:
                        # conservative: on text-mask errors, keep original general_mask
                        pass

                skeleton_mask = _graph_repair_skeleton(skeleton_mask, binary_mask, general_mask, effective_cfg)
                if effective_cfg.debug_dir:
                    repaired = (skeleton_mask * 255).astype(np.uint8)
                    debug_artifacts.extend(
                        _save_debug_images(
                            effective_cfg.debug_dir,
                            effective_cfg.debug_prefix,
                            {"skeleton_repaired": repaired},
                        )
                    )
        except Exception:
            pass

    stage_start = time.perf_counter()
    skeleton_segments, _ = _build_graph_from_skeleton(
        skeleton_mask,
        min_edge_length=effective_cfg.min_edge_length,
        node_merge_tolerance=effective_cfg.node_merge_tolerance,
    )
    stage_timings["graph_from_skeleton_ms"] = (time.perf_counter() - stage_start) * 1000.0

    skeleton_candidates: List[SegmentCandidate] = [
        SegmentCandidate(start=segment.start, end=segment.end, priority=0) for segment in skeleton_segments
    ]

    contour_candidates: List[SegmentCandidate] = []
    contour_points: List[Tuple[float, float]] = []
    binary_pixels = int(binary_mask.sum())
    skeleton_pixels = int(skeleton_mask.sum())
    need_contours = (
        effective_cfg.skeleton_config.extract_contours
        or not skeleton_segments
        or (
            skeleton_pixels > 0
            and binary_pixels > skeleton_pixels * 2
            and largest_contour_area > 0.0
            and largest_contour_area / max(1.0, float(binary_pixels)) >= 2.0
        )
    )
    if need_contours:
        contour_candidates = _segment_candidates_from_contours(
            binary_mask,
            min_edge_length=effective_cfg.min_edge_length,
            contours=contours,
        )

    if contour_candidates:
        contour_points = [candidate.start for candidate in contour_candidates]
        contour_points.extend(candidate.end for candidate in contour_candidates)
        contour_merge_tolerance = _contour_merge_tolerance(
            effective_cfg.node_merge_tolerance,
            effective_cfg.min_edge_length,
        )
        skeleton_candidates = [
            candidate
            for candidate in skeleton_candidates
            if not _candidate_covered_by_points(
                candidate,
                contour_points,
                contour_merge_tolerance,
            )
        ]

    candidates: List[SegmentCandidate] = skeleton_candidates + contour_candidates

    stage_start = time.perf_counter()
    segments, nodes = _assemble_segments_from_candidates(
        candidates,
        node_merge_tolerance=effective_cfg.node_merge_tolerance,
        min_edge_length=effective_cfg.min_edge_length,
    )
    stage_timings["assemble_candidates_ms"] = (time.perf_counter() - stage_start) * 1000.0

    if contour_points:
        stage_start = time.perf_counter()
        segments, nodes = _prune_short_leaf_segments(
            segments,
            nodes,
            contour_points=contour_points,
            contour_candidates=contour_candidates,
            node_merge_tolerance=effective_cfg.node_merge_tolerance,
            min_edge_length=effective_cfg.min_edge_length,
        )
        stage_timings["prune_short_leaf_ms"] = (time.perf_counter() - stage_start) * 1000.0

    stage_start = time.perf_counter()
    segments, nodes = _prune_textual_spurs(
        segments,
        nodes,
        binary_mask=binary_mask,
        skeleton_mask=skeleton_mask,
        contour_candidates=contour_candidates,
        node_merge_tolerance=effective_cfg.node_merge_tolerance,
        min_edge_length=effective_cfg.min_edge_length,
    )
    stage_timings["prune_textual_spurs_ms"] = (time.perf_counter() - stage_start) * 1000.0

    stage_start = time.perf_counter()
    segments, nodes, endpoint_debug = _filter_textual_endpoints(
        segments,
        nodes,
        binary_mask=binary_mask,
        skeleton_mask=skeleton_mask,
        contour_candidates=contour_candidates,
        node_merge_tolerance=effective_cfg.node_merge_tolerance,
        min_edge_length=effective_cfg.min_edge_length,
    )
    stage_timings["filter_textual_endpoints_ms"] = (time.perf_counter() - stage_start) * 1000.0
    metadata["endpoint_filter"] = endpoint_debug

    stage_start = time.perf_counter()
    segments, nodes = _merge_straight_chains(
        segments,
        nodes,
        contour_candidates=contour_candidates,
        node_merge_tolerance=effective_cfg.node_merge_tolerance,
        min_edge_length=effective_cfg.min_edge_length,
    )
    stage_timings["merge_straight_ms"] = (time.perf_counter() - stage_start) * 1000.0

    if not math.isclose(processing_scale, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        inverse_scale = 1.0 / processing_scale
        rescaled_segments: List[LineSegment] = []
        for segment in segments:
            start = _rescale_point(segment.start, inverse_scale)
            end = _rescale_point(segment.end, inverse_scale)
            rescaled_segments.append(
                LineSegment(
                    id=segment.id,
                    start=start,
                    end=end,
                    length=segment.length * inverse_scale,
                    angle_deg=segment.angle_deg,
                )
            )
        segments = rescaled_segments

        rescaled_nodes: List[LineNode] = []
        for node in nodes:
            rescaled_nodes.append(
                LineNode(
                    id=node.id,
                    position=_rescale_point(node.position, inverse_scale),
                    attached_segments=list(node.attached_segments),
                )
            )
        nodes = rescaled_nodes

    node_stats = _classify_nodes(nodes)

    confidence_summary = _score_segments(
        segments,
        nodes,
        min_edge_length=cfg.min_edge_length,
    )
    for segment in segments:
        info = confidence_summary["scores"].get(segment.id)
        if info is None:
            continue
        segment.confidence = float(info.get("score", 0.0))
        segment.confidence_label = str(info.get("label", "unknown"))

    elapsed_ms = (time.perf_counter() - start_ts) * 1000.0
    metadata["elapsed_ms"] += elapsed_ms
    metadata["skeleton_pixels"] = skeleton_pixels
    metadata["binary_pixels"] = binary_pixels
    metadata["timings_ms"] = stage_timings
    metadata["merged_segments"] = len(segments)
    metadata["nodes"] = len(nodes)
    metadata["node_classification"] = node_stats
    metadata["skeleton_metadata"] = skeleton_result.metadata
    metadata["confidence"] = confidence_summary
    metadata["flagged_segments"] = [item["id"] for item in confidence_summary.get("flagged_segments", [])]

    if cfg.junction_detector and cfg.junction_detector.enabled:
        junction_detector = JunctionDetector(cfg.junction_detector)
        junction_summary = junction_detector.annotate_nodes(
            image=image,
            nodes=nodes,
        )
        metadata["junction_detection"] = junction_summary

    if cfg.junction_patch_export and cfg.junction_patch_export.enabled:
        try:
            junction_export = _export_junction_patches(
                image=image,
                nodes=nodes,
                config=cfg.junction_patch_export,
            )
            metadata["junction_patch_export"] = junction_export
        except Exception as exc:  # pragma: no cover - zabezpieczenie debugowe
            metadata["junction_patch_export_error"] = str(exc)

    return LineDetectionResult(
        lines=segments,
        nodes=nodes,
        metadata=metadata,
        debug_artifacts=debug_artifacts,
    )


def _build_graph_from_skeleton(
    skeleton: np.ndarray,
    *,
    min_edge_length: float,
    node_merge_tolerance: float,
) -> Tuple[List[LineSegment], List[LineNode]]:
    if skeleton.size == 0:
        return [], []

    mask = skeleton.astype(bool)
    if not mask.any():
        return [], []

    node_candidates = _find_node_candidates(mask)
    if not node_candidates:
        first_coord = tuple(np.argwhere(mask)[0])
        node_candidates.append((int(first_coord[0]), int(first_coord[1])))

    clusters = _cluster_nodes(node_candidates, node_merge_tolerance)

    nodes: List[LineNode] = []
    node_index_by_coord: Dict[Tuple[int, int], int] = {}
    node_pixel_set: set[Tuple[int, int]] = set()

    for cluster_idx, cluster in enumerate(clusters):
        count = len(cluster["points"])
        avg_row = cluster["sum_row"] / count
        avg_col = cluster["sum_col"] / count
        position = (int(round(avg_col)), int(round(avg_row)))
        node = LineNode(id=f"node-{cluster_idx}", position=position, attached_segments=[])
        nodes.append(node)
        for point in cluster["points"]:
            coord = (int(point[0]), int(point[1]))
            node_index_by_coord[coord] = cluster_idx
            node_pixel_set.add(coord)

    visited_pairs: set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()
    segments: List[LineSegment] = []

    def ensure_node(coord: Tuple[int, int]) -> int:
        if coord not in node_index_by_coord:
            idx = len(nodes)
            node_index_by_coord[coord] = idx
            node_pixel_set.add(coord)
            node = LineNode(
                id=f"node-{idx}",
                position=(int(coord[1]), int(coord[0])),
                attached_segments=[],
            )
            nodes.append(node)
        return node_index_by_coord[coord]

    for node_coord in list(node_pixel_set):
        neighbors = _pixel_neighbors(mask, node_coord)
        for neighbor in neighbors:
            pair = (node_coord, neighbor)
            if pair in visited_pairs:
                continue

            end_coord, path = _trace_edge(mask, node_coord, neighbor, node_pixel_set, visited_pairs)
            if len(path) < 2:
                continue

            start_idx = ensure_node(node_coord)
            end_idx = ensure_node(end_coord)
            if start_idx == end_idx:
                continue

            length = _path_length(path)
            if length < min_edge_length:
                continue

            start_point = nodes[start_idx].position
            end_point = nodes[end_idx].position
            edge_id = f"edge-{len(segments)}"
            angle = math.degrees(math.atan2(end_point[1] - start_point[1], end_point[0] - start_point[0])) % 180
            segments.append(
                LineSegment(
                    id=edge_id,
                    start=start_point,
                    end=end_point,
                    length=float(length),
                    angle_deg=float(angle),
                )
            )
            nodes[start_idx].attached_segments.append(edge_id)
            nodes[end_idx].attached_segments.append(edge_id)

    filtered_nodes: List[LineNode] = []
    for node in nodes:
        node.attached_segments = sorted(set(node.attached_segments))
        if not node.attached_segments:
            continue
        node.id = f"node-{len(filtered_nodes)}"
        filtered_nodes.append(node)

    return segments, filtered_nodes


def _segment_candidates_from_contours(
    mask: np.ndarray,
    *,
    min_edge_length: float,
    contours: Optional[Sequence[np.ndarray]] = None,
) -> List[SegmentCandidate]:
    if mask.size == 0:
        return []

    local_contours: Sequence[np.ndarray]
    if contours is None:
        local_contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    else:
        local_contours = contours
    candidates: List[SegmentCandidate] = []

    for contour in local_contours:
        if contour is None or len(contour) < 3:
            continue

        area = cv2.contourArea(contour)
        if area <= 1.0:
            continue

        perimeter = cv2.arcLength(contour, True)
        epsilon = max(1.5, 0.01 * perimeter)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        points = approx if len(approx) >= 3 else contour

        vertices: List[Tuple[int, int]] = []
        for entry in points:
            x, y = map(int, entry[0])
            vertices.append((x, y))

        if len(vertices) < 3:
            continue

        simplified: List[Tuple[int, int]] = []
        for vertex in vertices:
            if not simplified or _point_distance(vertex, simplified[-1]) >= 1.0:
                simplified.append(vertex)
        if simplified and _point_distance(simplified[0], simplified[-1]) < 1.0:
            simplified[-1] = simplified[0]

        if len(simplified) < 3:
            continue

        count = len(simplified)
        for idx in range(count):
            start = simplified[idx]
            end = simplified[(idx + 1) % count]
            if start == end:
                continue
            length = _point_distance(start, end)
            if length < min_edge_length:
                continue
            candidates.append(
                SegmentCandidate(
                    start=(float(start[0]), float(start[1])),
                    end=(float(end[0]), float(end[1])),
                    priority=1,
                )
            )

    return candidates


def _candidate_covered_by_points(
    candidate: SegmentCandidate,
    points: Sequence[Tuple[float, float]],
    tolerance: float,
) -> bool:
    if not points:
        return False

    threshold = max(tolerance * 1.5, tolerance + 1.0)
    start_close = any(_point_distance(candidate.start, point) <= threshold for point in points)
    if not start_close:
        return False

    end_close = any(_point_distance(candidate.end, point) <= threshold for point in points)
    return end_close


def _contour_merge_tolerance(node_merge_tolerance: float, min_edge_length: float) -> float:
    return max(node_merge_tolerance * 6.0, min_edge_length * 0.5, 12.0)


def _prune_short_leaf_segments(
    segments: Sequence[LineSegment],
    nodes: Sequence[LineNode],
    *,
    contour_points: Sequence[Tuple[float, float]],
    contour_candidates: Sequence[SegmentCandidate],
    node_merge_tolerance: float,
    min_edge_length: float,
) -> Tuple[List[LineSegment], List[LineNode]]:
    if not segments or not nodes or not contour_points:
        return list(segments), list(nodes)

    contour_tolerance = max(node_merge_tolerance * 2.5, min_edge_length * 0.4, 10.0)
    spur_length = max(min_edge_length * 0.6, contour_tolerance)

    point_cache: Dict[Tuple[float, float], float] = {}

    def near_contour(point: Tuple[int, int]) -> bool:
        key = (float(point[0]), float(point[1]))
        if key not in point_cache:
            point_cache[key] = _point_set_distance((float(point[0]), float(point[1])), contour_points)
        return point_cache[key] <= contour_tolerance

    node_by_position: Dict[Tuple[int, int], LineNode] = {node.position: node for node in nodes}

    keep_segments: List[LineSegment] = []
    removed = False

    for segment in segments:
        length = float(segment.length)
        start_node = node_by_position.get(segment.start)
        end_node = node_by_position.get(segment.end)
        remove = False

        if length <= spur_length and start_node and end_node:
            start_degree = len(start_node.attached_segments)
            end_degree = len(end_node.attached_segments)
            start_near = start_degree <= 1 and near_contour(start_node.position)
            end_near = end_degree <= 1 and near_contour(end_node.position)

            if (start_near and end_degree >= 2) or (end_near and start_degree >= 2) or (start_near and end_near):
                remove = True

        if remove:
            removed = True
        else:
            keep_segments.append(segment)

    if not removed:
        return list(segments), list(nodes)

    candidate_list: List[SegmentCandidate] = [
        SegmentCandidate(
            start=(float(segment.start[0]), float(segment.start[1])),
            end=(float(segment.end[0]), float(segment.end[1])),
            priority=0,
        )
        for segment in keep_segments
    ]
    candidate_list.extend(contour_candidates)

    return _assemble_segments_from_candidates(
        candidate_list,
        node_merge_tolerance=node_merge_tolerance,
        min_edge_length=min_edge_length,
    )


def _local_density(mask: np.ndarray, position: LinePoint, radius: int) -> float:
    if mask is None or mask.size == 0 or radius <= 0:
        return 0.0

    rows, cols = mask.shape[:2]
    x, y = int(round(position[0])), int(round(position[1]))
    y = max(0, min(rows - 1, y))
    x = max(0, min(cols - 1, x))

    y_min = max(0, y - radius)
    y_max = min(rows, y + radius + 1)
    x_min = max(0, x - radius)
    x_max = min(cols, x + radius + 1)

    roi = mask[y_min:y_max, x_min:x_max]
    if roi.size == 0:
        return 0.0

    return float(np.count_nonzero(roi)) / float(roi.size)


def _prune_textual_spurs(
    segments: Sequence[LineSegment],
    nodes: Sequence[LineNode],
    *,
    binary_mask: np.ndarray,
    skeleton_mask: np.ndarray,
    contour_candidates: Sequence[SegmentCandidate],
    node_merge_tolerance: float,
    min_edge_length: float,
) -> Tuple[List[LineSegment], List[LineNode]]:
    if not segments or not nodes or binary_mask is None or binary_mask.size == 0:
        return list(segments), list(nodes)

    position_to_node: Dict[Tuple[int, int], LineNode] = {node.position: node for node in nodes}
    segment_by_id: Dict[str, LineSegment] = {segment.id: segment for segment in segments}

    sample_radius = int(round(max(node_merge_tolerance * 2.5, min_edge_length * 0.6, 8.0)))
    sample_radius = max(sample_radius, 5)
    short_length = max(min_edge_length * 1.35, 18.0)
    dense_threshold = 0.22
    density_margin = 0.08
    skeleton_threshold = 0.015

    segments_to_remove: set[str] = set()

    for node in nodes:
        if len(node.attached_segments) != 1:
            continue

        segment_id = node.attached_segments[0]
        segment = segment_by_id.get(segment_id)
        if segment is None:
            continue

        if float(segment.length) > short_length:
            continue

        other_pos = segment.end if segment.start == node.position else segment.start
        other_node = position_to_node.get(other_pos)
        if other_node is None:
            continue

        other_degree = len(other_node.attached_segments)
        if other_degree <= 1:
            continue

        local_density = _local_density(binary_mask, node.position, sample_radius)
        other_density = _local_density(binary_mask, other_pos, sample_radius + 2)
        skeleton_density = _local_density(skeleton_mask, node.position, sample_radius)

        if (
            local_density >= dense_threshold
            and local_density >= other_density + density_margin
            and skeleton_density >= skeleton_threshold
        ):
            segments_to_remove.add(segment_id)

    if not segments_to_remove:
        return list(segments), list(nodes)

    keep_segments: List[LineSegment] = [segment for segment in segments if segment.id not in segments_to_remove]

    candidate_list: List[SegmentCandidate] = [
        SegmentCandidate(
            start=(float(segment.start[0]), float(segment.start[1])),
            end=(float(segment.end[0]), float(segment.end[1])),
            priority=0,
        )
        for segment in keep_segments
    ]
    candidate_list.extend(contour_candidates)

    return _assemble_segments_from_candidates(
        candidate_list,
        node_merge_tolerance=node_merge_tolerance,
        min_edge_length=min_edge_length,
    )


def _filter_textual_endpoints(
    segments: Sequence[LineSegment],
    nodes: Sequence[LineNode],
    *,
    binary_mask: np.ndarray,
    skeleton_mask: np.ndarray,
    contour_candidates: Sequence[SegmentCandidate],
    node_merge_tolerance: float,
    min_edge_length: float,
    max_log_entries: int = 32,
) -> Tuple[List[LineSegment], List[LineNode], Dict[str, Any]]:
    sample_radius = int(round(max(node_merge_tolerance * 2.8, min_edge_length * 0.9, 12.0)))
    sample_radius = max(sample_radius, 8)
    short_branch_limit = float(max(42.0, min_edge_length * 3.4))

    thresholds = {
        "area_dense": float(max(140.0, min_edge_length * min_edge_length * 0.9)),
        "ink_dense": 0.28,
        "fill_dense": 0.56,
        "aspect_dense": 2.7,
        "skeleton_min": 0.019,
        "area_cluster": float(max(110.0, min_edge_length * min_edge_length * 0.7)),
        "ink_cluster": 0.24,
        "fill_cluster": 0.52,
        "neighbor_radius": float(sample_radius * 0.9),
        "area_local": float(max(90.0, min_edge_length * min_edge_length * 0.6)),
        "ink_local": 0.26,
        "aspect_local": 2.3,
        "density_margin": 0.11,
    }

    summary: Dict[str, Any] = {
        "evaluated": 0,
        "removed": 0,
        "kept": 0,
        "sample": [],
        "thresholds": thresholds,
        "limits": {
            "short_branch_limit": short_branch_limit,
            "sample_radius": sample_radius,
        },
    }

    if not segments or not nodes or binary_mask is None or binary_mask.size == 0:
        summary["kept"] = len(nodes)
        return list(segments), list(nodes), summary

    position_to_node: Dict[LinePoint, LineNode] = {node.position: node for node in nodes}
    segment_by_id: Dict[str, LineSegment] = {segment.id: segment for segment in segments}

    segments_to_remove: set[str] = set()
    sample_records: List[Dict[str, Any]] = []

    for node in nodes:
        if len(node.attached_segments) != 1:
            continue

        segment_id = node.attached_segments[0]
        segment = segment_by_id.get(segment_id)
        if segment is None:
            continue

        other_pos = segment.end if segment.start == node.position else segment.start
        other_node = position_to_node.get(other_pos)
        if other_node is None or len(other_node.attached_segments) <= 1:
            continue

        branch_length = float(segment.length)
        metrics: Dict[str, Any] = _endpoint_patch_stats(binary_mask, node.position, sample_radius)
        metrics["branch_length"] = branch_length
        metrics["local_density"] = _local_density(binary_mask, node.position, sample_radius)
        metrics["other_density"] = _local_density(binary_mask, other_pos, sample_radius)
        metrics["skeleton_density"] = _local_density(skeleton_mask, node.position, sample_radius)
        metrics["nearest_node_distance"] = _nearest_node_distance(
            node.position,
            nodes,
            exclude_positions={node.position, other_pos},
        )
        metrics["node_id"] = node.id
        metrics["segment_id"] = segment_id

        summary["evaluated"] += 1

        remove_candidate, reason = _should_remove_endpoint(metrics, thresholds, short_branch_limit)
        if remove_candidate:
            segments_to_remove.add(segment_id)
            summary["removed"] += 1
        else:
            summary["kept"] += 1

        if len(sample_records) < max_log_entries:
            nearest = metrics.get("nearest_node_distance")
            sample_records.append(
                {
                    "node_id": node.id,
                    "segment_id": segment_id,
                    "branch_length": round(branch_length, 3),
                    "area": int(metrics.get("area", 0)),
                    "ink_ratio": round(float(metrics.get("ink_ratio", 0.0)), 4),
                    "fill_ratio": round(float(metrics.get("fill_ratio", 0.0)), 4),
                    "aspect_ratio": round(float(metrics.get("aspect_ratio", 0.0)), 4),
                    "local_density": round(float(metrics.get("local_density", 0.0)), 4),
                    "other_density": round(float(metrics.get("other_density", 0.0)), 4),
                    "skeleton_density": round(float(metrics.get("skeleton_density", 0.0)), 4),
                    "nearest_node_distance": None if nearest is None else round(float(nearest), 3),
                    "decision": remove_candidate,
                    "reason": reason or None,
                }
            )

    summary["sample"] = sample_records
    if segments_to_remove:
        summary["removed_segments"] = sorted(segments_to_remove)

    if not segments_to_remove:
        return list(segments), list(nodes), summary

    keep_segments: List[LineSegment] = [segment for segment in segments if segment.id not in segments_to_remove]

    candidate_list: List[SegmentCandidate] = [
        SegmentCandidate(
            start=(float(segment.start[0]), float(segment.start[1])),
            end=(float(segment.end[0]), float(segment.end[1])),
            priority=0,
        )
        for segment in keep_segments
    ]
    candidate_list.extend(contour_candidates)

    new_segments, new_nodes = _assemble_segments_from_candidates(
        candidate_list,
        node_merge_tolerance=node_merge_tolerance,
        min_edge_length=min_edge_length,
    )

    return new_segments, new_nodes, summary


def _endpoint_patch_stats(mask: np.ndarray, position: LinePoint, radius: int) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "area": 0,
        "bbox_width": 0,
        "bbox_height": 0,
        "bbox_area": 0,
        "ink_ratio": 0.0,
        "fill_ratio": 0.0,
        "aspect_ratio": 0.0,
        "extent_ratio": 0.0,
    }

    if mask is None or mask.size == 0 or radius <= 0:
        return stats

    rows, cols = mask.shape[:2]
    x = int(round(position[0]))
    y = int(round(position[1]))
    y = max(0, min(rows - 1, y))
    x = max(0, min(cols - 1, x))

    y_min = max(0, y - radius)
    y_max = min(rows, y + radius + 1)
    x_min = max(0, x - radius)
    x_max = min(cols, x + radius + 1)

    patch = mask[y_min:y_max, x_min:x_max]
    if patch.size == 0:
        return stats

    binary_patch = patch > 0
    if not binary_patch.any():
        return stats

    ys, xs = np.nonzero(binary_patch)
    area = int(xs.size)
    width = int(xs.max() - xs.min() + 1)
    height = int(ys.max() - ys.min() + 1)
    bbox_area = int(width * height)
    patch_area = float(patch.size)

    ink_ratio = float(area) / patch_area
    fill_ratio = float(area) / float(bbox_area) if bbox_area > 0 else 0.0
    aspect_ratio = (
        float(max(width, height)) / float(min(width, height)) if min(width, height) > 0 else float(max(width, height))
    )
    extent_ratio = float(bbox_area) / patch_area if patch_area > 0 else 0.0

    stats.update(
        {
            "area": area,
            "bbox_width": width,
            "bbox_height": height,
            "bbox_area": bbox_area,
            "ink_ratio": ink_ratio,
            "fill_ratio": fill_ratio,
            "aspect_ratio": aspect_ratio,
            "extent_ratio": extent_ratio,
        }
    )

    return stats


def _nearest_node_distance(
    position: LinePoint,
    nodes: Sequence[LineNode],
    *,
    exclude_positions: set[LinePoint],
) -> Optional[float]:
    distances: List[float] = []
    for candidate in nodes:
        if candidate.position in exclude_positions:
            continue
        distances.append(_point_distance(position, candidate.position))

    if not distances:
        return None

    return float(min(distances))


def _should_remove_endpoint(
    metrics: Dict[str, Any],
    thresholds: Dict[str, float],
    short_branch_limit: float,
) -> Tuple[bool, str]:
    branch_length = float(metrics.get("branch_length", 0.0))
    if branch_length > short_branch_limit:
        return False, ""

    area = float(metrics.get("area", 0.0))
    if area <= 0.0:
        return False, ""

    aspect = float(metrics.get("aspect_ratio", 0.0))
    ink_ratio = float(metrics.get("ink_ratio", 0.0))
    fill_ratio = float(metrics.get("fill_ratio", 0.0))
    skeleton_density = float(metrics.get("skeleton_density", 0.0))
    nearest = metrics.get("nearest_node_distance")
    local_density = float(metrics.get("local_density", 0.0))
    other_density = float(metrics.get("other_density", 0.0))

    max_density = max(local_density, other_density)
    dense_pair_length = min(max(short_branch_limit * 0.5, 10.0), 24.0)
    neighbor_limit = max(thresholds.get("neighbor_radius", short_branch_limit * 0.4) * 2.0, 24.0)
    min_fill = thresholds["fill_cluster"] * 0.65
    min_density_peak = thresholds["ink_cluster"] + 0.08
    aspect_limit = thresholds["aspect_local"]

    pair_density_floor = max(thresholds["ink_local"], thresholds["ink_cluster"] * 0.9)
    uniform_density = abs(local_density - other_density) <= thresholds["density_margin"] * 0.5
    near_neighbor = nearest is not None and float(nearest) <= neighbor_limit * 1.1

    if (
        branch_length <= short_branch_limit * 0.55
        and area >= thresholds["area_local"]
        and fill_ratio >= thresholds["fill_cluster"] * 0.7
        and ink_ratio >= pair_density_floor
        and local_density >= thresholds["ink_local"]
        and other_density >= thresholds["ink_local"]
        and uniform_density
        and aspect <= thresholds["aspect_dense"]
        and skeleton_density >= thresholds["skeleton_min"] * 1.15
        and near_neighbor
    ):
        return True, "text_pair"

    if (
        area >= thresholds["area_dense"]
        and ink_ratio >= thresholds["ink_dense"]
        and fill_ratio >= thresholds["fill_dense"]
        and aspect <= thresholds["aspect_dense"]
        and skeleton_density >= thresholds["skeleton_min"]
    ):
        return True, "dense_blob"

    if (
        area >= thresholds["area_cluster"]
        and ink_ratio >= thresholds["ink_cluster"]
        and fill_ratio >= thresholds["fill_cluster"]
        and nearest is not None
        and float(nearest) <= thresholds["neighbor_radius"]
        and skeleton_density >= thresholds["skeleton_min"]
    ):
        return True, "cluster"

    if (
        area >= thresholds["area_local"]
        and ink_ratio >= thresholds["ink_local"]
        and aspect <= thresholds["aspect_local"]
        and local_density >= other_density + thresholds["density_margin"]
    ):
        return True, "density_margin"

    if (
        branch_length <= dense_pair_length
        and area >= thresholds["area_local"]
        and ink_ratio >= thresholds["ink_local"]
        and fill_ratio >= min_fill
        and max_density >= min_density_peak
        and aspect <= aspect_limit
        and skeleton_density >= thresholds["skeleton_min"] * 1.6
        and nearest is not None
        and float(nearest) <= neighbor_limit
    ):
        return True, "dense_pair"

    return False, ""


def _merge_straight_chains(
    segments: Sequence[LineSegment],
    nodes: Sequence[LineNode],
    *,
    contour_candidates: Sequence[SegmentCandidate],
    node_merge_tolerance: float,
    min_edge_length: float,
    angle_tolerance_deg: float = 15.0,
) -> Tuple[List[LineSegment], List[LineNode]]:
    if not segments or not nodes:
        return list(segments), list(nodes)

    position_to_node: Dict[Tuple[int, int], LineNode] = {node.position: node for node in nodes}
    segment_by_id: Dict[str, LineSegment] = {segment.id: segment for segment in segments}

    cos_threshold = -math.cos(math.radians(angle_tolerance_deg))
    length_multiplier = 1.25
    extra_gap = max(node_merge_tolerance * 3.0, min_edge_length)

    segments_to_remove: set[str] = set()
    new_candidates: List[SegmentCandidate] = []
    seen_pairs: set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()

    for node in nodes:
        if len(node.attached_segments) != 2:
            continue

        seg_a_id, seg_b_id = node.attached_segments
        if seg_a_id in segments_to_remove or seg_b_id in segments_to_remove:
            continue

        seg_a = segment_by_id.get(seg_a_id)
        seg_b = segment_by_id.get(seg_b_id)
        if seg_a is None or seg_b is None:
            continue

        other_a_pos = seg_a.end if seg_a.start == node.position else seg_a.start
        other_b_pos = seg_b.end if seg_b.start == node.position else seg_b.start

        if other_a_pos == other_b_pos:
            continue

        vec_a = (other_a_pos[0] - node.position[0], other_a_pos[1] - node.position[1])
        vec_b = (other_b_pos[0] - node.position[0], other_b_pos[1] - node.position[1])

        len_a = math.hypot(vec_a[0], vec_a[1])
        len_b = math.hypot(vec_b[0], vec_b[1])
        if len_a < 1.0 or len_b < 1.0:
            continue

        dot = vec_a[0] * vec_b[0] + vec_a[1] * vec_b[1]
        cos_angle = dot / (len_a * len_b)
        if cos_angle > cos_threshold:
            continue

        combined_length = _point_distance(other_a_pos, other_b_pos)
        current_length = float(seg_a.length) + float(seg_b.length)
        if combined_length > max(current_length * length_multiplier, current_length + extra_gap):
            continue

        other_a_node = position_to_node.get(other_a_pos)
        other_b_node = position_to_node.get(other_b_pos)
        if other_a_node is None or other_b_node is None:
            continue

        pair_key = tuple(sorted((other_a_pos, other_b_pos)))
        if pair_key in seen_pairs:
            continue

        seen_pairs.add(pair_key)
        segments_to_remove.update({seg_a_id, seg_b_id})
        new_candidates.append(
            SegmentCandidate(
                start=(float(other_a_pos[0]), float(other_a_pos[1])),
                end=(float(other_b_pos[0]), float(other_b_pos[1])),
                priority=2,
            )
        )

    if not segments_to_remove:
        return list(segments), list(nodes)

    keep_segments: List[LineSegment] = [segment for segment in segments if segment.id not in segments_to_remove]

    candidate_list: List[SegmentCandidate] = [
        SegmentCandidate(
            start=(float(segment.start[0]), float(segment.start[1])),
            end=(float(segment.end[0]), float(segment.end[1])),
            priority=0,
        )
        for segment in keep_segments
    ]
    candidate_list.extend(new_candidates)
    candidate_list.extend(contour_candidates)

    return _assemble_segments_from_candidates(
        candidate_list,
        node_merge_tolerance=node_merge_tolerance,
        min_edge_length=min_edge_length,
    )


def _assemble_segments_from_candidates(
    candidates: Sequence[SegmentCandidate],
    *,
    node_merge_tolerance: float,
    min_edge_length: float,
) -> Tuple[List[LineSegment], List[LineNode]]:
    if not candidates:
        return [], []

    node_positions: List[Tuple[float, float]] = []

    def locate(point: Tuple[float, float]) -> int:
        px, py = float(point[0]), float(point[1])
        for idx, existing in enumerate(node_positions):
            if _point_distance(existing, (px, py)) <= node_merge_tolerance:
                return idx
        node_positions.append((px, py))
        return len(node_positions) - 1

    pair_to_segment: Dict[Tuple[int, int], Dict[str, Any]] = {}

    for candidate in candidates:
        start_idx = locate(candidate.start)
        end_idx = locate(candidate.end)
        if start_idx == end_idx:
            continue

        length = _point_distance(candidate.start, candidate.end)
        if length < min_edge_length:
            continue

        pair = (min(start_idx, end_idx), max(start_idx, end_idx))
        existing = pair_to_segment.get(pair)
        if (
            existing is None
            or candidate.priority > existing["priority"]
            or (candidate.priority == existing["priority"] and length > existing["length"])
        ):
            pair_to_segment[pair] = {
                "start_idx": start_idx,
                "end_idx": end_idx,
                "priority": candidate.priority,
                "length": length,
            }

    nodes: List[LineNode] = []
    for idx, (x, y) in enumerate(node_positions):
        node = LineNode(id=f"node-{idx}", position=(int(round(x)), int(round(y))), attached_segments=[])
        nodes.append(node)

    segments: List[LineSegment] = []
    for pair, data in sorted(pair_to_segment.items()):
        start_idx = data["start_idx"]
        end_idx = data["end_idx"]
        start_pos = nodes[start_idx].position
        end_pos = nodes[end_idx].position

        length = _point_distance(start_pos, end_pos)
        if length < min_edge_length:
            continue

        seg_id = f"edge-{len(segments)}"
        angle = math.degrees(math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])) % 180
        segment = LineSegment(
            id=seg_id,
            start=start_pos,
            end=end_pos,
            length=length,
            angle_deg=angle,
        )
        segments.append(segment)
        nodes[start_idx].attached_segments.append(seg_id)
        nodes[end_idx].attached_segments.append(seg_id)

    filtered_nodes: List[LineNode] = []
    for node in nodes:
        if not node.attached_segments:
            continue
        node.attached_segments = sorted(set(node.attached_segments))
        node.id = f"node-{len(filtered_nodes)}"
        filtered_nodes.append(node)

    return segments, filtered_nodes


def _find_node_candidates(mask: np.ndarray) -> List[Tuple[int, int]]:
    rows, cols = mask.shape
    candidates: List[Tuple[int, int]] = []

    for row in range(rows):
        for col in range(cols):
            if not mask[row, col]:
                continue
            neighbors = _pixel_neighbors(mask, (row, col))
            degree = len(neighbors)
            if degree != 2:
                candidates.append((row, col))
            elif _is_corner_pixel((row, col), neighbors):
                candidates.append((row, col))

    return candidates


def _cluster_nodes(
    points: Sequence[Tuple[int, int]],
    tolerance: float,
) -> List[Dict[str, Any]]:
    clusters: List[Dict[str, Any]] = []

    for row, col in points:
        coord = (float(row), float(col))
        matched_cluster = None
        for cluster in clusters:
            center_row = cluster["sum_row"] / len(cluster["points"])
            center_col = cluster["sum_col"] / len(cluster["points"])
            if _point_distance((center_col, center_row), (coord[1], coord[0])) <= tolerance:
                matched_cluster = cluster
                break

        if matched_cluster is None:
            clusters.append(
                {
                    "points": [(coord[0], coord[1])],
                    "sum_row": coord[0],
                    "sum_col": coord[1],
                }
            )
        else:
            matched_cluster["points"].append((coord[0], coord[1]))
            matched_cluster["sum_row"] += coord[0]
            matched_cluster["sum_col"] += coord[1]

    return clusters


def _trace_edge(
    mask: np.ndarray,
    start: Tuple[int, int],
    first_step: Tuple[int, int],
    node_pixels: set[Tuple[int, int]],
    visited_pairs: set[Tuple[Tuple[int, int], Tuple[int, int]]],
) -> Tuple[Tuple[int, int], List[Tuple[int, int]]]:
    path: List[Tuple[int, int]] = [start, first_step]
    prev = start
    current = first_step
    visited_pairs.add((prev, current))
    visited_pairs.add((current, prev))

    while True:
        if current in node_pixels and current != start:
            return current, path

        neighbors = _pixel_neighbors(mask, current)
        next_candidates = [nb for nb in neighbors if nb != prev]

        if not next_candidates:
            return current, path

        if len(next_candidates) > 1 and current not in node_pixels:
            node_pixels.add(current)
            return current, path

        next_pixel = next_candidates[0]
        if (current, next_pixel) in visited_pairs:
            return current, path

        path.append(next_pixel)
        visited_pairs.add((current, next_pixel))
        visited_pairs.add((next_pixel, current))
        prev, current = current, next_pixel


def _pixel_neighbors(mask: np.ndarray, coord: Tuple[int, int]) -> List[Tuple[int, int]]:
    row, col = coord
    rows, cols = mask.shape
    result: List[Tuple[int, int]] = []
    for dr, dc in NEIGHBOR_OFFSETS:
        nr, nc = row + dr, col + dc
        if 0 <= nr < rows and 0 <= nc < cols and mask[nr, nc]:
            result.append((nr, nc))
    return result


CORNER_STRAIGHTNESS_THRESHOLD = -0.7


def _is_corner_pixel(coord: Tuple[int, int], neighbors: Sequence[Tuple[int, int]]) -> bool:
    if len(neighbors) != 2:
        return False

    row, col = coord
    (r1, c1), (r2, c2) = neighbors
    dr1, dc1 = r1 - row, c1 - col
    dr2, dc2 = r2 - row, c2 - col

    len1 = math.hypot(dr1, dc1)
    len2 = math.hypot(dr2, dc2)
    if len1 == 0 or len2 == 0:
        return False

    dot = (dr1 * dr2 + dc1 * dc2) / (len1 * len2)
    return dot > CORNER_STRAIGHTNESS_THRESHOLD


def _path_length(path: Sequence[Tuple[int, int]]) -> float:
    total = 0.0
    for (r1, c1), (r2, c2) in zip(path, path[1:]):
        total += math.hypot(c2 - c1, r2 - r1)
    return total


def _projection_parameter(a: LinePoint, b: LinePoint, point: Tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    px, py = point

    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return 0.0

    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    return max(0.0, min(1.0, t))


def _are_segments_colinear(
    seg_a: LineSegment,
    seg_b: LineSegment,
    angle_tol: float,
    gap_tol: int,
) -> bool:
    """Sprawdza kolinearność dwóch odcinków z tolerancją."""

    if abs(seg_a.angle_deg - seg_b.angle_deg) > angle_tol:
        return False

    dist = min(
        _point_distance(seg_a.start, seg_b.start),
        _point_distance(seg_a.start, seg_b.end),
        _point_distance(seg_a.end, seg_b.start),
        _point_distance(seg_a.end, seg_b.end),
    )
    return dist <= gap_tol


def _combine_segments(segments: Sequence[LineSegment]) -> LineSegment:
    """Łączy grupę kolinearnych segmentów w jeden."""

    points = [seg.start for seg in segments] + [seg.end for seg in segments]
    start = min(points, key=lambda p: (p[0], p[1]))
    end = max(points, key=lambda p: (p[0], p[1]))
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0])) % 180
    return LineSegment(
        id="seg-merged-" + "-".join(seg.id for seg in segments),
        start=start,
        end=end,
        length=length,
        angle_deg=angle,
    )


def _segment_intersection(
    p1: LinePoint,
    p2: LinePoint,
    p3: LinePoint,
    p4: LinePoint,
) -> Optional[Tuple[float, float]]:
    """Zwraca punkt przecięcia dwóch odcinków (lub None)."""

    denom = (p1[0] - p2[0]) * (p3[1] - p4[1]) - (p1[1] - p2[1]) * (p3[0] - p4[0])
    if denom == 0:
        return None

    num_x = (p1[0] * p2[1] - p1[1] * p2[0]) * (p3[0] - p4[0]) - (p1[0] - p2[0]) * (p3[0] * p4[1] - p3[1] * p4[0])
    num_y = (p1[0] * p2[1] - p1[1] * p2[0]) * (p3[1] - p4[1]) - (p1[1] - p2[1]) * (p3[0] * p4[1] - p3[1] * p4[0])

    x = num_x / denom
    y = num_y / denom

    tol = 2.5
    if _point_on_segment((x, y), p1, p2, tol) and _point_on_segment((x, y), p3, p4, tol):
        return x, y
    return None


def _point_on_segment(point: Tuple[float, float], a: LinePoint, b: LinePoint, tol: float = 1e-6) -> bool:
    """Sprawdza czy punkt leży w obrębie odcinka."""

    min_x, max_x = sorted((a[0], b[0]))
    min_y, max_y = sorted((a[1], b[1]))
    if not (min_x - tol <= point[0] <= max_x + tol and min_y - tol <= point[1] <= max_y + tol):
        return False

    # dodatkowe sprawdzenie odległości od odcinka, aby uniknąć punktów bardzo odległych
    return _distance_point_to_segment(point, a, b) <= tol


def _point_distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _point_set_distance(point: Tuple[float, float], points: Sequence[Tuple[float, float]]) -> float:
    return min(_point_distance(point, candidate) for candidate in points)


def _distance_point_to_segment(point: Tuple[float, float], a: LinePoint, b: LinePoint) -> float:
    """Oblicza odległość punktu od odcinka."""

    ax, ay = a
    bx, by = b
    px, py = point

    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)

    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    closest_x = ax + t * dx
    closest_y = ay + t * dy
    return math.hypot(px - closest_x, py - closest_y)


def _rescale_point(point: Tuple[float, float] | LinePoint, scale: float) -> LinePoint:
    """Skaluje współrzędne punktu i zaokrągla do najbliższej kratki pikseli."""

    return int(round(float(point[0]) * scale)), int(round(float(point[1]) * scale))


def _build_junction_patch_extractor(image: np.ndarray, patch_size: int) -> Callable[[LinePoint], np.ndarray]:
    gray = _ensure_grayscale(image)
    target_size = max(8, int(patch_size))
    if target_size % 2 == 1:
        target_size += 1
    half = target_size // 2
    pad = half + 2
    padded = np.pad(gray, ((pad, pad), (pad, pad)), mode="reflect")

    def _extract(position: LinePoint) -> np.ndarray:
        col = int(position[0])
        row = int(position[1])
        start_row = row - half + pad
        start_col = col - half + pad
        end_row = start_row + target_size
        end_col = start_col + target_size
        return padded[start_row:end_row, start_col:end_col].copy()

    return _extract


def _enhance_lines_from_color(image: np.ndarray, config: LineDetectionConfig) -> np.ndarray:
    if image.ndim != 3:
        return image

    try:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    except cv2.error:
        return image

    sat_thresh = int(np.clip(config.color_enhancement_saturation_threshold, 0, 255))
    val_thresh = int(np.clip(config.color_enhancement_value_threshold, 0, 255))
    lower = (0, 0, 0)
    upper = (180, sat_thresh, val_thresh)
    candidate = cv2.inRange(hsv, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, kernel, iterations=1)
    candidate = cv2.GaussianBlur(candidate, (5, 5), 0)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mask = candidate.astype(np.float32) / 255.0
    strength = float(np.clip(config.color_enhancement_strength, 0.0, 1.0))
    darkening = mask * (strength * 160.0)
    enhanced = np.clip(gray - darkening, 0.0, 255.0).astype(np.uint8)
    return enhanced


def _detect_dotted_candidates(
    image: np.ndarray, config: LineDetectionConfig
) -> Tuple[np.ndarray, Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] | None:
    # Accept either color (H,S,V) or grayscale input.
    if image.ndim == 3:
        try:
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        except cv2.error:
            return None
        sat_channel = hsv[:, :, 1]
        val_channel = hsv[:, :, 2]
    elif image.ndim == 2:
        # single-channel grayscale: treat saturation as 'low' (0) so the
        # saturation check will pass when the threshold allows it and use
        # the grayscale as value channel.
        sat_channel = np.zeros_like(image, dtype=np.uint8)
        val_channel = image
    else:
        return None

    sat_thresh = int(np.clip(config.dotted_line_bridge_saturation_threshold, 0, 255))
    val_thresh = int(np.clip(config.dotted_line_bridge_value_threshold, 0, 255))

    # Low saturation helps pick up greyscale/drawn dots. We look for both
    # bright AND dark candidates (some schematics use dark-filled dots,
    # other drawing tools might produce bright marks). To preserve the
    # existing config semantics (val_thresh usually set high for bright
    # candidates) we build both sides symmetrically: dark_threshold :=
    # 255 - val_thresh.
    mask = cv2.inRange(sat_channel, 0, sat_thresh)
    bright_mask = cv2.inRange(val_channel, val_thresh, 255)
    dark_mask = cv2.inRange(val_channel, 0, max(0, 255 - val_thresh))
    combined = cv2.bitwise_and(mask, cv2.bitwise_or(bright_mask, dark_mask))
    if cv2.countNonZero(combined) == 0:
        return None

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel, iterations=1)
    if cv2.countNonZero(cleaned) == 0:
        cleaned = combined

    # Szacujemy orientację poprzez gradient Sobela
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    angle = cv2.phase(grad_x, grad_y, angleInDegrees=True)
    angle = angle % 180.0

    vertical_mask = ((angle >= 60) & (angle <= 120)).astype(np.uint8)
    horizontal_mask = ((angle <= 20) | (angle >= 160)).astype(np.uint8)
    diag_pos_mask = ((angle > 20) & (angle < 60)).astype(np.uint8)
    diag_neg_mask = ((angle > 120) & (angle < 160)).astype(np.uint8)

    dotted = (cleaned > 0).astype(np.uint8)
    vertical = cv2.bitwise_and(dotted, vertical_mask)
    horizontal = cv2.bitwise_and(dotted, horizontal_mask)

    dilated_common = cv2.dilate(dotted, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)
    # return a tuple (general_mask, (vertical_mask, horizontal_mask, diag_pos_mask, diag_neg_mask))
    return dilated_common, (vertical, horizontal, diag_pos_mask, diag_neg_mask)


def _detect_text_mask(image: np.ndarray, config: LineDetectionConfig) -> np.ndarray:
    """Heurystyczne wykrywanie obszarów tekstowych / etykiet.

    Zwraca binarną maskę (0/1) z tymi obszarami. Heurystyka jest konserwatywna:
    skupia się na wielu drobnych komponentach w ciasnym prostokącie (linia tekstu).
    """
    if image is None or image.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)

    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # Binaryzuj ostro (OTSU) żeby wydzielić drobne składowe
    try:
        _, thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    except cv2.error:
        thr = (gray > 0).astype(np.uint8) * 255

    # Znajdź małe komponenty (potencjalne litery / elementy tekstowe)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thr.astype(np.uint8), connectivity=8)
    h, w = thr.shape[:2]
    small_mask = np.zeros((h, w), dtype=np.uint8)
    min_area = max(1, int(getattr(config, "text_mask_min_component_area", 4)))
    max_area = int(getattr(config, "text_mask_max_component_area", 500))
    centroids_list = []
    for label_idx in range(1, num_labels):
        area = int(stats[label_idx, cv2.CC_STAT_AREA])
        if min_area <= area <= max_area:
            small_mask[labels == label_idx] = 255
            # record centroid for cluster counting
            cx, cy = int(centroids[label_idx][0]), int(centroids[label_idx][1])
            centroids_list.append((cx, cy))

    # continue even if there are no small components — we'll fall back to a
    # density-based test for larger filled blocks if needed

    # Dilate small components to join nearby letters into a line-like cluster
    # — this helps when individual glyphs are separate small contours
    dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3))
    dilated_small = cv2.dilate(small_mask, dilate_kernel, iterations=1)
    clusters, _ = cv2.findContours(dilated_small.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros((h, w), dtype=np.uint8)
    components_threshold = max(1, int(getattr(config, "text_mask_components_threshold", 3)))
    min_wh_ratio = float(getattr(config, "text_mask_min_width_height_ratio", 1.8))
    expand = int(getattr(config, "text_mask_expand_px", 4))

    for ctr in clusters:
        x, y, cw, ch = cv2.boundingRect(ctr)
        # Count how many of the small centroids fall into this bbox
        count = sum(1 for cx, cy in centroids_list if x <= cx < x + cw and y <= cy < y + ch)
        if count >= components_threshold and cw / max(1.0, ch) >= min_wh_ratio:
            # expand a bit to include margin
            x0 = max(0, x - expand)
            y0 = max(0, y - expand)
            x1 = min(w, x + cw + expand)
            y1 = min(h, y + ch + expand)
            mask[y0:y1, x0:x1] = 255

    # If our small-component heuristic produced nothing, fall back to a
    # local-density based detection: for larger filled blocks (e.g. dense
    # annotation boxes) detect rectangular regions that look like text lines
    # (wide + high foreground density).
    if cv2.countNonZero(mask) == 0:
        num_labels2, labels2, stats2, _ = cv2.connectedComponentsWithStats(
            (thr > 0).astype(np.uint8) * 255, connectivity=8
        )
        for li in range(1, num_labels2):
            area = int(stats2[li, cv2.CC_STAT_AREA])
            x, y, cw, ch = int(stats2[li, 0]), int(stats2[li, 1]), int(stats2[li, 2]), int(stats2[li, 3])
            if area < max_area:
                continue
            # density threshold — how much of bbox is foreground
            density = float(area) / float(max(1, cw * ch))
            if density >= 0.2 and (cw / max(1.0, ch)) >= min_wh_ratio and cw >= 10:
                x0 = max(0, x - expand)
                y0 = max(0, y - expand)
                x1 = min(w, x + cw + expand)
                y1 = min(h, y + ch + expand)
                mask[y0:y1, x0:x1] = 255

    return mask


def _export_junction_patches(
    *,
    image: np.ndarray,
    nodes: Sequence[LineNode],
    config: JunctionPatchExportConfig,
) -> Dict[str, Any]:
    if not nodes:
        return {"saved": 0}

    min_degree = max(1, int(config.min_node_degree))
    patch_size = max(8, int(config.patch_size))
    extractor = _build_junction_patch_extractor(image, patch_size)

    output_dir = Path(config.output_dir)
    label_dir = output_dir / config.default_label
    for label in ("dot_present", "no_dot", "unknown"):
        (output_dir / label).mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
    saved_paths: List[str] = []
    manifest_entries: List[Dict[str, Any]] = []
    limit = config.limit_per_image

    for idx, node in enumerate(nodes):
        degree = len(node.attached_segments)
        if degree < min_degree:
            continue
        if limit is not None and len(saved_paths) >= limit:
            break

        patch = extractor(node.position)
        filename = f"junction_{timestamp}_{node.id}_{idx}.png"
        sanitized = _safe_filename(filename)
        target_path = (label_dir / sanitized).resolve()
        cv2.imwrite(str(target_path), patch)
        saved_paths.append(str(target_path))
        row, col = map(int, node.position)
        manifest_entries.append(
            {
                "filename": target_path.name,
                "label": config.default_label,
                "node_id": node.id,
                "degree": degree,
                "position_row": row,
                "position_col": col,
                "timestamp": timestamp,
            }
        )

    _append_manifest(output_dir / config.manifest_name, manifest_entries)
    return {
        "saved": len(saved_paths),
        "label": config.default_label,
        "directory": str(label_dir),
    }


def _append_manifest(path: Path, entries: Sequence[Dict[str, Any]]) -> None:
    if not entries:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    fieldnames = [
        "filename",
        "label",
        "node_id",
        "degree",
        "position_row",
        "position_col",
        "timestamp",
    ]
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for entry in entries:
            writer.writerow(entry)


def _safe_filename(value: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    return "".join(char if char in allowed else "_" for char in value)


def _softmax(values: Sequence[float]) -> np.ndarray:
    scores = np.asarray(values, dtype=np.float32)
    if scores.size == 0:
        return np.asarray([], dtype=np.float32)
    shifted = scores - scores.max()
    exp_values = np.exp(shifted)
    total = exp_values.sum()
    if total <= 0.0:
        return np.full_like(exp_values, 1.0 / float(len(exp_values)))
    return exp_values / total


def _classify_nodes(nodes: Sequence[LineNode]) -> Dict[str, int]:
    """Nadaje węzłom klasyfikację zgodną z definicjami essential/non-essential."""

    stats = {
        "essential": 0,
        "non_essential": 0,
        "endpoints": 0,
        "isolated": 0,
    }

    for node in nodes:
        degree = len(node.attached_segments)
        if degree >= 3:
            node.classification = "essential"
            stats["essential"] += 1
        elif degree == 2:
            node.classification = "non_essential"
            stats["non_essential"] += 1
        elif degree == 1:
            node.classification = "endpoint"
            stats["endpoints"] += 1
        else:
            node.classification = "isolated"
            stats["isolated"] += 1

    stats.setdefault("endpoint", stats.get("endpoints", 0))

    return stats


def _segment_confidence(
    segment: LineSegment,
    start_node: LineNode | None,
    end_node: LineNode | None,
    *,
    min_edge_length: float,
) -> Tuple[float, Dict[str, Any]]:
    length = float(segment.length)
    reference = max(1.0, float(min_edge_length))
    length_ratio = length / reference
    score = min(1.0, max(0.0, length_ratio / 3.0))
    reasons: List[str] = []

    if length_ratio < 1.05:
        score -= 0.3
        reasons.append("short_segment")
    elif length_ratio < 1.45:
        score -= 0.15
        reasons.append("marginal_length")
    elif length_ratio > 3.5:
        score += 0.06
    elif length_ratio > 2.2:
        score += 0.03

    def _degree(node: LineNode | None) -> int:
        return len(node.attached_segments) if node else 0

    start_degree = _degree(start_node)
    end_degree = _degree(end_node)

    if start_degree >= 3:
        score += 0.08
        reasons.append("start_supported")
    elif start_degree == 2:
        score += 0.03
    elif start_degree <= 1:
        score -= 0.12
        reasons.append("start_endpoint")

    if end_degree >= 3:
        score += 0.08
        reasons.append("end_supported")
    elif end_degree == 2:
        score += 0.03
    elif end_degree <= 1:
        score -= 0.12
        reasons.append("end_endpoint")

    if start_degree <= 1 and end_degree <= 1:
        score -= 0.14
        reasons.append("isolated_branch")
    elif start_degree >= 2 and end_degree >= 2 and length_ratio >= 1.8:
        score += 0.05
        reasons.append("well_supported")

    if start_node and start_node.classification == "isolated":
        score -= 0.05
        reasons.append("start_isolated")
    if end_node and end_node.classification == "isolated":
        score -= 0.05
        reasons.append("end_isolated")

    score = max(0.0, min(score, 1.0))
    details: Dict[str, Any] = {
        "length_ratio": float(length_ratio),
        "start_degree": int(start_degree),
        "end_degree": int(end_degree),
        "reasons": sorted(set(reasons)),
    }
    return score, details


def _score_segments(
    segments: Sequence[LineSegment],
    nodes: Sequence[LineNode],
    *,
    min_edge_length: float,
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "scores": {},
        "high_confidence": [],
        "medium_confidence": [],
        "low_confidence": [],
        "flagged_segments": [],
        "statistics": {
            "average": 0.0,
            "min": 0.0,
            "max": 0.0,
        },
    }

    if not segments:
        return summary

    node_by_position: Dict[LinePoint, LineNode] = {node.position: node for node in nodes}

    total_score = 0.0
    min_score = 1.0
    max_score = 0.0

    for segment in segments:
        start_node = node_by_position.get(segment.start)
        end_node = node_by_position.get(segment.end)
        score, details = _segment_confidence(
            segment,
            start_node,
            end_node,
            min_edge_length=min_edge_length,
        )
        label = "high" if score >= 0.65 else "medium" if score >= 0.45 else "low"
        entry = {
            "score": round(score, 3),
            "label": label,
            "length": round(float(segment.length), 3),
            "length_ratio": round(float(details.get("length_ratio", 0.0)), 3),
            "start_node": start_node.id if start_node else None,
            "end_node": end_node.id if end_node else None,
            "start_classification": start_node.classification if start_node else None,
            "end_classification": end_node.classification if end_node else None,
            "start_degree": details.get("start_degree"),
            "end_degree": details.get("end_degree"),
            "reasons": details.get("reasons", []),
            "start_position": list(segment.start),
            "end_position": list(segment.end),
        }
        summary["scores"][segment.id] = entry
        summary[f"{label}_confidence"].append(segment.id)

        total_score += score
        min_score = min(min_score, score)
        max_score = max(max_score, score)

        if label == "low":
            summary["flagged_segments"].append(
                {
                    "id": segment.id,
                    "score": entry["score"],
                    "length": entry["length"],
                    "reasons": entry["reasons"],
                    "start_node": entry["start_node"],
                    "end_node": entry["end_node"],
                    "start_position": entry["start_position"],
                    "end_position": entry["end_position"],
                }
            )

    total = len(segments)
    if total > 0:
        summary["statistics"] = {
            "average": round(total_score / total, 3),
            "min": round(min_score if total > 0 else 0.0, 3),
            "max": round(max_score if total > 0 else 0.0, 3),
        }
    summary["flagged_segments"].sort(key=lambda item: item["score"])
    return summary


def _prepare_image(
    image: np.ndarray,
    *,
    binary: bool,
    config: LineDetectionConfig,
) -> np.ndarray:
    """Normalizuje obraz do skali szarości i aplikuje wstępne filtrowanie."""
    working = image
    if config.enable_color_enhancement:
        working = _enhance_lines_from_color(image, config)
    gray = _ensure_grayscale(working)
    blurred = cv2.GaussianBlur(gray, config.gaussian_kernel_size, config.gaussian_sigma)

    if binary:
        _, processed = cv2.threshold(
            blurred,
            config.binary_threshold,
            255,
            cv2.THRESH_BINARY,
        )
    elif config.use_adaptive_threshold:
        processed = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY,
            config.adaptive_block_size,
            config.adaptive_c,
        )
    else:
        processed = blurred

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, config.morph_kernel_size)
    bridged = cv2.morphologyEx(
        processed,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=max(1, config.morph_iterations),
    )
    filtered = cv2.morphologyEx(
        bridged,
        cv2.MORPH_OPEN,
        kernel,
        iterations=max(1, config.morph_iterations - 1),
    )

    if config.dotted_line_bridge_iterations > 0:
        candidates = _detect_dotted_candidates(image, config)
        if candidates is not None:
            general_mask, orientation_masks = candidates
            overlap = cv2.bitwise_and(general_mask, (filtered > 0).astype(np.uint8))
            if cv2.countNonZero(overlap) > 0:
                kernel = cv2.getStructuringElement(
                    cv2.MORPH_RECT,
                    tuple(max(1, int(size)) for size in config.dotted_line_bridge_kernel_size),
                )
                iterations = max(1, int(config.dotted_line_bridge_iterations))
                # Work on a binary mask so closing operations add or connect
                # foreground pixels deterministically. Use the skeleton
                # engine's binary threshold to decide what counts as 'line'.
                bin_thresh = int(getattr(config.skeleton_config, "binary_threshold", 127) or 127)
                binary_mask = (filtered >= bin_thresh).astype(np.uint8)

                common_closing = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, kernel, iterations=iterations)
                vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3))
                horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1))
                vertical_close = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, vertical_kernel, iterations=iterations)
                horizontal_close = cv2.morphologyEx(
                    binary_mask, cv2.MORPH_CLOSE, horizontal_kernel, iterations=iterations
                )
                # diagonal kernels (1-pixel wide along diagonal)
                diag1_kernel = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.uint8)
                diag2_kernel = np.array([[0, 0, 1], [0, 1, 0], [1, 0, 0]], dtype=np.uint8)
                diag1_close = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, diag1_kernel, iterations=iterations)
                diag2_close = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, diag2_kernel, iterations=iterations)

                # masks where closing introduced new foreground pixels
                # orientation_masks is (vertical, horizontal, diag_pos, diag_neg)
                vert_mask_src, hor_mask_src, diag_pos_src, diag_neg_src = orientation_masks
                vertical_mask = cv2.bitwise_and(vert_mask_src, (vertical_close > binary_mask).astype(np.uint8))
                horizontal_mask = cv2.bitwise_and(hor_mask_src, (horizontal_close > binary_mask).astype(np.uint8))
                diag1_mask = cv2.bitwise_and(diag_pos_src, (diag1_close > binary_mask).astype(np.uint8))
                diag2_mask = cv2.bitwise_and(diag_neg_src, (diag2_close > binary_mask).astype(np.uint8))
                common_mask = (common_closing > binary_mask).astype(np.uint8)

                # force newly-closed pixels to full-intensity so the later
                # binarization in SkeletonEngine will pick them up.
                result = filtered.copy()
                result[common_mask > 0] = 255
                result[vertical_mask > 0] = 255
                result[horizontal_mask > 0] = 255
                result[diag1_mask > 0] = 255
                result[diag2_mask > 0] = 255

                # Attempt targeted removal/filling of small round dot-like components
                # followed by endpoint-bridging. This tries to remove small
                # circular dots that break thin-line continuity and then
                # connects the nearby line endpoints.
                # For each connected component in the general dotted mask, create
                # a small ROI and check the skeleton endpoints there. If exactly
                # two endpoints appear and are reasonably close, draw a 1px
                # connecting line between them to close the gap caused by a dot.
                if config.dotted_line_bridge_enable_global_endpoint_pairing:
                    try:
                        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
                            general_mask.astype(np.uint8), connectivity=8
                        )
                    except Exception:
                        num_labels = 0
                        labels = None

                if labels is not None and num_labels > 1:
                    # Small connected components inside the binary_mask are
                    # candidates for circular 'dots'. Evaluate circularity and
                    # fill when appropriate (conservative thresholds).
                    for lbl in range(1, num_labels):
                        area = int(stats[lbl, cv2.CC_STAT_AREA])
                        if area < int(config.dotted_line_bridge_component_min_area) or area > int(
                            config.dotted_line_bridge_component_max_area
                        ):
                            continue

                        x = int(stats[lbl, cv2.CC_STAT_LEFT])
                        y = int(stats[lbl, cv2.CC_STAT_TOP])
                        w = int(stats[lbl, cv2.CC_STAT_WIDTH])
                        h = int(stats[lbl, cv2.CC_STAT_HEIGHT])

                        # Only consider roughly circular small blobs
                        roi_bin = (binary_mask[y : y + h, x : x + w] > 0).astype(np.uint8)
                        if roi_bin.sum() == 0:
                            continue
                        contours, _ = cv2.findContours(roi_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        if not contours:
                            continue
                        cnt = max(contours, key=cv2.contourArea)
                        perim = float(cv2.arcLength(cnt, True))
                        a = float(cv2.contourArea(cnt))
                        if perim <= 1.0:
                            continue
                        circularity = 4.0 * math.pi * a / (perim * perim)
                        # fill if fairly circular and compact
                        if circularity >= 0.35 and min(w, h) <= 2 + int(
                            config.dotted_line_bridge_endpoint_max_distance // 4
                        ):
                            # draw filled contour onto result (local coordinates)
                            cv2.drawContours(result[y : y + h, x : x + w], [cnt], -1, color=255, thickness=-1)

                    # Try Hough circle detection as a complementary method
                    # to find small round dots which were missed by contour heuristics.
                    # Hough-based dot-filling was removed from the conservative
                    # default pipeline to avoid false positives during tuning.
                    pad = 6
                    for lbl in range(1, num_labels):
                        area = int(stats[lbl, cv2.CC_STAT_AREA])
                        if area < int(config.dotted_line_bridge_component_min_area) or area > int(
                            config.dotted_line_bridge_component_max_area
                        ):
                            continue

                        x = int(stats[lbl, cv2.CC_STAT_LEFT])
                        y = int(stats[lbl, cv2.CC_STAT_TOP])
                        w = int(stats[lbl, cv2.CC_STAT_WIDTH])
                        h = int(stats[lbl, cv2.CC_STAT_HEIGHT])

                        x0 = max(0, x - pad)
                        y0 = max(0, y - pad)
                        x1 = min(result.shape[1], x + w + pad)
                        y1 = min(result.shape[0], y + h + pad)

                        roi_bin = (binary_mask[y0:y1, x0:x1] > 0).astype(np.uint8)
                        if roi_bin.sum() == 0:
                            continue

                        # attempt targeted morphological closing inside small ROI
                        # to bridge dot-sized gaps along the predominant orientation
                        if config.dotted_line_bridge_enable_roi_close:
                            try:
                                if area <= int(config.dotted_line_bridge_component_max_area):
                                    # decide kernel size based on ROI dimensions
                                    k = max(3, min(11, max(w, h) // 1 + 1))
                                    # orientation counts inside the current component
                                    v_count = int((vert_mask_src[y : y + h, x : x + w]).sum())
                                    h_count = int((hor_mask_src[y : y + h, x : x + w]).sum())
                                    d1_count = int((diag_pos_src[y : y + h, x : x + w]).sum())
                                    d2_count = int((diag_neg_src[y : y + h, x : x + w]).sum())
                                # select kernel shape by majority orientation
                                if h_count >= v_count and h_count >= d1_count and h_count >= d2_count:
                                    local_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min(11, k * 2 + 1), 1))
                                elif v_count > h_count and v_count >= d1_count and v_count >= d2_count:
                                    local_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min(11, k * 2 + 1)))
                                else:
                                    local_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min(11, k), min(11, k)))

                                roi_mask = (binary_mask[y : y + h, x : x + w]).astype(np.uint8)
                                closed_roi = cv2.morphologyEx(roi_mask, cv2.MORPH_CLOSE, local_kernel, iterations=1)
                                added_local = (closed_roi > roi_mask).astype(np.uint8)
                                # only apply when closing actually added a few pixels
                                if added_local.sum() > 0 and added_local.sum() <= max(400, area * 2):
                                    result[y : y + h, x : x + w][added_local > 0] = 255
                            except Exception:
                                pass

                        # Thin the ROI to get endpoints
                        roi_skel = _fast_skeletonize((roi_bin * 255).astype(np.uint8))
                        if roi_skel.max() > 0:
                            roi_skel_bin = (roi_skel > 0).astype(np.uint8)
                        else:
                            roi_skel_bin = roi_bin

                        # collect endpoints (neighbors==1)
                        ys, xs = roi_skel_bin.nonzero()
                        endpoints = []
                        for ry, rx in zip(ys, xs):
                            # count neighbors
                            neigh = roi_skel_bin[max(0, ry - 1) : ry + 2, max(0, rx - 1) : rx + 2]
                            cnt = int(neigh.sum()) - 1
                            if cnt == 1:
                                endpoints.append((x0 + rx, y0 + ry))

                        maxd = int(config.dotted_line_bridge_endpoint_max_distance)
                        best_pair = None

                        # First, try to connect real endpoints if present
                        if len(endpoints) >= 2:
                            best_dist = 0
                            for i in range(len(endpoints)):
                                for j in range(i + 1, len(endpoints)):
                                    (x1p, y1p) = endpoints[i]
                                    (x2p, y2p) = endpoints[j]
                                    d = math.hypot(x1p - x2p, y1p - y2p)
                                    if d > best_dist and d <= maxd:
                                        best_dist = d
                                        best_pair = ((int(x1p), int(y1p)), (int(x2p), int(y2p)))

                        # Fallback: connect centroids of the two largest skeleton
                        # clusters if endpoints were not found or insufficient.
                        if best_pair is None:
                            try:
                                num_c, lbls, st, cen = cv2.connectedComponentsWithStats(
                                    roi_skel_bin.astype(np.uint8), connectivity=8
                                )
                                clusters = []
                                for ci in range(1, num_c):
                                    area_c = int(st[ci, cv2.CC_STAT_AREA])
                                    if area_c <= 0:
                                        continue
                                    cx = int(cen[ci, 0]) + x0
                                    cy = int(cen[ci, 1]) + y0
                                    clusters.append(((cx, cy), area_c))
                                if len(clusters) >= 2:
                                    clusters.sort(key=lambda x: x[1], reverse=True)
                                    (c1, _), (c2, _) = clusters[0], clusters[1]
                                    d = math.hypot(c1[0] - c2[0], c1[1] - c2[1])
                                    if d <= maxd:
                                        best_pair = (c1, c2)
                            except Exception:
                                pass

                        if best_pair is None:
                            continue

                        # Draw the connecting line on result
                        cv2.line(result, best_pair[0], best_pair[1], color=255, thickness=1)

                        # Directional scan: try to find foreground pixels on
                        # opposing sides of the component center and connect them.
                        try:
                            cx = x + w // 2
                            cy = y + h // 2
                            max_gap = int(config.dotted_line_bridge_endpoint_max_distance)
                            directions = [(1, 0), (0, 1), (1, 1), (1, -1), (-1, 0), (0, -1), (-1, -1), (-1, 1)]
                            for dx, dy in directions:
                                pos = None
                                neg = None
                                for step in range(1, max_gap + 1):
                                    sx = cx + dx * step
                                    sy = cy + dy * step
                                    if 0 <= sx < result.shape[1] and 0 <= sy < result.shape[0]:
                                        if binary_mask[sy, sx] > 0:
                                            pos = (sx, sy)
                                            break
                                for step in range(1, max_gap + 1):
                                    sx = cx - dx * step
                                    sy = cy - dy * step
                                    if 0 <= sx < result.shape[1] and 0 <= sy < result.shape[0]:
                                        if binary_mask[sy, sx] > 0:
                                            neg = (sx, sy)
                                            break
                                if pos and neg:
                                    d = math.hypot(pos[0] - neg[0], pos[1] - neg[1])
                                    if d <= max_gap:
                                        cv2.line(result, pos, neg, color=255, thickness=1)
                                        break
                        except Exception:
                            pass

                # Global endpoint pairing across small gaps that intersect dotted
                # candidate regions: find skeleton endpoints and connect nearby
                # pairs when the connecting line passes through the dotted mask.
                try:
                    sk_global = _fast_skeletonize((binary_mask * 255).astype(np.uint8))
                    if sk_global.max() > 0:
                        sk_bin = (sk_global > 0).astype(np.uint8)
                        ys, xs = sk_bin.nonzero()
                        endpoints = []
                        for ry, rx in zip(ys, xs):
                            neigh = sk_bin[max(0, ry - 1) : ry + 2, max(0, rx - 1) : rx + 2]
                            cnt = int(neigh.sum()) - 1
                            if cnt == 1:
                                endpoints.append((rx, ry))

                        # naive O(N^2) search — endpoints count is usually small
                        maxd = int(config.dotted_line_bridge_endpoint_max_distance)
                        for i in range(len(endpoints)):
                            for j in range(i + 1, len(endpoints)):
                                x1p, y1p = endpoints[i]
                                x2p, y2p = endpoints[j]
                                d = math.hypot(x1p - x2p, y1p - y2p)
                                if d <= maxd and d >= 1.0:
                                    # sample along the segment and count how many points
                                    # overlay the dotted general_mask
                                    n_samples = max(3, int(d))
                                    xsamps = np.linspace(x1p, x2p, n_samples).astype(int)
                                    ysamps = np.linspace(y1p, y2p, n_samples).astype(int)
                                    hit = 0
                                    for sx, sy in zip(xsamps, ysamps):
                                        if 0 <= sy < general_mask.shape[0] and 0 <= sx < general_mask.shape[1]:
                                            if general_mask[sy, sx] > 0:
                                                hit += 1
                                    if hit / float(n_samples) >= 0.5:
                                        cv2.line(
                                            result, (int(x1p), int(y1p)), (int(x2p), int(y2p)), color=255, thickness=1
                                        )
                except Exception:
                    pass

                filtered = result

    return filtered


def _ensure_grayscale(image: np.ndarray) -> np.ndarray:
    """Zwraca obraz w skali szarości niezależnie od formatu wejściowego."""

    if len(image.shape) == 2:
        return image

    if len(image.shape) == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    raise ValueError("Unsupported image shape for line detection")


def _fast_skeletonize(image: np.ndarray) -> np.ndarray:
    """Cienkowanie obrazu binarnego."""

    # cv2.ximgproc.thinning daje lepszy efekt, ale jest dostępne tylko w module contrib.
    if hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "thinning"):
        return cv2.ximgproc.thinning(image)

    # Fallback do skimage jeżeli dostępne.
    try:
        import importlib

        morph_module = importlib.import_module("skimage.morphology")
        skeletonize = getattr(morph_module, "skeletonize", None)
        if skeletonize is None:
            return image
        normalized = (image > 0).astype(np.uint8)
        skeleton = skeletonize(normalized).astype(np.uint8) * 255
        return skeleton
    except ImportError:
        return _morphological_skeletonize(image)


def _morphological_skeletonize(image: np.ndarray) -> np.ndarray:
    """Zapasowa implementacja skeletonizacji bazująca na operacjach morfologicznych."""
    if image.ndim != 2:
        raise ValueError("Skeletonizacja wymaga obrazu 2D")

    working = image if image.dtype == np.uint8 else image.astype(np.uint8)
    _, binary = cv2.threshold(working, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    skeleton = np.zeros_like(binary)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))

    while True:
        eroded = cv2.erode(binary, element)
        temp = cv2.dilate(eroded, element)
        temp = cv2.subtract(binary, temp)
        skeleton = cv2.bitwise_or(skeleton, temp)
        if cv2.countNonZero(eroded) == 0:
            break
        binary = eroded

    return skeleton


def _graph_repair_skeleton(
    skeleton_mask: np.ndarray,
    binary_mask: np.ndarray,
    general_mask: np.ndarray | None,
    config: LineDetectionConfig,
) -> np.ndarray:
    """Repair skeleton by connecting endpoint node pairs in a graph-aware way.

    Strategy:
    - Build graph from current skeleton
    - Find endpoint nodes (degree == 1)
    - For each endpoint pair within a distance threshold, check
      colinearity (angle threshold) and whether the line between them
      overlaps the dotted-candidate mask (general_mask) sufficiently.
    - Draw 1px connecting line on skeleton_mask for accepted pairs.

    Returns a modified skeleton_mask copy (uint8 0/1).
    """
    if skeleton_mask is None or skeleton_mask.size == 0:
        return skeleton_mask

    repair_enabled = getattr(config, "dotted_line_graph_repair_enable", False)
    if not repair_enabled:
        return skeleton_mask

    if general_mask is None:
        # If no dotted mask, nothing to base repairs on
        return skeleton_mask

    working = skeleton_mask.copy().astype(np.uint8)

    # get segments & nodes from current skeleton
    segments, nodes = _build_graph_from_skeleton(
        working,
        min_edge_length=max(1.0, config.min_edge_length),
        node_merge_tolerance=max(1.0, config.node_merge_tolerance),
    )
    if not nodes:
        return working

    # early bailout: if the skeleton graph has too many nodes, skip graph-repair
    max_nodes_allowed = int(getattr(config, "dotted_line_graph_repair_max_nodes", 0))
    if max_nodes_allowed and len(nodes) > max_nodes_allowed:
        # too complex to safely perform O(N^2) endpoint pairing; abort repair
        return working

    seg_by_id = {s.id: s for s in segments}

    # find endpoints
    endpoints = [node for node in nodes if len(node.attached_segments) == 1]
    if len(endpoints) < 2:
        return working

    maxd = float(config.dotted_line_bridge_endpoint_max_distance)
    angle_thresh = float(config.dotted_line_graph_repair_angle_threshold)
    overlap_frac = float(config.dotted_line_graph_repair_overlap_fraction)
    max_joins = int(getattr(config, "dotted_line_graph_repair_max_joins_per_image", 200))

    joins = 0

    # prepare quick lookup for segment direction for each endpoint node
    def endpoint_direction(node: LineNode) -> Tuple[float, float] | None:
        if not node.attached_segments:
            return None
        seg_id = node.attached_segments[0]
        seg = seg_by_id.get(seg_id)
        if not seg:
            return None
        sx, sy = seg.start
        ex, ey = seg.end
        # node.position is (x,y)
        nx, ny = node.position
        # choose vector that points *out* of the node
        if (nx, ny) == (sx, sy):
            vx, vy = ex - sx, ey - sy
        else:
            vx, vy = sx - ex, sy - ey
        norm = math.hypot(vx, vy)
        if norm <= 0.0:
            return None
        return (vx / norm, vy / norm)

    # convert general_mask to boolean for faster operations
    gen_mask_bool = (general_mask > 0).astype(np.uint8)

    # iterate pairs (naive O(N^2) - endpoints normally small)
    for i in range(len(endpoints)):
        if joins >= max_joins:
            break
        a = endpoints[i]
        ax, ay = a.position
        dir_a = endpoint_direction(a)
        if dir_a is None:
            continue
        for j in range(i + 1, len(endpoints)):
            b = endpoints[j]
            bx, by = b.position
            # already same coord guard
            if ax == bx and ay == by:
                continue

            d = math.hypot(ax - bx, ay - by)
            if d > maxd or d < 1.0:
                continue

            dir_b = endpoint_direction(b)
            if dir_b is None:
                continue

            # angle between endpoint direction and the connecting vector
            vec_x, vec_y = bx - ax, by - ay
            vec_norm = math.hypot(vec_x, vec_y)
            if vec_norm == 0:
                continue
            vxn, vyn = vec_x / vec_norm, vec_y / vec_norm

            def angle_diff_deg(v1: Tuple[float, float], v2: Tuple[float, float]) -> float:
                a1 = math.degrees(math.atan2(v1[1], v1[0])) % 360.0
                a2 = math.degrees(math.atan2(v2[1], v2[0])) % 360.0
                diff = abs((a1 - a2 + 180.0) % 360.0 - 180.0)
                return diff

            # endpoints should roughly face each other: dir_a aligns with vec
            diff_a = angle_diff_deg(dir_a, (vxn, vyn))
            # dir_b should align with reversed vector
            diff_b = angle_diff_deg(dir_b, (-vxn, -vyn))
            if diff_a > angle_thresh or diff_b > angle_thresh:
                continue

            # sample along segment and require overlap with dotted mask
            n_samples = max(3, int(d))
            xsamps = np.linspace(ax, bx, n_samples).astype(int)
            ysamps = np.linspace(ay, by, n_samples).astype(int)
            hits = 0
            valid = 0
            for sx, sy in zip(xsamps, ysamps):
                if 0 <= sy < gen_mask_bool.shape[0] and 0 <= sx < gen_mask_bool.shape[1]:
                    valid += 1
                    if gen_mask_bool[sy, sx] > 0:
                        hits += 1
            if valid == 0:
                continue
            if (float(hits) / float(valid)) < overlap_frac:
                continue

            # Ok - accept join. Draw a 1px line on working skeleton mask
            cv2.line(working, (int(ax), int(ay)), (int(bx), int(by)), color=1, thickness=1)
            joins += 1
            if joins >= max_joins:
                break

    return working


def _save_debug_images(
    directory: Path,
    prefix: str,
    images: Dict[str, np.ndarray],
) -> List[Path]:
    """Zapisuje debugowe wersje obrazów i zwraca listę ścieżek."""

    directory.mkdir(parents=True, exist_ok=True)
    saved_paths: List[Path] = []

    for key, img in images.items():
        path = directory / f"{prefix}-{key}.png"
        cv2.imwrite(str(path), img)
        saved_paths.append(path)

    return saved_paths


def _config_to_metadata(config: LineDetectionConfig) -> Dict[str, Any]:
    """Przekształca konfigurację w formę serializowalną do JSON."""

    metadata: Dict[str, Any] = {}
    for field_info in dataclass_fields(config):
        key = field_info.name
        value = getattr(config, key)
        if isinstance(value, Path):
            metadata[key] = str(value)
        elif isinstance(value, tuple):
            metadata[key] = list(value)
        elif is_dataclass(value):
            metadata[key] = asdict(value)
        else:
            metadata[key] = value
    return metadata


def line_detection_result_from_dict(payload: Dict[str, Any]) -> LineDetectionResult:
    """Odtwarza wynik segmentacji linii z serializowanej struktury."""

    segments: List[LineSegment] = []
    for item in payload.get("lines", []):
        if not isinstance(item, dict):
            continue
        try:
            start = _coerce_point(item.get("start"))
            end = _coerce_point(item.get("end"))
        except ValueError:
            continue
        seg_id = str(item.get("id", f"edge-{len(segments)}"))
        length_value = item.get("length")
        try:
            length = float(length_value) if length_value is not None else _point_distance(start, end)
        except (TypeError, ValueError):
            length = _point_distance(start, end)
        angle_value = item.get("angle_deg")
        try:
            angle = float(angle_value) if angle_value is not None else 0.0
        except (TypeError, ValueError):
            angle = 0.0
        confidence_value = item.get("confidence")
        try:
            confidence = float(confidence_value) if confidence_value is not None else 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        label_value = item.get("confidence_label")
        confidence_label = label_value if isinstance(label_value, str) else "unknown"
        segments.append(
            LineSegment(
                id=seg_id,
                start=start,
                end=end,
                length=length,
                angle_deg=angle,
                confidence=confidence,
                confidence_label=confidence_label,
            )
        )

    nodes: List[LineNode] = []
    for item in payload.get("nodes", []):
        if not isinstance(item, dict):
            continue
        try:
            position = _coerce_point(item.get("position"))
        except ValueError:
            continue
        node_id = str(item.get("id", f"node-{len(nodes)}"))
        attached = item.get("attached_segments")
        if isinstance(attached, list):
            attached_segments = [str(seg) for seg in attached if isinstance(seg, (str, int))]
        else:
            attached_segments = []
        classification = item.get("classification", "unspecified")
        junction_state = item.get("junction_state") or item.get("junctionState", "unspecified")
        junction_label = item.get("junction_label") or item.get("junctionLabel", "unknown")
        confidence_value = item.get("junction_confidence") or item.get("junctionConfidence")
        try:
            junction_confidence = float(confidence_value) if confidence_value is not None else 0.0
        except (TypeError, ValueError):
            junction_confidence = 0.0
        nodes.append(
            LineNode(
                id=node_id,
                position=position,
                attached_segments=attached_segments,
                classification=str(classification),
                junction_state=str(junction_state),
                junction_label=str(junction_label),
                junction_confidence=junction_confidence,
            )
        )

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    debug_values = payload.get("debug_artifacts") or payload.get("debugArtifacts") or []
    debug_artifacts: List[Path] = []
    for value in debug_values:
        if isinstance(value, str) and value:
            debug_artifacts.append(Path(value))

    return LineDetectionResult(
        lines=segments,
        nodes=nodes,
        metadata=dict(metadata),
        debug_artifacts=debug_artifacts,
    )


def _coerce_point(value: Any) -> LinePoint:
    if isinstance(value, dict):
        x = value.get("x")
        y = value.get("y")
        if x is not None and y is not None:
            try:
                return int(round(float(x))), int(round(float(y)))
            except (TypeError, ValueError):
                pass
    if isinstance(value, Sequence) and len(value) == 2:
        try:
            x_val = int(round(float(value[0])))
            y_val = int(round(float(value[1])))
            return x_val, y_val
        except (TypeError, ValueError):
            pass
    raise ValueError("Unsupported point representation")
