from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, Optional, Set

JsonDict = Dict[str, object]


class RetouchBuffer:
    """Lightweight storage for the latest fragment prepared for automatic retouch."""

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._lock = threading.Lock()
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._storage_path.exists():
            self._storage_path.write_text("{}", encoding="utf-8")

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

    def _load(self) -> JsonDict:
        try:
            raw = self._storage_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, payload: JsonDict) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        self._write_atomic(serialized)

    def set_entry(self, entry: JsonDict) -> JsonDict:
        if not isinstance(entry, dict):
            raise ValueError("Retouch entry must be a mapping.")
        with self._lock:
            self._save(entry)
        return entry

    def get_entry(self) -> Optional[JsonDict]:
        with self._lock:
            entry = self._load()
        return entry or None

    def clear(self) -> None:
        with self._lock:
            self._save({})

    def get_preserved_filenames(self) -> Set[str]:
        entry = self.get_entry()
        if not entry:
            return set()
        storage = entry.get("storage")
        if not isinstance(storage, dict):
            return set()
        filename = storage.get("filename")
        if isinstance(filename, str) and filename:
            return {filename}
        return set()
