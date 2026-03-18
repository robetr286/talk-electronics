from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from talk_electronic.routes.diagnostic_chat import _auto_reply
from talk_electronic.services.diagnostic_chat import DiagnosticChatStore


@pytest.fixture()
def sample_session() -> dict[str, object]:
    return {
        "flaggedSegments": [
            {
                "id": "edge-21",
                "score": 0.0,
                "reasons": ["end_endpoint", "isolated_branch", "marginal_length"],
                "start_node": "N1",
                "end_node": "N2",
                "length": 123.456,
            },
            {
                "id": "edge-42",
                "score": 0.82,
                "reasons": ["long_segment"],
                "start_node": "N2",
                "end_node": "N5",
            },
        ],
        "confidenceSummary": {
            "scores": {
                "edge-21": {"score": 0.0, "reasons": ["end_endpoint"]},
                "edge-42": {"score": 0.82, "reasons": ["long_segment"]},
            }
        },
        "selectedSegmentId": "edge-21",
        "metadata": {
            "node_count": 6,
            "edge_count": 12,
            "connected_components": [{"id": 1}, {"id": 2}],
            "cycles": ["loop-1"],
            "netlist": ["WIRE 1", "WIRE 2", "WIRE 3"],
            "skipped_segments": ["edge-99"],
            "node_classification": {"essential": 2, "endpoint": 4},
        },
    }


def test_auto_reply_reports_lowest_score(sample_session):
    reply = _auto_reply(sample_session, "Podaj nr punktu.")
    assert "Najniższą pewność ma odcinek edge-21" in reply
    assert "Porównaj wskazane odcinki" in reply


def test_auto_reply_handles_highest_score_question(sample_session):
    reply = _auto_reply(sample_session, "A najwyższą pewność ma jaki punkt ?")
    assert "Najwyższą pewność ma odcinek edge-42" in reply
    assert "Najniższą pewność nadal ma odcinek edge-21" in reply


def test_auto_reply_describes_selected_segment(sample_session):
    sample_session["selectedSegmentId"] = "edge-42"
    reply = _auto_reply(sample_session, "Który punkt teraz mam podświetlony?")
    assert "Obecnie podświetlony jest odcinek edge-42" in reply


def test_auto_reply_explains_repeated_question(sample_session):
    reply = _auto_reply(sample_session, "Dlaczego powtarzasz ciągle tę samą odpowiedź?")
    assert "Odpowiedzi generuję" in reply
    assert "edge-21" in reply


def test_auto_reply_handles_missing_segments():
    reply = _auto_reply({"flaggedSegments": []}, "Jakie są wyniki?")
    assert "Dodaj oznaczone odcinki" in reply


def test_auto_reply_mentions_explicit_segment(sample_session):
    reply = _auto_reply(sample_session, "Co możesz powiedzieć o edge 21?")
    assert "Podświetlony odcinek edge-21" in reply


def test_auto_reply_handles_help_question(sample_session):
    reply = _auto_reply(sample_session, "O co mogę cię spytać?")
    assert "Możesz pytać o konkretne odcinki" in reply


def test_auto_reply_requests_identifier_for_generic_question(sample_session):
    sample_session["selectedSegmentId"] = None
    reply = _auto_reply(sample_session, "Co mi możesz powiedzieć o tym punkcie?")
    assert "Podaj identyfikator odcinka" in reply


def test_auto_reply_handles_unknown_segment(sample_session):
    reply = _auto_reply(sample_session, "A odcinek eddge72 jakie ma parametry?")
    assert "Nie znajduję odcinka edge-72" in reply


def test_auto_reply_describes_capabilities(sample_session):
    reply = _auto_reply(sample_session, "Co jest w twoim zakresie możliwości?")
    assert "Analizuję oznaczone odcinki schematu" in reply
    assert "odcinków = 12" in reply
    assert "węzłów = 6" in reply


def test_auto_reply_reports_counts_from_metadata(sample_session):
    reply = _auto_reply(sample_session, "Ile punktów jest na schemacie?")
    assert "Liczba węzłów wynosi 6" in reply
    second = _auto_reply(sample_session, "Ile odcinków znalazłeś?")
    assert "Liczba odcinków wynosi 12" in second


def test_auto_reply_counts_segments_without_metadata():
    session = {
        "flaggedSegments": [
            {"id": "edge-1", "score": 0.25},
            {"id": "edge-2", "score": 0.5},
        ],
    }
    reply = _auto_reply(session, "Ile odcinków oznaczyłeś?")
    assert "Mam oznaczonych segmentów do przejrzenia: 2" in reply


def test_auto_reply_reports_segment_node_count(sample_session):
    reply = _auto_reply(sample_session, "Edge-21 z ilu punktów się składa?")
    assert "Liczba znanych węzłów dla edge-21 wynosi 2" in reply
    assert "N1 -> N2" in reply


def test_auto_reply_provides_segment_details(sample_session):
    reply = _auto_reply(sample_session, "Podaj mi szczegóły dla edge-21")
    assert "Odcinek łączy węzły N1 -> N2" in reply
    assert "Długość geometryczna odcinka wynosi 123.46" in reply


def test_store_appends_messages_and_updates_selection(tmp_path: Path):
    storage = tmp_path / "chat.json"
    store = DiagnosticChatStore(storage)
    session = store.create_session(
        element_id="element-1",
        title="Test",
        source_url="http://example.local",
        metadata={"context": "demo"},
        flagged_segments=[{"id": "edge-21", "score": 0.1}],
        confidence_summary={"scores": {"edge-21": {"score": 0.1}}},
        selected_segment_id="edge-21",
    )

    session_id = session["id"]
    first_message = {
        "id": "msg-1",
        "role": "user",
        "content": "Pierwsza wiadomość",
        "createdAt": datetime.utcnow().isoformat(),
    }
    store.append_messages(session_id, [first_message], session_updates={"selectedSegmentId": "edge-42"}, max_messages=3)

    updated = store.get_session(session_id)
    assert updated is not None
    assert updated.get("selectedSegmentId") == "edge-42"
    assert len(updated.get("messages", [])) == 1

    base_time = datetime.utcnow()
    bulk_messages = []
    for index in range(4):
        bulk_messages.append(
            {
                "id": f"msg-{index + 2}",
                "role": "assistant" if index % 2 else "user",
                "content": f"Wiadomość {index + 2}",
                "createdAt": (base_time + timedelta(seconds=index)).isoformat(),
            }
        )

    store.append_messages(session_id, bulk_messages, max_messages=2)

    trimmed = store.get_session(session_id)
    assert trimmed is not None
    assert len(trimmed.get("messages", [])) == 2
    assert trimmed["messages"][0]["id"] == "msg-4"
    assert trimmed["messages"][1]["id"] == "msg-5"
