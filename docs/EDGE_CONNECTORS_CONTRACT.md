# Edge connectors — kontrakt API i UI (minimalny)

## API (backend)

- Endpoint bazowy: `/api/edge-connectors`
- Autoryzacja: nagłówek `X-Edge-Token` (domyślnie), można skonfigurować przez `EDGE_CONNECTORS_HEADER`; token z `EDGE_CONNECTORS_TOKEN` (fallback na `IGNORE_REGIONS_TOKEN`).
- ID konektora: `edge-{uuid12}` (tworzone przez backend).
- Wzór pola `edgeId`: litera A/B/C/D + dwie cyfry, np. `A05`, `C12`.
- Wzór `page`: tekst zawierający numer 1–999, np. "2".
- Obsługiwane typy geometrii: `polygon`, `rect`, `polyline`; pole `geometry.points` musi zawierać ≥ 2 punkty.

### Tworzenie / aktualizacja
- `POST /api/edge-connectors`
- `PUT/PATCH /api/edge-connectors/{id}`
- Body JSON (minimalny kontrakt):
  ```json
  {
    "edgeId": "A05",
    "page": "2",
    "geometry": {"type": "polygon", "points": [[0,0],[120,0],[120,30],[0,30]]},
    "label": "J1",
    "netName": "VCC",
    "sheetId": "sheet-001",
    "historyId": "hist-123",
    "note": "lewy górny port",
    "source": {"type": "pdf", "filename": "schemat.pdf", "token": "...", "page": 2, "totalPages": 3, "previewUrl": "..."},
    "metadata": {"pageWidthPx": 2400, "pageHeightPx": 3200, "imageDpi": 300}
  }
  ```
- Walidacja: `edgeId` i `page` wymagane; `geometry.type` ∈ {polygon, rect, polyline}; `geometry.points` lista ≥ 2.

### Odczyt
- `GET /api/edge-connectors` — lista (bez payloadów). Parametr `includePayload=1` dołącza pełne payloady.
- `GET /api/edge-connectors/{id}` — pojedynczy wpis z payloadem.
- Pola odpowiedzi (skrócone):
  ```json
  {
    "id": "edge-abc123",
    "edgeId": "A05",
    "page": "2",
    "label": "J1",
    "note": "...",
    "sheetId": "sheet-001",
    "netName": "VCC",
    "historyId": "hist-123",
    "source": {"type": "pdf", "filename": "schemat.pdf", "page": 2, "token": "..."},
    "metadata": {"pageWidthPx": 2400, "pageHeightPx": 3200, "imageDpi": 300},
    "createdAt": "2026-01-04T12:34:56.789Z",
    "updatedAt": "2026-01-04T12:34:56.789Z",
    "storage": {"json": "uploads/edge-connectors/entries/edge-abc123.json"},
    "payload": { ... } // tylko gdy includePayload=1 lub GET /{id}
  }
  ```

### Usuwanie
- `DELETE /api/edge-connectors/{id}` — wymaga tokenu, usuwa wpis i jego payload.

## UI (frontend)

- Pliki: `static/js/edgeConnectors.js` (formularz CRUD, lista), zakładka "Łączenie schematów" w `templates/index.html`.
- Autoryzacja w UI: token pobierany z `window.EDGE_CONNECTORS_TOKEN` lub `localStorage` pod kluczem `app:edgeConnectorsToken`; nagłówek ustawia `edgeConnectors.js` (`X-Edge-Token` lub nadpisany z `window.EDGE_CONNECTORS_HEADER`).
- Formularz zapisuje/edytuje pola: `edgeId`, `page`, `label`, `netName`, `sheetId`, `historyId`, `note`, `geometry` (JSON), `metadata/source` z kontekstu PDF jeśli dostępny.
- Lista sortowana po `updatedAt/createdAt`, umożliwia edycję/usuwanie, podgląd JSON szczegółów i kopiowanie.
- Integracja z netlistą (już w kodzie): `lineSegmentation.js` przekazuje `edgeConnectorHistoryId` do `/api/segment/netlist`; `tests/test_netlist_generation.py` sprawdza obecność `metadata.edgeConnectors` w odpowiedzi netlisty.

## Mock / testowanie UI

- Aby testować bez modelu: można podać ręcznie payload w formularzu i zapisać; lista i podgląd działają w oparciu o zapisane wpisy.
- Żeby szybko zobaczyć marker na obrazie, można zasilić frontend przykładowymi punktami (patrz `DEFAULT_GEOMETRY_TEMPLATE` w `edgeConnectors.js`) i później rozbudować o rysowanie na canvasie, gdy flow detekcji będzie gotowy.
