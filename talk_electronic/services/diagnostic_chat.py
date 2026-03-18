from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

JsonDict = Dict[str, Any]


class DiagnosticChatStore:
    """Prosta, współdzielona pamięć rozmów diagnostycznych zapisywana w pliku JSON."""

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

    def _load_sessions(self) -> List[JsonDict]:
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
        return [session for session in data if isinstance(session, dict)]

    def _save_sessions(self, sessions: Iterable[JsonDict]) -> None:
        payload = json.dumps(list(sessions), ensure_ascii=False, indent=2)
        self._write_atomic(payload)

    def list_sessions(self) -> List[JsonDict]:
        with self._lock:
            return self._load_sessions()

    def create_session(
        self,
        *,
        element_id: Optional[str],
        title: Optional[str],
        source_url: Optional[str],
        metadata: Optional[JsonDict] = None,
        flagged_segments: Optional[Sequence[JsonDict]] = None,
        confidence_summary: Optional[JsonDict] = None,
        selected_segment_id: Optional[str] = None,
        selected_segment: Optional[JsonDict] = None,
    ) -> JsonDict:
        session_id = f"chat-{uuid.uuid4().hex}"
        created_at = datetime.now(timezone.utc).isoformat()
        flagged_payload = [entry for entry in (flagged_segments or []) if isinstance(entry, dict)]
        selected_segment_payload = selected_segment if isinstance(selected_segment, dict) else None
        session: JsonDict = {
            "id": session_id,
            "createdAt": created_at,
            "updatedAt": created_at,
            "elementId": element_id,
            "title": title or "Sesja diagnostyczna",
            "sourceUrl": source_url,
            "metadata": metadata or {},
            "flaggedSegments": flagged_payload,
            "confidenceSummary": confidence_summary if isinstance(confidence_summary, dict) else {},
            "messages": [],
            "selectedSegmentId": str(selected_segment_id) if selected_segment_id else None,
            "selectedSegment": selected_segment_payload,
        }
        with self._lock:
            sessions = self._load_sessions()
            sessions.append(session)
            self._save_sessions(sessions)
        return session

    def get_session(self, session_id: str) -> Optional[JsonDict]:
        with self._lock:
            sessions = self._load_sessions()
            for session in sessions:
                if session.get("id") == session_id:
                    return session
        return None

    def append_messages(
        self,
        session_id: str,
        messages: Sequence[JsonDict],
        *,
        session_updates: Optional[JsonDict] = None,
        max_messages: int = 40,
    ) -> Optional[JsonDict]:
        with self._lock:
            sessions = self._load_sessions()
            updated_session: Optional[JsonDict] = None
            for session in sessions:
                if session.get("id") != session_id:
                    continue
                session.setdefault("messages", [])
                if not isinstance(session["messages"], list):
                    session["messages"] = []
                session["messages"].extend(messages)
                if max_messages and max_messages > 0:
                    session["messages"] = session["messages"][-max_messages:]
                session["updatedAt"] = datetime.now(timezone.utc).isoformat()
                if session_updates:
                    for key, value in session_updates.items():
                        if value is None:
                            session.pop(key, None)
                        else:
                            session[key] = value
                updated_session = session
                break
            if updated_session is None:
                return None
            self._save_sessions(sessions)
            return updated_session

    def update_session(self, session: JsonDict) -> JsonDict:
        session_id = session.get("id")
        if not isinstance(session_id, str):
            raise ValueError("Session must include id")
        with self._lock:
            sessions = self._load_sessions()
            replaced = False
            for idx, existing in enumerate(sessions):
                if existing.get("id") == session_id:
                    sessions[idx] = session
                    replaced = True
                    break
            if not replaced:
                sessions.append(session)
            self._save_sessions(sessions)
        return session
