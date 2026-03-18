from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import networkx as nx

from .line_detection import LineDetectionResult


@dataclass(slots=True)
class NetlistNode:
    """Simplified logical node derived from skeleton graph."""

    id: str
    label: str
    position: Tuple[int, int]
    degree: int
    attached_segments: List[str] = field(default_factory=list)
    neighbors: List[str] = field(default_factory=list)
    classification: str = "unspecified"
    is_essential: bool = False
    net_label: str = ""


@dataclass(slots=True)
class NetlistEdge:
    """Edge between two logical nodes, treated as a wire segment."""

    id: str
    source: str
    target: str
    length: float
    angle_deg: float


@dataclass(slots=True)
class NetlistResult:
    """Structured representation of wiring connectivity."""

    nodes: List[NetlistNode]
    edges: List[NetlistEdge]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "position": node.position,
                    "degree": node.degree,
                    "attached_segments": list(node.attached_segments),
                    "neighbors": list(node.neighbors),
                    "classification": node.classification,
                    "is_essential": node.is_essential,
                    "net_label": node.net_label,
                }
                for node in self.nodes
            ],
            "edges": [
                {
                    "id": edge.id,
                    "source": edge.source,
                    "target": edge.target,
                    "length": edge.length,
                    "angle_deg": edge.angle_deg,
                }
                for edge in self.edges
            ],
            "metadata": self.metadata,
        }


def netlist_result_from_dict(payload: Dict[str, Any]) -> NetlistResult:
    """Hydrate a ``NetlistResult`` from a serialized dictionary."""

    if not isinstance(payload, dict):  # pragma: no cover - defensive
        raise TypeError("Netlist payload must be a dictionary")

    nodes: List[NetlistNode] = []
    for node_payload in payload.get("nodes", []) or []:
        if not isinstance(node_payload, dict):  # pragma: no cover - guard rail
            continue
        raw_position = node_payload.get("position")
        if isinstance(raw_position, (list, tuple)) and len(raw_position) >= 2:
            try:
                position = (int(raw_position[0]), int(raw_position[1]))
            except (TypeError, ValueError):  # pragma: no cover - guard rail
                position = (0, 0)
        else:
            position = (0, 0)

        nodes.append(
            NetlistNode(
                id=str(node_payload.get("id", "")),
                label=str(node_payload.get("label", "")),
                position=position,
                degree=int(node_payload.get("degree", 0) or 0),
                attached_segments=[str(segment) for segment in (node_payload.get("attached_segments", []) or [])],
                neighbors=[str(neighbor) for neighbor in (node_payload.get("neighbors", []) or [])],
                classification=str(node_payload.get("classification", "unspecified") or "unspecified"),
                is_essential=bool(node_payload.get("is_essential", False)),
                net_label=str(node_payload.get("net_label", "")),
            )
        )

    edges: List[NetlistEdge] = []
    for edge_payload in payload.get("edges", []) or []:
        if not isinstance(edge_payload, dict):  # pragma: no cover - guard rail
            continue
        edges.append(
            NetlistEdge(
                id=str(edge_payload.get("id", "")),
                source=str(edge_payload.get("source", "")),
                target=str(edge_payload.get("target", "")),
                length=float(edge_payload.get("length", 0.0) or 0.0),
                angle_deg=float(edge_payload.get("angle_deg", 0.0) or 0.0),
            )
        )

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    return NetlistResult(nodes=nodes, edges=edges, metadata=metadata)


def generate_netlist(result: LineDetectionResult) -> NetlistResult:
    """Convert line detection output into a graph-backed netlist."""

    graph = nx.Graph()
    segment_to_nodes: Dict[str, List[str]] = {}
    node_segments: Dict[str, List[str]] = {}
    node_classification: Dict[str, str] = {}

    for node in result.nodes:
        graph.add_node(node.id, position=node.position)
        node_segments[node.id] = sorted(node.attached_segments)
        classification_value = getattr(node, "classification", "unspecified") or "unspecified"
        if classification_value == "unspecified":
            degree = len(node.attached_segments)
            if degree >= 3:
                classification_value = "essential"
            elif degree == 2:
                classification_value = "non_essential"
            elif degree == 1:
                classification_value = "endpoint"
            elif degree == 0:
                classification_value = "isolated"
        node_classification[node.id] = classification_value
        for segment_id in node.attached_segments:
            segment_to_nodes.setdefault(segment_id, []).append(node.id)

    edges: List[NetlistEdge] = []
    skipped_segments: List[str] = []

    for segment in result.lines:
        node_ids = segment_to_nodes.get(segment.id, [])
        if len(node_ids) != 2:
            skipped_segments.append(segment.id)
            continue
        source_id, target_id = node_ids
        graph.add_edge(
            source_id,
            target_id,
            segment_id=segment.id,
            length=segment.length,
            angle_deg=segment.angle_deg,
        )
        edges.append(
            NetlistEdge(
                id=segment.id,
                source=source_id,
                target=target_id,
                length=segment.length,
                angle_deg=segment.angle_deg,
            )
        )

    def _node_sort_key(node_id: str) -> Tuple[int, str]:
        parts = node_id.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return int(parts[1]), node_id
        return float("inf"), node_id

    ordered_node_ids = sorted(graph.nodes, key=_node_sort_key)
    nodes: List[NetlistNode] = []
    node_label_map: Dict[str, str] = {}
    for index, node_id in enumerate(ordered_node_ids):
        label = f"N{index + 1:03d}"
        node_label_map[node_id] = label

    component_entries: List[Dict[str, Any]] = []
    node_component: Dict[str, str] = {}
    for comp_index, component in enumerate(
        sorted(nx.connected_components(graph), key=lambda comp: sorted(comp, key=_node_sort_key))
    ):
        ordered_ids = sorted(component, key=_node_sort_key)
        component_label = f"NET{comp_index + 1:03d}"
        for node_id in ordered_ids:
            node_component[node_id] = component_label
        component_entries.append(
            {
                "id": component_label,
                "node_ids": ordered_ids,
                "node_labels": [node_label_map[node_id] for node_id in ordered_ids],
                "size": len(ordered_ids),
            }
        )

    for node_id in ordered_node_ids:
        label = node_label_map[node_id]
        position = graph.nodes[node_id].get("position", (0, 0))
        degree = graph.degree[node_id]
        neighbor_ids = sorted(graph.neighbors(node_id), key=_node_sort_key)
        segments = node_segments.get(node_id, [])
        classification = node_classification.get(node_id, "unspecified")
        is_essential = classification == "essential"
        nodes.append(
            NetlistNode(
                id=node_id,
                label=label,
                position=position,
                degree=degree,
                attached_segments=list(segments),
                neighbors=neighbor_ids,
                classification=classification,
                is_essential=is_essential,
                net_label=node_component.get(node_id, ""),
            )
        )

    connected_components = [entry["node_ids"] for entry in component_entries]
    cycles = [sorted(cycle, key=_node_sort_key) for cycle in nx.cycle_basis(graph)]

    classification_counts: Dict[str, int] = {
        "essential": 0,
        "non_essential": 0,
        "endpoint": 0,
        "isolated": 0,
    }
    classification_labels: Dict[str, List[str]] = {
        "essential": [],
        "non_essential": [],
        "endpoint": [],
        "isolated": [],
        "unspecified": [],
    }

    for node in nodes:
        classification = node.classification or "unspecified"
        if classification not in classification_counts:
            classification_counts[classification] = 0
        classification_counts[classification] += 1
        classification_labels.setdefault(classification, []).append(node.label)

    classification_counts.setdefault("endpoints", classification_counts.get("endpoint", 0))
    classification_labels.setdefault("endpoints", list(classification_labels.get("endpoint", [])))

    degree_histogram = Counter(node.degree for node in nodes)
    metadata: Dict[str, Any] = {
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "connected_components": connected_components,
        "cycles": cycles,
        "skipped_segments": skipped_segments,
        "node_labels": node_label_map,
        "net_labels": {node_id: entry["id"] for entry in component_entries for node_id in entry["node_ids"]},
        "node_classification": classification_counts,
        "node_classification_labels": classification_labels,
        "essential_node_labels": classification_labels.get("essential", []),
        "non_essential_node_labels": classification_labels.get("non_essential", []),
        "endpoint_node_labels": classification_labels.get("endpoint", []),
        "isolated_node_labels": classification_labels.get("isolated", []),
        "components": component_entries,
        "degree_histogram": dict(sorted(degree_histogram.items())),
    }

    netlist_lines = [
        "WIRE {edge_id} {source} {target} LEN={length:.2f} ANG={angle:.1f}".format(
            edge_id=edge.id,
            source=node_label_map[edge.source],
            target=node_label_map[edge.target],
            length=edge.length,
            angle=edge.angle_deg,
        )
        for edge in edges
    ]
    metadata["netlist"] = netlist_lines

    return NetlistResult(nodes=nodes, edges=edges, metadata=metadata)
