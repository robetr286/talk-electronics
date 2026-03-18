from __future__ import annotations

import json
from pathlib import Path

from talk_electronic.services.processing_history import ProcessingHistoryStore
from talk_electronic.services.retouch_buffer import RetouchBuffer


def _load_json(path: Path) -> object:
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw)


def test_retouch_buffer_roundtrip(tmp_path):
    storage = tmp_path / "retouch-buffer.json"
    buffer = RetouchBuffer(storage)

    payload = {
        "id": "retouch-1",
        "layers": [
            {"name": "base", "opacity": 0.8},
            {"name": "notes", "opacity": 1.0},
        ],
        "storage": {"filename": "retouch_layer.png"},
    }

    stored = buffer.set_entry(payload)
    assert stored == payload
    assert _load_json(storage) == payload

    retrieved = buffer.get_entry()
    assert retrieved == payload
    assert buffer.get_preserved_filenames() == {"retouch_layer.png"}

    buffer.clear()
    assert buffer.get_entry() is None
    assert _load_json(storage) == {}
    assert buffer.get_preserved_filenames() == set()


def test_retouch_buffer_invalid_json(tmp_path):
    storage = tmp_path / "retouch-buffer.json"
    buffer = RetouchBuffer(storage)

    storage.write_text("not a json", encoding="utf-8")
    assert buffer.get_entry() is None

    payload = {"storage": {"filename": "valid.png"}}
    buffer.set_entry(payload)
    assert buffer.get_entry() == payload


def test_processing_history_store_lifecycle(tmp_path):
    storage = tmp_path / "processing-history.json"
    store = ProcessingHistoryStore(storage)

    baseline = store.list_entries()
    assert baseline == []

    first = {
        "id": "entry-1",
        "storage": {"filename": "first.png"},
        "steps": ["import", "segment"],
    }
    second = {
        "id": "entry-2",
        "storage": {"filename": "second.png"},
        "steps": ["import", "retouch"],
    }

    store.upsert_entry(first)
    store.upsert_entry(second)

    listed = store.list_entries()
    assert {entry["id"] for entry in listed} == {"entry-1", "entry-2"}

    updated_first = {
        "id": "entry-1",
        "storage": {"filename": "first.png"},
        "steps": ["import", "segment", "netlist"],
    }
    store.upsert_entry(updated_first)

    retrieved = store.get_entry("entry-1")
    assert retrieved == updated_first

    preserved = store.get_referenced_filenames()
    assert preserved == {"first.png", "second.png"}

    removed = store.remove_entry("entry-2")
    assert removed and removed["id"] == "entry-2"
    assert store.remove_entry("missing") is None

    preserved_after = store.get_referenced_filenames()
    assert preserved_after == {"first.png"}

    cleared = store.clear()
    assert cleared == [updated_first]
    assert store.list_entries() == []


def test_processing_history_recovers_from_invalid_content(tmp_path):
    storage = tmp_path / "processing-history.json"
    storage.parent.mkdir(parents=True, exist_ok=True)
    storage.write_text('{"unexpected": true}', encoding="utf-8")

    store = ProcessingHistoryStore(storage)
    assert store.list_entries() == []

    entry = {"id": "entry-1", "storage": {"filename": "file.png"}}
    store.upsert_entry(entry)
    assert store.list_entries() == [entry]
