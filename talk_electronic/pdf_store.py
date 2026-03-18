from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(slots=True)
class PdfDocument:
    """Metadata about an uploaded document (PDF or raster image)."""

    path: str
    total_pages: int
    name: str
    kind: str = "pdf"
    dpi: int | None = None
    width_px: int | None = None
    height_px: int | None = None


class PdfStore:
    """In-memory store mapping upload tokens to PDF metadata."""

    def __init__(self) -> None:
        self._store: Dict[str, PdfDocument] = {}

    def add(self, token: str, document: PdfDocument) -> None:
        self._store[token] = document

    def get(self, token: str) -> Optional[PdfDocument]:
        return self._store.get(token)

    def remove(self, token: str) -> None:
        self._store.pop(token, None)

    def clear(self) -> None:
        self._store.clear()
