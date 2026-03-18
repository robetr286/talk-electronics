# Kontrakt API: edge connectors i netlista

Zakres: opis aktualnych endpointow backendu dla konektorow krawedziowych oraz netlisty (budowanie, eksport SPICE), wraz z wymaganiami payloadow i kodami bledow.

## Autoryzacja
- Mutacje konektorow (/api/edge-connectors POST/PUT/PATCH/DELETE) wymagaja tokenu konfigurowanego w `EDGE_CONNECTORS_TOKEN` (fallback `IGNORE_REGIONS_TOKEN`).
- Naglowek domyslny: `X-Edge-Token`; akceptowane rowniez `Authorization: Bearer <token>` lub `X-Api-Key`.

## Edge connectors
Endpoint: `/api/edge-connectors`

### Schema payloadu (POST/PUT/PATCH)
- `edgeId` (string, wymagane): regex `^[ABCD][0-9]{2}$` (np. A01, D12).
- `page` (string, wymagane): liczba 1-999 w postaci tekstu.
- `geometry` (dict, wymagane):
  - `type`: `polygon` | `rect` | `polyline`.
  - `points`: lista co najmniej 2 punktow `[x, y, ...]` (liczby, rzutowane do int).
- `label` (string, opcjonalne): domyslnie `edgeId`.
- `note`, `sheetId`, `netName`, `historyId` (opcjonalne, string).
- `source` (dict, opcjonalne): kontekst pliku/preview (np. token, filename).
- `metadata` (dict, opcjonalne): dowolne metadane; jesli brak `roi_abs/roi`, backend dolicza ROI z geometrii.

### Walidacje
- Bledne pola -> `400 INVALID_CONNECTOR` ([talk_electronic/routes/edge_connectors.py](talk_electronic/routes/edge_connectors.py#L58-L115)).
- Brak uprawnien -> `403 FORBIDDEN` (sprawdzane przed mutacja).

### Operacje
- `GET /api/edge-connectors/`: lista entries (bez payloadow; `includePayload=1` dodaje payload). Zwraca `storageUrls.json` do pobrania pliku.
- `GET /api/edge-connectors/<id>`: pojedynczy rekord + payload.
- `POST /api/edge-connectors/`: tworzy `edge-<uuid>`, zapisuje payload do `uploads/edge-connectors/entries/<id>.json` i indeks.
- `PUT/PATCH /api/edge-connectors/<id>`: nadpisuje payload + indeks, zachowuje `createdAt` (lub ustawia, gdy brak).
- `DELETE /api/edge-connectors/<id>`: usuwa indeks i plik payload; brak rekordu -> `404 CONNECTOR_NOT_FOUND`.

### Detekcja pomocnicza
- `GET /api/edge-connectors/detect?page=<n>&token=<token>&shrink=0..0.15`
  - Jesli znajdzie plik `{token}_page_{page}.png|jpg|jpeg` lub `{token}_source.*` w `UPLOAD_FOLDER`, uruchamia prosty detektor konturow.
  - Wynik: `items` z polygonem/rect, `reason` (np. heuristic, mask_bbox, full_image_bbox, no_contours, no_image), `debug` (rozmiar, liczba konturow, shrink).
  - Fallback: deterministyczny mock z `geometry rect 10x40`.

### ROI z geometrii
- Backend wylicza bounding box z `geometry.points` jako `metadata.roi_abs` gdy pole nie istnieje ([talk_electronic/routes/edge_connectors.py](talk_electronic/routes/edge_connectors.py#L121-L168)).

## Netlista
Endpointy pod `/api/segment` ([talk_electronic/routes/segment.py](talk_electronic/routes/segment.py#L83-L362), [talk_electronic/routes/segment.py](talk_electronic/routes/segment.py#L520-L648)).

### POST /api/segment/netlist
- Wymagane: `lines` (dict wynik `LineDetectionResult.to_dict()`) **lub** `historyId` wskazujace zapisany wynik segmentacji.
- Opcjonalne: `symbolHistoryId` lub `symbols` (inline dict), `edgeConnectorHistoryId` (string), `storeHistory` (bool), `symbolDetections` alias.
- Walidacje: brak payloadu -> `400 INVALID_PAYLOAD`; brak linii -> `400 NO_LINES`; brak lines/historyId -> `400 MISSING_LINES`; brak historii -> `404 SEGMENT_HISTORY_NOT_FOUND`; blad odczytu pliku -> `404/500` zgodnie z kodami z backendu.
- Dzialanie: buduje `NetlistResult` (nodes, edges, metadata) i dopina metadane z symboli oraz konektorow (ponizej).
- Odpowiedz 200: `{ "netlist": NetlistResult }` + opcjonalne `historyEntry` gdy `storeHistory=true` (zapis do processed/segments).

#### Format NetlistResult
- `nodes[]`: `id`, `label` (N001..), `position (x,y)`, `degree`, `attached_segments[]`, `neighbors[]`, `classification` (essential/non_essential/endpoint/isolated/unspecified), `is_essential`, `net_label` (NET001..).
- `edges[]`: `id`, `source`, `target`, `length`, `angle_deg`.
- `metadata`: m.in. `connected_components`, `cycles`, `skipped_segments`, `node_labels` (map id->label), `net_labels` (nodeId->NETxxx), histogram stopni, `netlist` (lista linii WIRE...), `source` (historyId/label), `symbols` (opcjonalnie), `edgeConnectors` (opcjonalnie), klasyfikacje wezlow.

#### Dolaczanie symboli
- Jesli `symbols` inline lub `symbolHistoryId`, wstawiane do `metadata.symbols` z polami `count`, `detector`, `summary`, `detections`, `historyId`, `source`.

#### Dolaczanie edge connectors
- Backend szuka `historyCandidates` na podstawie: `historyId` segmentacji, `edgeConnectorHistoryId`, `metadata.historyId/id` w payloadzie linii, `source.historyId/id` i `netlist.metadata.source.*`.
- Dla kazdego dopasowanego `historyId` pobiera wpisy z `EdgeConnectorStore` i dopina do `metadata.edgeConnectors` jako `items` (pelny payload z ROI), `count`, `pages`, `edgeIds`, pierwszy `historyId` uzyty.

### POST /api/segment/netlist/spice
- Wymagane: `netlist` (dict NetlistResult) **lub** `historyId` zapisanej netlisty.
- Komponenty: `components`/`componentAssignments`/`assignments` (lista dict) parsowane do instancji SPICE; bledy walidacji -> `400 INVALID_COMPONENTS`.
- Tytul: `title` (opcjonalnie, fallback z metadata.source.label/id); `groundAlias` domyslnie `0`.
- Walidacja SPICE: ostrzezenia w `metadata.warnings`; bledy -> `400 SPICE_COMPONENT_ERRORS` lub `400 SPICE_GENERATION_ERROR` gdy generator odrzuci dane.
- Odpowiedz 200: `spice` (tekst), `metadata` (title, componentCount, groundAlias, source, warnings) + `historyEntry` gdy `storeHistory=true` (plik cir w processed/spice).

## Kody bledow (wybrane)
- Konektory: `INVALID_CONNECTOR` (400), `CONNECTOR_NOT_FOUND` (404), `FORBIDDEN` (403).
- Netlista: `INVALID_PAYLOAD`, `MISSING_LINES`, `SEGMENT_HISTORY_NOT_FOUND`, `SEGMENT_FILE_MISSING`, `SEGMENT_FILE_READ_ERROR`, `NO_LINES`, `INVALID_NETLIST`, `INVALID_COMPONENTS`, `SPICE_COMPONENT_ERRORS`, `SPICE_GENERATION_ERROR` (400/404/500 zalezne od zrodla).

## Przyklady

### Utworzenie konektora
```json
POST /api/edge-connectors/
{
  "edgeId": "A01",
  "page": "1",
  "geometry": {"type": "rect", "points": [[10,10],[60,10],[60,40],[10,40]]},
  "historyId": "lines-123",
  "source": {"token": "abc", "file": "abc_page_1.png"},
  "metadata": {"note": "prawa gora"}
}
```

### Budowa netlisty z historii + konektory
```json
POST /api/segment/netlist
{
  "historyId": "lines-123",
  "edgeConnectorHistoryId": "lines-123",
  "symbolHistoryId": "symbols-789",
  "storeHistory": true
}
```
Odpowiedz zawiera `netlist.nodes/edges`, `metadata.edgeConnectors.items[*].geometry/metadata.roi_abs`, oraz opcjonalny `historyEntry` z zapisanym plikiem netlisty.

### Eksport SPICE
```json
POST /api/segment/netlist/spice
{
  "historyId": "netlist-456",
  "components": [
    {"ref": "R1", "type": "resistor", "nodes": ["N001", "N002"], "value": "10k"},
    {"ref": "V1", "type": "vsource", "nodes": ["N000", "N001"], "value": "5"}
  ],
  "groundAlias": "0"
}
```
