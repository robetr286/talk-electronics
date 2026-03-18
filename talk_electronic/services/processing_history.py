from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

JsonDict = Dict[str, object]


class ProcessingHistoryStore:
    """Thread-safe JSON-backed storage for image processing history."""

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._lock = threading.Lock()
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._storage_path.exists():
            self._storage_path.write_text("[]", encoding="utf-8")

    def _write_atomic(self, payload: str) -> None:
        directory = self._storage_path.parent
        directory.mkdir(parents=True, exist_ok=True)
        prefix = f".{self._storage_path.name}."
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
            os.replace(temp_path, self._storage_path)
        except OSError:
            temp_path.unlink(missing_ok=True)
            raise

    def _load_entries(self) -> List[JsonDict]:
        try:
            raw = self._storage_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [entry for entry in data if isinstance(entry, dict)]

    def _save_entries(self, entries: Iterable[JsonDict]) -> None:
        serialized = json.dumps(list(entries), ensure_ascii=False, indent=2)
        self._write_atomic(serialized)

    def list_entries(self) -> List[JsonDict]:
        with self._lock:
            return self._load_entries()

    def upsert_entry(self, entry: JsonDict) -> JsonDict:
        entry_id = entry.get("id")
        if not isinstance(entry_id, str):
            raise ValueError("Entry must include a string 'id'.")

        with self._lock:
            entries = self._load_entries()
            updated = False
            for idx, existing in enumerate(entries):
                if existing.get("id") == entry_id:
                    entries[idx] = entry
                    updated = True
                    break
            if not updated:
                entries.append(entry)
            self._save_entries(entries)
        return entry

    def remove_entry(self, entry_id: str) -> Optional[JsonDict]:
        with self._lock:
            entries = self._load_entries()
            filtered: List[JsonDict] = []
            removed: Optional[JsonDict] = None
            for entry in entries:
                if entry.get("id") == entry_id:
                    removed = entry
                    continue
                filtered.append(entry)
            if removed is None:
                return None
            self._save_entries(filtered)
            return removed

    def remove_entries(self, entry_ids: Iterable[str]) -> List[JsonDict]:
        id_set: Set[str] = {str(entry_id) for entry_id in entry_ids if entry_id}
        if not id_set:
            return []
        with self._lock:
            entries = self._load_entries()
            kept: List[JsonDict] = []
            removed: List[JsonDict] = []
            for entry in entries:
                identifier = entry.get("id")
                if isinstance(identifier, str) and identifier in id_set:
                    removed.append(entry)
                else:
                    kept.append(entry)
            if removed:
                self._save_entries(kept)
            return removed

    def clear(self) -> List[JsonDict]:
        with self._lock:
            entries = self._load_entries()
            self._save_entries([])
            return entries

    def get_referenced_filenames(self) -> Set[str]:
        preserved: Set[str] = set()
        for entry in self.list_entries():
            storage = entry.get("storage")
            if isinstance(storage, dict):
                filename = storage.get("filename")
                if isinstance(filename, str) and filename:
                    preserved.add(filename)
        return preserved

    def get_entry(self, entry_id: str) -> Optional[JsonDict]:
        with self._lock:
            entries = self._load_entries()
            for entry in entries:
                if entry.get("id") == entry_id:
                    return entry
        return None
