from talk_electronic import create_app


def test_readiness_no_sessions(tmp_path):
    app = create_app({"UPLOAD_FOLDER": tmp_path, "TESTING": True})
    client = app.test_client()

    resp = client.get("/api/diagnostics/readiness")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert isinstance(payload, dict)
    assert payload["symbols_detected"] is False
    assert payload["netlist_generated"] is False
    assert payload["labels_coverage_pct"] == 0
    assert payload["values_coverage_pct"] == 0
    assert payload["ready"] is False


def test_apply_corrections(tmp_path):
    app = create_app({"UPLOAD_FOLDER": tmp_path, "TESTING": True})
    client = app.test_client()

    store = app.extensions["diagnostic_chat"]
    # Components with missing values
    metadata = {
        "components": [
            {"ref": "R1", "label": "R1", "value": None},
            {"ref": "C1", "label": None, "value": None},
        ]
    }
    session = store.create_session(element_id=None, title="t", source_url=None, metadata=metadata)

    # Before corrections: values_coverage_pct should be 0
    resp = client.get("/api/diagnostics/readiness")
    payload = resp.get_json()
    assert payload["values_coverage_pct"] == 0

    # Apply corrections: set R1 value and C1 label+value
    corrections = {"R1": {"value": "10kΩ"}, "C1": {"label": "C1", "value": "100µF"}}
    resp = client.post("/api/diagnostics/corrections", json={"session_id": session["id"], "corrections": corrections})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert set(body["applied"]) == {"R1", "C1"}

    # After corrections: values_coverage_pct should be > 0
    resp = client.get("/api/diagnostics/readiness")
    payload = resp.get_json()
    assert payload["values_coverage_pct"] >= 50
    # missing_details should not list R1 and C1 under missing_values or missing_labels
    md = payload.get("missing_details") or {}
    assert "R1" not in md.get("missing_values", [])
    assert "C1" not in md.get("missing_values", [])


def test_readiness_with_session(tmp_path):
    app = create_app({"UPLOAD_FOLDER": tmp_path, "TESTING": True})
    client = app.test_client()

    # Create a session in the DiagnosticChatStore
    store = app.extensions["diagnostic_chat"]
    metadata = {
        "symbols": ["R", "C", "IC"],
        "netlist": [{"id": "net1"}, {"id": "net2"}],
        "labels_coverage_pct": 85,
        "values_coverage_pct": 90,
    }
    store.create_session(element_id=None, title="t", source_url=None, metadata=metadata)

    resp = client.get("/api/diagnostics/readiness")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["symbols_detected"] is True
    assert payload["netlist_generated"] is True
    assert payload["labels_coverage_pct"] >= 80
    assert payload["values_coverage_pct"] >= 80
    assert payload["ready"] is True
