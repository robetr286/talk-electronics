from __future__ import annotations

import pytest

from talk_electronic.services.netlist import NetlistEdge, NetlistNode, NetlistResult, netlist_result_from_dict
from talk_electronic.services.netlist_export import (
    ComponentInstance,
    SpiceValidationResult,
    generate_spice_netlist,
    parse_component_instances,
    validate_spice_components,
)


@pytest.fixture()
def simple_netlist() -> NetlistResult:
    nodes = [
        NetlistNode(
            id="node-0",
            label="N001",
            position=(0, 0),
            degree=1,
            attached_segments=["edge-0"],
            neighbors=["node-1"],
            classification="endpoint",
            is_essential=False,
            net_label="NET001",
        ),
        NetlistNode(
            id="node-1",
            label="N002",
            position=(10, 0),
            degree=1,
            attached_segments=["edge-0"],
            neighbors=["node-0"],
            classification="endpoint",
            is_essential=False,
            net_label="NET002",
        ),
    ]
    edges = [
        NetlistEdge(id="edge-0", source="node-0", target="node-1", length=10.0, angle_deg=0.0),
    ]
    metadata = {
        "node_labels": {"node-0": "N001", "node-1": "N002"},
        "net_labels": {"node-0": "NET001", "node-1": "NET002"},
    }
    return NetlistResult(nodes=nodes, edges=edges, metadata=metadata)


def test_generate_spice_netlist_writes_components(simple_netlist: NetlistResult) -> None:
    components = [
        ComponentInstance(kind="resistor", nodes=["NET001", "NET002"], value="1k"),
        ComponentInstance(kind="capacitor", nodes=["NET002", "ground"], value="10u"),
    ]

    netlist_text = generate_spice_netlist(simple_netlist, components, title="Demo RC")
    lines = netlist_text.strip().splitlines()

    assert lines[0] == "* Demo RC"
    assert "R1 NET001 NET002 1k" in lines
    assert "C1 NET002 0 10u" in lines
    assert lines[-1] == ".end"


def test_generate_spice_netlist_unknown_node(simple_netlist: NetlistResult) -> None:
    components = [ComponentInstance(kind="resistor", nodes=["NET001", "NET999"], value="1k")]

    with pytest.raises(ValueError):
        generate_spice_netlist(simple_netlist, components)


def test_validate_spice_components_reports_unknown(simple_netlist: NetlistResult) -> None:
    components = [ComponentInstance(kind="resistor", nodes=["NET999", "NET001"], value="1k")]

    result = validate_spice_components(simple_netlist, components)

    assert isinstance(result, SpiceValidationResult)
    assert result.errors
    assert "NET999" in result.errors[0]


def test_netlist_roundtrip(simple_netlist: NetlistResult) -> None:
    payload = simple_netlist.to_dict()
    hydrated = netlist_result_from_dict(payload)

    assert len(hydrated.nodes) == len(simple_netlist.nodes)
    assert len(hydrated.edges) == len(simple_netlist.edges)
    assert hydrated.metadata["node_labels"] == simple_netlist.metadata["node_labels"]


def test_parse_component_instances_accepts_minimal_payload() -> None:
    payload = [
        {"kind": "resistor", "nodes": ["N001", "N002"], "value": "100"},
        {"type": "capacitor", "pins": ["N002", "0"], "parameters": {"tol": "5%"}},
    ]

    components = parse_component_instances(payload)

    assert len(components) == 2
    assert components[0].kind == "resistor"
    assert components[1].nodes[-1] == "0"
    assert components[1].parameters["tol"] == "5%"


def test_generate_spice_netlist_warns_on_empty_components(simple_netlist: NetlistResult) -> None:
    netlist_text = generate_spice_netlist(simple_netlist, [], title="Only wiring")

    assert "No components" in netlist_text
    assert "WARN" in netlist_text


def test_spice_endpoint_generates_text(client, simple_netlist: NetlistResult) -> None:
    payload = {
        "netlist": simple_netlist.to_dict(),
        "components": [
            {"kind": "resistor", "nodes": ["NET001", "NET002"], "value": "1k"},
        ],
        "title": "API Test",
    }

    response = client.post("/api/segment/netlist/spice", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, dict)
    assert data["metadata"]["componentCount"] == 1
    assert "R1 NET001 NET002 1k" in data["spice"]


def test_spice_endpoint_stores_history(client, simple_netlist: NetlistResult) -> None:
    payload = {
        "netlist": simple_netlist.to_dict(),
        "storeHistory": True,
    }

    response = client.post("/api/segment/netlist/spice", json=payload)
    assert response.status_code == 200

    data = response.get_json()
    entry = data.get("historyEntry")
    assert entry is not None
    filename = entry["storage"]["filename"]
    assert filename.endswith(".cir")
    upload_folder = client.application.config["UPLOAD_FOLDER"]
    export_path = upload_folder / filename
    assert export_path.exists()
