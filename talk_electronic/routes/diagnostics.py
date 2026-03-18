from __future__ import annotations

from typing import Any, Dict, List

from flask import Blueprint, current_app, jsonify

diagnostics_bp = Blueprint("diagnostics", __name__, url_prefix="/api/diagnostics")


def _get_latest_session() -> Dict[str, Any] | None:
    store = current_app.extensions.get("diagnostic_chat")
    if not store:
        return None
    sessions = store.list_sessions()
    if not sessions:
        return None
    return sessions[-1]


@diagnostics_bp.route("/readiness", methods=["GET"])
def diagnostics_readiness():
    """Return a lightweight readiness summary for the diagnostics checklist.

    This inspects the latest diagnostic session (if any) and returns the
    following JSON structure used by the frontend:
      - symbols_detected: bool
      - netlist_generated: bool
      - labels_coverage_pct: int (0-100)
      - values_coverage_pct: int (0-100)
      - avg_confidence: float (0.0-1.0)
      - missing: list[str]
      - ready: bool
    """
    session = _get_latest_session()

    symbols_detected = False
    netlist_generated = False
    labels_coverage = 0
    values_coverage = 0
    avg_confidence = 0.0

    if session and isinstance(session, dict):
        metadata = session.get("metadata") or {}
        # prepare components list early for coverage calculation and details
        comp_list = metadata.get("components") or metadata.get("symbols") or []
        components = comp_list if isinstance(comp_list, list) else []

        # heuristics: check common keys used in other parts of app
        symbols = metadata.get("symbols") or metadata.get("components") or metadata.get("detected_symbols")
        if symbols:
            try:
                symbols_detected = len(symbols) > 0
            except Exception:
                symbols_detected = True

        netlist = metadata.get("netlist") or metadata.get("netlist_entries") or metadata.get("netlist_count")
        if isinstance(netlist, (list, dict)):
            netlist_generated = len(netlist) > 0
        elif isinstance(netlist, (int, float)):
            netlist_generated = int(netlist) > 0

        # coverage may be stored or we compute a fallback
        labels_coverage = int(metadata.get("labels_coverage_pct") or metadata.get("labelsCoverage") or 0)
        values_coverage = int(metadata.get("values_coverage_pct") or metadata.get("valuesCoverage") or 0)

        # Fallback: compute coverage from components list if available
        if isinstance(components, list) and components:
            total = len(components)
            labels_count = 0
            values_count = 0
            for c in components:
                if isinstance(c, dict):
                    if c.get("label"):
                        labels_count += 1
                    if c.get("value"):
                        values_count += 1
            # only override if we didn't already have coverage info (0) or it's more accurate
            try:
                computed_labels_pct = int(labels_count * 100 / total)
                computed_values_pct = int(values_count * 100 / total)
                if labels_coverage == 0:
                    labels_coverage = computed_labels_pct
                if values_coverage == 0:
                    values_coverage = computed_values_pct
            except Exception:
                pass

        conf = session.get("confidenceSummary") or metadata.get("confidence") or {}
        if isinstance(conf, dict):
            avg = conf.get("avg") or conf.get("average") or conf.get("mean")
            try:
                avg_confidence = float(avg) if avg is not None else 0.0
            except Exception:
                avg_confidence = 0.0

    missing: List[str] = []
    if not symbols_detected:
        missing.append("symbols")
    if not netlist_generated:
        missing.append("netlist")
    if labels_coverage < 80:
        missing.append("component_labels")
    if values_coverage < 80:
        missing.append("component_values")

    ready = symbols_detected and netlist_generated and (labels_coverage >= 80 or values_coverage >= 80)

    # Provide more detailed missing items when possible
    missing_details: Dict[str, List[str]] = {}
    components = []
    if session and isinstance(session, dict):
        metadata = session.get("metadata") or {}
        comp_list = metadata.get("components") or metadata.get("symbols") or []
        if isinstance(comp_list, list):
            components = comp_list

    missing_comp_labels = []
    missing_comp_values = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        ref = comp.get("ref") or comp.get("id") or comp.get("name")
        if ref:
            if not comp.get("label"):
                missing_comp_labels.append(str(ref))
            if not comp.get("value"):
                missing_comp_values.append(str(ref))

    if missing_comp_labels:
        missing_details["missing_labels"] = missing_comp_labels
    if missing_comp_values:
        missing_details["missing_values"] = missing_comp_values

    result = {
        "symbols_detected": bool(symbols_detected),
        "netlist_generated": bool(netlist_generated),
        "labels_coverage_pct": int(labels_coverage),
        "values_coverage_pct": int(values_coverage),
        "avg_confidence": float(avg_confidence),
        "missing": missing,
        "missing_details": missing_details,
        "ready": bool(ready),
    }

    return jsonify(result)


@diagnostics_bp.route("/corrections", methods=["POST"])
def apply_corrections():
    """Apply user corrections (labels/values) to the latest session.

    Expected JSON payload example:
    {
      "session_id": "chat-...",   # optional, otherwise use latest session
      "corrections": {
         "R1": {"label":"R1","value":"10kΩ"},
         "C5": {"label":"C5","value":"100µF"}
      }
    }
    """
    from flask import request

    payload = request.get_json() or {}

    session_id = payload.get("session_id")
    corrections = payload.get("corrections") or {}

    store = current_app.extensions.get("diagnostic_chat")
    if not store:
        return jsonify({"ok": False, "message": "No diagnostic chat store available"}), 500

    session = None
    if isinstance(session_id, str):
        session = store.get_session(session_id)
    if session is None:
        sessions = store.list_sessions()
        session = sessions[-1] if sessions else None

    if session is None:
        return jsonify({"ok": False, "message": "No session available to apply corrections"}), 400

    # Apply corrections to metadata.components if present, or create list
    metadata = session.get("metadata") or {}
    comps = metadata.get("components") if isinstance(metadata.get("components"), list) else []

    # Map by ref for easy updates
    comp_map = {}
    for c in comps:
        if isinstance(c, dict):
            ref = c.get("ref") or c.get("id") or c.get("name")
            if ref:
                comp_map[str(ref)] = dict(c)

    # Apply incoming corrections
    for ref, data in corrections.items() if isinstance(corrections, dict) else ():  # type: ignore
        if not isinstance(data, dict):
            continue
        entry = comp_map.get(ref) or {"ref": ref}
        if "label" in data:
            entry["label"] = data["label"]
        if "value" in data:
            entry["value"] = data["value"]
        comp_map[ref] = entry

    # Persist back to metadata.components
    metadata["components"] = list(comp_map.values())
    session["metadata"] = metadata

    # Add audit entry in session.messages so corrections are traceable
    import time

    audit_message = {"role": "user", "content": f"Applied corrections: {corrections}", "timestamp": time.time()}
    store.append_messages(session["id"], [audit_message], session_updates={"metadata": metadata})

    return jsonify({"ok": True, "applied": list(corrections.keys())})
