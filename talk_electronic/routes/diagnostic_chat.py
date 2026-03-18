from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request

from ..services.diagnostic_chat import DiagnosticChatStore

diagnostic_chat_bp = Blueprint("diagnostic_chat", __name__, url_prefix="/api/chat")

JsonDict = Dict[str, Any]


def _chat_store() -> DiagnosticChatStore:
    return current_app.extensions["diagnostic_chat"]


def _normalize_question(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _sanitize_identifier(value: str) -> str:
    normalized = _normalize_question(value)
    if not normalized:
        return ""
    return normalized.replace(" ", "").replace("-", "").replace("_", "")


def _format_edge_label(digits: str) -> str:
    digits_only = "".join(ch for ch in digits if ch.isdigit())
    return f"edge-{digits_only}" if digits_only else "edge"


EDGE_PATTERN = re.compile(r"e+d+g+e\s*[-_ ]?\s*(\d+)", re.IGNORECASE)
ODCINEK_PATTERN = re.compile(r"(?:odcinek|punkt)\s*(?:nr|numer)?\s*[-_#: ]?\s*(\d+)", re.IGNORECASE)


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit():
            return int(stripped)
        try:
            parsed = float(stripped)
        except ValueError:
            return None
        if parsed.is_integer():
            return int(parsed)
    return None


def _count_value(value: Any) -> Optional[int]:
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return _as_int(value)


def _extract_count_from_dict(data: Any, *keys: str) -> Optional[int]:
    if not isinstance(data, dict):
        return None
    for key in keys or ():
        if key not in data:
            continue
        count = _count_value(data[key])
        if count is not None:
            return count
    return None


def _prepare_segment(entry: JsonDict) -> Optional[JsonDict]:
    if not isinstance(entry, dict):
        return None
    identifier = entry.get("id") or entry.get("segment_id") or entry.get("segmentId")
    if not identifier:
        return None
    try:
        score_value = entry.get("score")
        score_float = float(score_value) if score_value is not None else None
    except (TypeError, ValueError):
        score_float = None
    reasons = entry.get("reasons")
    if isinstance(reasons, list):
        reason_list = [str(item) for item in reasons if str(item)]
    elif reasons:
        reason_list = [str(reasons)]
    else:
        reason_list = []
    label = entry.get("label") if isinstance(entry.get("label"), str) else None
    length_value = entry.get("length")
    if isinstance(length_value, str):
        try:
            length_value = float(length_value.strip())
        except (ValueError, AttributeError):
            length_value = None
    start_node = entry.get("start_node") or entry.get("startNode") or entry.get("from_node")
    end_node = entry.get("end_node") or entry.get("endNode") or entry.get("to_node")
    start_position = entry.get("start_position") or entry.get("startPosition")
    end_position = entry.get("end_position") or entry.get("endPosition")
    return {
        "id": str(identifier),
        "score": score_float,
        "score_text": f"{score_float:.2f}" if isinstance(score_float, float) else None,
        "reasons": reason_list,
        "label": label,
        "length": float(length_value) if isinstance(length_value, (int, float)) else None,
        "start_node": str(start_node) if start_node else None,
        "end_node": str(end_node) if end_node else None,
        "start_position": start_position if isinstance(start_position, (list, tuple)) else None,
        "end_position": end_position if isinstance(end_position, (list, tuple)) else None,
    }


def _collect_segments(session: JsonDict) -> Dict[str, Optional[JsonDict]]:
    segments: List[JsonDict] = []
    flagged = session.get("flaggedSegments") or []
    for entry in flagged:
        prepared = _prepare_segment(entry)
        if prepared:
            segments.append(prepared)

    if not segments:
        confidence = session.get("confidenceSummary") if isinstance(session.get("confidenceSummary"), dict) else {}
        scores = confidence.get("scores") if isinstance(confidence, dict) else None
        if isinstance(scores, dict):
            for seg_id, entry in scores.items():
                candidate = dict(entry) if isinstance(entry, dict) else {}
                candidate.setdefault("id", seg_id)
                prepared = _prepare_segment(candidate)
                if prepared:
                    segments.append(prepared)

    def score_for_min(candidate: JsonDict) -> float:
        return candidate.get("score") if isinstance(candidate.get("score"), float) else 1.0

    def score_for_max(candidate: JsonDict) -> float:
        return candidate.get("score") if isinstance(candidate.get("score"), float) else -1.0

    worst = min(segments, key=score_for_min) if segments else None
    best = max(segments, key=score_for_max) if segments else None

    selected_segment_id = session.get("selectedSegmentId")
    selected_segment = None
    if selected_segment_id:
        for candidate in segments:
            if candidate["id"] == str(selected_segment_id):
                selected_segment = candidate
                break
    if selected_segment is None:
        selected_raw = session.get("selectedSegment")
        selected_segment = _prepare_segment(selected_raw) if selected_raw else None

    return {
        "segments": segments,
        "worst": worst,
        "best": best,
        "selected": selected_segment,
    }


def _format_segment_details(prefix: str, segment: JsonDict) -> str:
    score_text = segment.get("score_text")
    details = f"{prefix} {segment['id']}"
    if score_text:
        details += f" (ocena {score_text})"
    details += "."
    reasons = segment.get("reasons") or []
    if reasons:
        details += f" Powody: {', '.join(reasons)}."
    return details


def _format_segment_connections(segment: JsonDict) -> Optional[str]:
    start_node = segment.get("start_node")
    end_node = segment.get("end_node")
    nodes = [node for node in (start_node, end_node) if isinstance(node, str) and node]
    if not nodes:
        return None
    if len(nodes) == 1:
        return f"Mam tylko jeden węzeł tego odcinka: {nodes[0]}."
    if nodes[0] == nodes[1]:
        return f"Oba końce odcinka są przypisane do tego samego węzła {nodes[0]}."
    return f"Odcinek łączy węzły {nodes[0]} -> {nodes[1]}."


def _format_segment_length(segment: JsonDict) -> Optional[str]:
    length_value = segment.get("length")
    if isinstance(length_value, float):
        length_text = f"{length_value:.2f}" if not length_value.is_integer() else f"{int(length_value)}"
        return f"Długość geometryczna odcinka wynosi {length_text}."
    return None


def _format_worst_group(group: List[JsonDict], *, adverb: str = "") -> str:
    filtered = [segment for segment in group if isinstance(segment.get("id"), str)]
    if not filtered:
        return "Najniższą pewność ma odcinek nieznany."
    adverb_part = f" {adverb.strip()}" if adverb else ""
    score_text = filtered[0].get("score_text")
    if len(filtered) == 1:
        return _format_segment_details(f"Najniższą pewność{adverb_part} ma odcinek", filtered[0])
    ids = ", ".join(segment["id"] for segment in filtered)
    details = f"Najniższą pewność{adverb_part} mają odcinki: {ids}"
    if score_text:
        details += f" (ocena {score_text})"
    return details + "."


def _auto_reply(session: JsonDict, user_content: str) -> str:
    question_text = user_content.strip()
    summary = _collect_segments(session)
    worst = summary["worst"]
    best = summary["best"]
    selected = summary["selected"]
    segments = summary["segments"]

    metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
    node_count = _extract_count_from_dict(metadata, "node_count", "nodeCount", "nodes")
    edge_count = _extract_count_from_dict(
        metadata,
        "edge_count",
        "edgeCount",
        "edges",
        "lines",
        "segments",
        "segment_count",
        "line_count",
    )
    component_count = _extract_count_from_dict(metadata, "connected_components", "components", "component_count")
    cycle_count = _extract_count_from_dict(metadata, "cycles", "cycle_count", "cycleCount")
    netlist_count = _extract_count_from_dict(metadata, "netlist")
    skipped_count = _extract_count_from_dict(metadata, "skipped_segments", "skippedSegments")
    classification_source = metadata.get("node_classification")
    if not isinstance(classification_source, dict):
        classification_source = metadata.get("nodeClassification")
    classification = classification_source if isinstance(classification_source, dict) else {}
    essential_count = _extract_count_from_dict(classification, "essential", "essential_nodes", "essentialCount")
    endpoint_count = _extract_count_from_dict(classification, "endpoint", "endpoints", "terminal", "terminals")

    normalized = _normalize_question(question_text) if question_text else ""
    normalized_compact = normalized.replace(" ", "")
    normalized_alnum = normalized_compact.replace("-", "").replace("_", "")
    count_tokens = ("ile", "ilu", "liczb", "policz", "zlicz")
    count_intent = any(token in normalized for token in count_tokens)
    response_parts: List[str] = []
    response_parts.append(f"Zarejestrowałem pytanie: \u201e{question_text}\u201d.")
    append_lowest_followup = True

    segment_lookup: Dict[str, JsonDict] = {}
    for segment in segments:
        identifier = segment.get("id")
        if isinstance(identifier, str):
            sanitized = _sanitize_identifier(identifier)
            if sanitized and sanitized not in segment_lookup:
                segment_lookup[sanitized] = segment

    mentioned_segments: List[JsonDict] = []
    mentioned_ids: set[str] = set()
    mentioned_segment_ids: set[str] = set()
    if segments and normalized:
        for candidate in segments:
            identifier = candidate.get("id")
            if not isinstance(identifier, str):
                continue
            sanitized = _sanitize_identifier(identifier)
            ident_norm = _normalize_question(identifier)
            if ident_norm and ident_norm in normalized and sanitized not in mentioned_ids:
                mentioned_segments.append(candidate)
                mentioned_ids.add(sanitized)
                mentioned_segment_ids.add(identifier)
                continue
            if sanitized and sanitized in normalized_alnum and sanitized not in mentioned_ids:
                mentioned_segments.append(candidate)
                mentioned_ids.add(sanitized)
                mentioned_segment_ids.add(identifier)

    candidate_identifiers: List[str] = []
    seen_candidates: set[str] = set()
    for match in EDGE_PATTERN.finditer(question_text):
        digits = match.group(1)
        if not digits:
            continue
        candidate = f"edge{digits}"
        if candidate not in seen_candidates:
            candidate_identifiers.append(candidate)
            seen_candidates.add(candidate)
    for match in ODCINEK_PATTERN.finditer(question_text):
        digits = match.group(1)
        if not digits:
            continue
        candidate = f"edge{digits}"
        if candidate not in seen_candidates:
            candidate_identifiers.append(candidate)
            seen_candidates.add(candidate)

    unknown_identifiers: List[str] = []
    for candidate in candidate_identifiers:
        sanitized_candidate = candidate.replace("-", "").replace("_", "")
        if sanitized_candidate not in segment_lookup:
            label = _format_edge_label("".join(ch for ch in candidate if ch.isdigit()))
            if label not in unknown_identifiers:
                unknown_identifiers.append(label)

    handled_specific = False

    worst_group: List[JsonDict] = []
    if worst:
        worst_score = worst.get("score") if isinstance(worst.get("score"), float) else None
        if worst_score is None:
            worst_group = [worst]
        else:

            def _matches_worst(candidate: JsonDict) -> bool:
                candidate_score = candidate.get("score")
                return isinstance(candidate_score, float) and abs(candidate_score - worst_score) < 1e-9

            worst_group = [candidate for candidate in segments if _matches_worst(candidate)] or [worst]
    worst_ids = {segment.get("id") for segment in worst_group if isinstance(segment.get("id"), str)}

    capability_triggers = (
        "co potrafisz",
        "twoje mozliwosci",
        "jakie masz mozliwosci",
        "jak mozesz pomoc",
        "jak dzialasz",
        "co mozesz zrobic",
        "w czym pomagasz",
        "czym sie zajmujesz",
        "jak dziala ten chat",
        "zakresie mozliwosci",
        "twoja funkcjonalnosc",
        "co analizujesz",
    )
    if any(keyword in normalized for keyword in capability_triggers):
        capability_parts: List[str] = []
        capability_parts.append("Analizuję oznaczone odcinki schematu i wyjaśniam powody ich klasyfikacji.")
        capability_parts.append("Mogę wskazać aktualnie podświetlony odcinek oraz porównać poziomy pewności.")

        stats_fragments: List[str] = []
        if edge_count is not None:
            stats_fragments.append(f"odcinków = {edge_count}")
        elif segments:
            stats_fragments.append(f"segmentów do przejrzenia = {len(segments)}")
        if node_count is not None:
            stats_fragments.append(f"węzłów = {node_count}")
        if component_count is not None:
            stats_fragments.append(f"komponentów = {component_count}")
        if cycle_count is not None:
            stats_fragments.append(f"cykli = {cycle_count}")
        if stats_fragments:
            capability_parts.append(
                "Na podstawie ostatniej analizy mam policzone statystyki: " + ", ".join(stats_fragments) + "."
            )

        if netlist_count is not None:
            capability_parts.append(f"Generuję netlistę z {netlist_count} wpisami, gdy jest dostępna.")

        classification_fragments: List[str] = []
        if essential_count is not None:
            classification_fragments.append(f"węzły kluczowe = {essential_count}")
        if endpoint_count is not None:
            classification_fragments.append(f"zakończenia ścieżek = {endpoint_count}")
        if classification_fragments:
            capability_parts.append(
                "Rozpoznaję klasyfikację węzłów, m.in. " + ", ".join(classification_fragments) + "."
            )

        capability_parts.append(
            "Możesz pytać o konkretne odcinki, poprosić o porównanie pewności lub o dodatkowe dane liczbowe."
        )

        response_parts.extend(capability_parts)
        handled_specific = True
        append_lowest_followup = False

    if not handled_specific and count_intent:
        count_pairs = (
            ("węzłów", node_count, ("wez", "punkt", "node")),
            ("odcinków", edge_count, ("odcink", "segment", "edge", "lini", "polaczen", "laczen", "sciez")),
            ("komponentów", component_count, ("komponent", "modul", "sekcj", "obwod")),
            ("cykli", cycle_count, ("cykl", "petl")),
            ("wpisów netlisty", netlist_count, ("netlist", "netlis", "netlista")),
            ("pominiętych segmentów", skipped_count, ("pomin", "odrzuc", "skipped")),
        )
        counts_reported = False
        for noun, count_value, keywords in count_pairs:
            if not any(keyword in normalized for keyword in keywords):
                continue
            if count_value is not None:
                response_parts.append(f"Liczba {noun} wynosi {count_value}.")
            elif noun == "odcinków" and segments:
                response_parts.append(f"Mam oznaczonych segmentów do przejrzenia: {len(segments)}.")
            else:
                response_parts.append(f"Nie mam policzonej liczby {noun} dla tej próbki.")
            counts_reported = True
        if counts_reported:
            handled_specific = True
            append_lowest_followup = False

    if "najwyzsz" in normalized or "max" in normalized:
        if best:
            response_parts.append(_format_segment_details("Najwyższą pewność ma odcinek", best))
            if worst_group and best.get("id") not in worst_ids:
                response_parts.append(_format_worst_group(worst_group, adverb="nadal"))
        elif segments:
            response_parts.append("Nie rozpoznaję odcinka o wyższej pewności niż pozostałe.")
        else:
            response_parts.append("Nie mam danych o pewności odcinków.")
        handled_specific = True
    elif any(keyword in normalized for keyword in ("podswietl", "zaznacz", "aktywn", "wybrany")):
        if selected:
            response_parts.append(_format_segment_details("Obecnie podświetlony jest odcinek", selected))
        elif segments:
            response_parts.append(
                _format_segment_details(
                    "Nie otrzymałem informacji o aktywnym punkcie, domyślam się, że chodzi o odcinek",
                    segments[0],
                )
            )
        else:
            response_parts.append("Nie mam informacji o aktualnie podświetlonym punkcie.")
        handled_specific = True
    elif "dlaczego" in normalized and ("powtarz" in normalized or "ciagle" in normalized):
        response_parts.append(
            "Odpowiedzi generuję na podstawie oznaczonych odcinków i dostępnych podsumowań, "
            "dlatego mogą brzmieć podobnie, gdy dane się nie zmieniają."
        )
        if worst_group:
            response_parts.append(_format_worst_group(worst_group, adverb="nadal"))
        handled_specific = True
    elif "co moge" in normalized and ("spytac" in normalized or "zapytac" in normalized):
        response_parts.append(
            "Możesz pytać o konkretne odcinki (np. edge-21), porównanie pewności, powody oznaczenia segmentów "
            "lub poprosić o wskazanie aktualnie podświetlonego odcinka."
        )
        handled_specific = True
    elif "nie dzialasz" in normalized or "nie dziala" in normalized:
        response_parts.append(
            "Działam w oparciu o dane z segmentacji. Sprawdź, czy nowe wyniki zostały zapisane, "
            "a następnie ponów pytanie o konkretny odcinek lub aktualną selekcję."
        )
        handled_specific = True

    if unknown_identifiers:
        for label in unknown_identifiers:
            response_parts.append(
                (
                    f"Nie znajduję odcinka {label} w bieżącej liście wyników. "
                    "Sprawdź identyfikator w zestawieniu i spróbuj ponownie."
                )
            )
        handled_specific = True

    if mentioned_segments:
        seen_ids: set[str] = set()
        detail_keywords = ("szczeg", "informac", "parametr", "opis", "dane", "detal")
        want_details = any(keyword in normalized for keyword in detail_keywords)
        node_keywords = ("punkt", "wez", "wezl", "node", "kontakt", "pin")
        want_node_counts = count_intent and any(keyword in normalized for keyword in node_keywords)
        for candidate in mentioned_segments:
            identifier = candidate.get("id")
            if not isinstance(identifier, str) or identifier in seen_ids:
                continue
            prefix = "Odcinek"
            if selected and identifier == selected.get("id"):
                prefix = "Podświetlony odcinek"
            response_parts.append(_format_segment_details(prefix, candidate))
            mentioned_segment_ids.add(identifier)
            nodes = [
                node
                for node in (candidate.get("start_node"), candidate.get("end_node"))
                if isinstance(node, str) and node
            ]
            if want_node_counts:
                if nodes:
                    unique_nodes = list(dict.fromkeys(nodes))
                    if len(unique_nodes) == 1:
                        response_parts.append(f"Liczba znanych węzłów dla {identifier} wynosi 1 ({unique_nodes[0]}).")
                    else:
                        joined_nodes = " -> ".join(unique_nodes)
                        response_parts.append(
                            f"Liczba znanych węzłów dla {identifier} wynosi {len(unique_nodes)} " f"({joined_nodes})."
                        )
                    connection_text = _format_segment_connections(candidate)
                    if connection_text:
                        response_parts.append(connection_text)
                else:
                    response_parts.append(f"Nie mam informacji o węzłach przypisanych do {identifier}.")
                append_lowest_followup = False
            else:
                connection_text = _format_segment_connections(candidate)
                if connection_text:
                    response_parts.append(connection_text)
                length_text = _format_segment_length(candidate)
                if length_text and want_details:
                    response_parts.append(length_text)
                if want_details and not candidate.get("reasons"):
                    response_parts.append("Brak dodatkowych powodów oznaczenia poza bieżącą klasyfikacją.")
                append_lowest_followup = append_lowest_followup and not want_details
            seen_ids.add(identifier)
        handled_specific = True

    if not handled_specific and not mentioned_segments and ("odcink" in normalized or "punkc" in normalized):
        response_parts.append(
            "Podaj identyfikator odcinka (np. edge-21), abym mógł udzielić dokładniejszej odpowiedzi."
        )
        handled_specific = True

    if not handled_specific:
        if worst_group:
            response_parts.append(_format_worst_group(worst_group))
        if best and (not worst_ids or best.get("id") not in worst_ids):
            response_parts.append(_format_segment_details("Najwyższą pewność ma odcinek", best))
    else:
        if append_lowest_followup and worst_group and (worst_ids - mentioned_segment_ids):
            response_parts.append(_format_worst_group(worst_group, adverb="nadal"))

    advice_line = "Porównaj wskazane odcinki ze schematem i sprawdź sąsiednie węzły, aby potwierdzić klasyfikację."
    if segments:
        if advice_line not in response_parts:
            response_parts.append(advice_line)
    else:
        response_parts.append("Dodaj oznaczone odcinki lub podsumowanie pewności, aby uzyskać dokładniejszą analizę.")

    return " ".join(response_parts)


@diagnostic_chat_bp.post("/sessions")
def create_session():  # type: ignore[override]
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Nieprawidłowe dane wejściowe"}), 400

    element_id = payload.get("elementId")
    title = payload.get("title") or payload.get("label")
    source_url = payload.get("sourceUrl") or payload.get("source")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    flagged_segments = payload.get("flaggedSegments") if isinstance(payload.get("flaggedSegments"), list) else []
    confidence_summary = payload.get("confidenceSummary") if isinstance(payload.get("confidenceSummary"), dict) else {}
    selected_segment_id = payload.get("selectedSegmentId")
    selected_segment = payload.get("selectedSegment") if isinstance(payload.get("selectedSegment"), dict) else None

    store = _chat_store()
    session = store.create_session(
        element_id=str(element_id) if element_id else None,
        title=str(title) if title else None,
        source_url=str(source_url) if source_url else None,
        metadata=metadata,
        flagged_segments=flagged_segments,
        confidence_summary=confidence_summary,
        selected_segment_id=str(selected_segment_id) if selected_segment_id else None,
        selected_segment=selected_segment,
    )
    return jsonify({"session": session}), 201


@diagnostic_chat_bp.get("/sessions/<session_id>")
def get_session(session_id: str):  # type: ignore[override]
    store = _chat_store()
    session = store.get_session(session_id)
    if session is None:
        return jsonify({"error": "Nie znaleziono sesji"}), 404
    return jsonify({"session": session}), 200


@diagnostic_chat_bp.post("/sessions/<session_id>/messages")
def post_message(session_id: str):  # type: ignore[override]
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Nieprawidłowe dane wejściowe"}), 400

    content = payload.get("content") or payload.get("message")
    if not isinstance(content, str) or not content.strip():
        return jsonify({"error": "Wiadomość musi być tekstem"}), 400

    selected_segment_id = payload.get("selectedSegmentId")
    if isinstance(selected_segment_id, str) and not selected_segment_id.strip():
        selected_segment_id = None
    selected_segment = payload.get("selectedSegment") if isinstance(payload.get("selectedSegment"), dict) else None

    store = _chat_store()
    session = store.get_session(session_id)
    if session is None:
        return jsonify({"error": "Sesja nie istnieje"}), 404

    session_updates: Dict[str, Any] = {}
    if selected_segment_id:
        session_updates["selectedSegmentId"] = str(selected_segment_id)
        session["selectedSegmentId"] = str(selected_segment_id)
    if selected_segment:
        session_updates["selectedSegment"] = selected_segment
        session["selectedSegment"] = selected_segment
    elif selected_segment_id is None and "selectedSegment" in session_updates:
        session_updates["selectedSegment"] = None

    user_message: JsonDict = {
        "id": f"msg-{uuid.uuid4().hex}",
        "role": "user",
        "content": content.strip(),
        "createdAt": datetime.utcnow().isoformat(),
    }

    assistant_text = _auto_reply(session, content)
    assistant_message: JsonDict = {
        "id": f"msg-{uuid.uuid4().hex}",
        "role": "assistant",
        "content": assistant_text,
        "createdAt": datetime.utcnow().isoformat(),
    }

    updates_payload = session_updates or None
    updated = store.append_messages(
        session_id,
        [user_message, assistant_message],
        session_updates=updates_payload,
    )
    if updated is None:
        return jsonify({"error": "Nie udało się zapisać wiadomości"}), 500

    return jsonify({"session": updated, "messages": updated.get("messages", [])}), 201
