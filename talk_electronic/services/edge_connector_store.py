from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional

JsonDict = Dict[str, object]


class EdgeConnectorStore:
    """Thread-safe storage for edge connector annotations and artifacts."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._index_path = base_dir / "index.json"
        self._lock = threading.Lock()
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        if not self._index_path.exists():
            self._index_path.write_text("[]", encoding="utf-8")

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def json_dir(self) -> Path:
        return self._base_dir / "entries"

    @property
    def assets_dir(self) -> Path:
        """Optional directory for future screenshots or attachments."""

        return self._base_dir / "assets"

    def entry_payload_path(self, entry_id: str) -> Path:
        return self.json_dir / f"{entry_id}.json"

    def _write_atomic(self, payload: str) -> None:
        directory = self._index_path.parent
        directory.mkdir(parents=True, exist_ok=True)
        prefix = f".{self._index_path.name}."
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(directory),
            prefix=prefix,
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        try:
            os.replace(temp_path, self._index_path)
        except OSError:
            temp_path.unlink(missing_ok=True)
            raise

    def _load_entries(self) -> List[JsonDict]:
        try:
            raw = self._index_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [entry for entry in data if isinstance(entry, dict)]

    def _save_entries(self, entries: List[JsonDict]) -> None:
        serialized = json.dumps(entries, ensure_ascii=False, indent=2)
        self._write_atomic(serialized)

    def list_entries(self) -> List[JsonDict]:
        with self._lock:
            return self._load_entries()

    def upsert_entry(self, entry: JsonDict) -> JsonDict:
        entry_id = entry.get("id")
        if not isinstance(entry_id, str):
            raise ValueError("Entry must contain a string 'id'.")

        with self._lock:
            entries = self._load_entries()
            replaced = False
            for idx, existing in enumerate(entries):
                if existing.get("id") == entry_id:
                    entries[idx] = entry
                    replaced = True
                    break
            if not replaced:
                entries.append(entry)
            self._save_entries(entries)
        return entry

    def get_entry(self, entry_id: str) -> Optional[JsonDict]:
        with self._lock:
            entries = self._load_entries()
            for entry in entries:
                if entry.get("id") == entry_id:
                    return entry
        return None

    def remove_entry(self, entry_id: str) -> Optional[JsonDict]:
        with self._lock:
            entries = self._load_entries()
            kept: List[JsonDict] = []
            removed: Optional[JsonDict] = None
            for entry in entries:
                if entry.get("id") == entry_id:
                    removed = entry
                else:
                    kept.append(entry)
            if removed is None:
                return None
            self._save_entries(kept)
            payload_path = self.entry_payload_path(entry_id)
            payload_path.unlink(missing_ok=True)
            return removed

    def clear(self) -> List[JsonDict]:
        with self._lock:
            entries = self._load_entries()
            self._save_entries([])
            for entry in entries:
                entry_id = entry.get("id")
                if isinstance(entry_id, str):
                    self.entry_payload_path(entry_id).unlink(missing_ok=True)
            return entries

    def save_payload(self, entry_id: str, payload: JsonDict) -> Path:
        path = self.entry_payload_path(entry_id)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        path.write_text(serialized, encoding="utf-8")
        return path

    def load_payload(self, entry_id: str) -> Optional[JsonDict]:
        path = self.entry_payload_path(entry_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
