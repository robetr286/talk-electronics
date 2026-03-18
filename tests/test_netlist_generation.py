from __future__ import annotations

import cv2
import numpy as np

from talk_electronic.services.line_detection import (
    LineDetectionConfig,
    LineDetectionResult,
    LineNode,
    LineSegment,
    detect_lines,
    line_detection_result_from_dict,
)
from talk_electronic.services.netlist import generate_netlist
from talk_electronic.services.skeleton import SkeletonConfig


def _draw_cross_image(size: int = 160, thickness: int = 5) -> np.ndarray:
    image = np.zeros((size, size), dtype=np.uint8)
    center = size // 2
    cv2.line(image, (20, center), (size - 20, center), 255, thickness)
    cv2.line(image, (center, 20), (center, size - 20), 255, thickness)
    return image


def test_generate_netlist_from_cross_shape():
    image = _draw_cross_image()
    cfg = LineDetectionConfig(
        gaussian_kernel_size=(3, 3),
        gaussian_sigma=0.0,
        morph_iterations=0,
        skeleton_config=SkeletonConfig(prune_short_branches=2),
        min_edge_length=12.0,
    )

    detection = detect_lines(image, binary=False, config=cfg)
    netlist = generate_netlist(detection)

    assert len(netlist.nodes) == len(detection.nodes)
    assert len(netlist.edges) == len(detection.lines)
    assert netlist.metadata["node_count"] == len(detection.nodes)
    assert netlist.metadata["edge_count"] == len(detection.lines)
    assert netlist.metadata["skipped_segments"] == []
    assert len(netlist.metadata["components"]) == 1
    assert netlist.metadata["components"][0]["id"] == netlist.nodes[0].net_label

    components = netlist.metadata["connected_components"]
    assert len(components) == 1
    assert set(components[0]) == {node.id for node in detection.nodes}
    assert len(netlist.metadata["netlist"]) == len(detection.lines)
    assert all(entry.startswith("WIRE ") for entry in netlist.metadata["netlist"])

    # Central node should have degree >= 4 for the cross shape.
    central = max(netlist.nodes, key=lambda item: item.degree)
    assert central.degree >= 4
    assert len(central.neighbors) >= 4
    assert central.classification == "essential"
    assert central.is_essential is True
    assert central.net_label.startswith("NET")
    classification_counts = netlist.metadata.get("node_classification", {})
    assert classification_counts.get("essential") == 1
    assert classification_counts.get("endpoint") == 4 or classification_counts.get("endpoints") == 4
    essential_labels = netlist.metadata.get("essential_node_labels", [])
    assert isinstance(essential_labels, list)
    assert len(essential_labels) == 1
    assert central.label in essential_labels
    degree_histogram = netlist.metadata.get("degree_histogram")
    assert isinstance(degree_histogram, dict)
    assert sum(degree_histogram.values()) == netlist.metadata["node_count"]
    assert max(degree_histogram) >= central.degree
    assert degree_histogram.get(1, 0) >= 4


def test_generate_netlist_handles_missing_nodes():
    detection = LineDetectionResult(
        lines=[
            LineSegment(
                id="edge-orphan",
                start=(0, 0),
                end=(10, 0),
                length=10.0,
                angle_deg=0.0,
            )
        ],
        nodes=[
            LineNode(id="node-0", position=(0, 0), attached_segments=[]),
        ],
    )

    netlist = generate_netlist(detection)

    assert netlist.metadata["node_count"] == 1
    assert netlist.metadata["edge_count"] == 0
    assert netlist.metadata["skipped_segments"] == ["edge-orphan"]
    assert netlist.metadata["netlist"] == []
    assert netlist.edges == []
    assert len(netlist.nodes) == 1
    assert netlist.nodes[0].classification == "isolated"
    assert netlist.metadata.get("node_classification", {}).get("isolated") == 1
    assert netlist.nodes[0].net_label == "NET001"
    assert netlist.metadata.get("degree_histogram", {}).get(0) == 1


def test_line_detection_result_roundtrip():
    image = _draw_cross_image()
    cfg = LineDetectionConfig(
        gaussian_kernel_size=(3, 3),
        gaussian_sigma=0.0,
        morph_iterations=0,
        skeleton_config=SkeletonConfig(prune_short_branches=2),
        min_edge_length=12.0,
    )

    detection = detect_lines(image, binary=False, config=cfg)
    payload = detection.to_dict()
    hydrated = line_detection_result_from_dict(payload)

    assert len(hydrated.lines) == len(detection.lines)
    assert len(hydrated.nodes) == len(detection.nodes)
    assert hydrated.metadata["merged_segments"] == detection.metadata["merged_segments"]


def test_netlist_endpoint_accepts_serialized_lines(client):
    image = _draw_cross_image()
    cfg = LineDetectionConfig(
        gaussian_kernel_size=(3, 3),
        gaussian_sigma=0.0,
        morph_iterations=0,
        skeleton_config=SkeletonConfig(prune_short_branches=2),
        min_edge_length=12.0,
    )

    detection = detect_lines(image, binary=False, config=cfg)
    response = client.post(
        "/api/segment/netlist",
        json={
            "lines": detection.to_dict(),
            "storeHistory": True,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert "netlist" in payload

    netlist = payload["netlist"]
    assert netlist["metadata"]["edge_count"] == len(detection.lines)
    assert len(netlist["metadata"]["netlist"]) == len(detection.lines)

    history_entry = payload.get("historyEntry")
    assert history_entry is not None
    assert history_entry["type"] == "netlist"


def test_netlist_endpoint_attaches_symbol_metadata(client):
    image = _draw_cross_image()
    cfg = LineDetectionConfig(
        gaussian_kernel_size=(3, 3),
        gaussian_sigma=0.0,
        morph_iterations=0,
        skeleton_config=SkeletonConfig(prune_short_branches=2),
        min_edge_length=12.0,
    )

    detection = detect_lines(image, binary=False, config=cfg)
    symbols_payload = {
        "detector": {"name": "yolov8", "version": "seg-train6"},
        "count": 1,
        "detections": [
            {
                "id": "res-0001",
                "label": "resistor",
                "score": 0.91,
                "bbox": [10.0, 12.0, 24.0, 10.0],
                "box": {"x": 10.0, "y": 12.0, "width": 24.0, "height": 10.0},
            }
        ],
        "summary": {"latencyMs": 8.4},
    }

    response = client.post(
        "/api/segment/netlist",
        json={
            "lines": detection.to_dict(),
            "symbols": symbols_payload,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    symbols_meta = payload["netlist"]["metadata"].get("symbols")
    assert symbols_meta is not None
    assert symbols_meta["count"] == 1
    assert symbols_meta["detector"]["name"] == "yolov8"
    assert len(symbols_meta["detections"]) == 1
    assert symbols_meta["detections"][0]["label"] == "resistor"


def test_netlist_endpoint_includes_edge_connectors(app, client):
    image = _draw_cross_image()
    cfg = LineDetectionConfig(
        gaussian_kernel_size=(3, 3),
        gaussian_sigma=0.0,
        morph_iterations=0,
        skeleton_config=SkeletonConfig(prune_short_branches=2),
        min_edge_length=12.0,
    )

    detection = detect_lines(image, binary=False, config=cfg)

    store = app.extensions["edge_connector_store"]
    history_id = "hist-edge-001"
    entry_id = "edge-test-001"
    payload = {
        "id": entry_id,
        "edgeId": "A01",
        "page": "2",
        "label": "Wejście sekcji B",
        "netName": "VCC_B",
        "sheetId": "sheet-02",
        "historyId": history_id,
        "geometry": {
            "type": "rect",
            "points": [[0, 0], [12, 0], [12, 4], [0, 4]],
        },
    }
    json_path = store.save_payload(entry_id, payload)
    relative = json_path.relative_to(app.config["UPLOAD_FOLDER"]).as_posix()
    store.upsert_entry(
        {
            "id": entry_id,
            "edgeId": payload["edgeId"],
            "page": payload["page"],
            "label": payload["label"],
            "netName": payload["netName"],
            "sheetId": payload["sheetId"],
            "historyId": history_id,
            "source": payload.get("source", {}),
            "metadata": payload.get("metadata", {}),
            "createdAt": "2025-01-01T12:00:00Z",
            "updatedAt": "2025-01-01T12:00:00Z",
            "storage": {"json": relative},
        }
    )

    response = client.post(
        "/api/segment/netlist",
        json={
            "lines": detection.to_dict(),
            "edgeConnectorHistoryId": history_id,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    connectors = payload["netlist"]["metadata"].get("edgeConnectors")
    assert connectors is not None
    assert connectors["count"] == 1
    assert connectors.get("historyId") == history_id
    assert connectors["items"][0]["edgeId"] == "A01"
    assert connectors["items"][0]["page"] == "2"


def test_generate_netlist_multiple_components():
    nodes = [
        LineNode(id="node-0", position=(0, 0), attached_segments=["edge-0"], classification="endpoint"),
        LineNode(id="node-1", position=(40, 0), attached_segments=["edge-0"], classification="endpoint"),
        LineNode(id="node-2", position=(0, 40), attached_segments=["edge-1"], classification="endpoint"),
        LineNode(id="node-3", position=(40, 40), attached_segments=["edge-1"], classification="endpoint"),
    ]
    lines = [
        LineSegment(id="edge-0", start=(0, 0), end=(40, 0), length=40.0, angle_deg=0.0),
        LineSegment(id="edge-1", start=(0, 40), end=(40, 40), length=40.0, angle_deg=0.0),
    ]
    detection = LineDetectionResult(lines=lines, nodes=nodes, metadata={})

    netlist = generate_netlist(detection)

    assert netlist.metadata["node_count"] == 4
    assert netlist.metadata["edge_count"] == 2
    assert len(netlist.metadata["components"]) == 2
    component_ids = [entry["id"] for entry in netlist.metadata["components"]]
    assert component_ids == sorted(component_ids)

    net_labels = {node.id: node.net_label for node in netlist.nodes}
    assert len(set(net_labels.values())) == 2

    for entry in netlist.metadata["components"]:
        assert entry["size"] == 2
        labels = entry["node_labels"]
        assert all(label.startswith("N") for label in labels)

    neighbor_counts = {node.id: len(node.neighbors) for node in netlist.nodes}
    assert neighbor_counts["node-0"] == 1
    assert neighbor_counts["node-2"] == 1
    assert net_labels["node-0"] != net_labels["node-2"]
    degree_histogram = netlist.metadata.get("degree_histogram")
    assert degree_histogram == {1: 4}
