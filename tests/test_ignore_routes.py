from __future__ import annotations

from pathlib import Path

import pytest

TOKEN_HEADERS = {"X-Ignore-Token": "test-secret"}


@pytest.mark.usefixtures("client")
def test_ignore_regions_crud(app, client):
    payload = {
        "objects": [
            {"type": "rect", "points": [[10, 10], [50, 40]]},
            {
                "type": "poly",
                "points": [[60, 60], [80, 60], [80, 90], [60, 90]],
            },
            {
                "type": "brush",
                "points": [[100, 100], [110, 105], [120, 110]],
                "brushSize": 12,
            },
        ],
        "imageShape": [200, 200],
        "source": {"kind": "pdf", "id": "doc-1", "label": "PDF page 1"},
        "image": {"filename": "page1.png", "url": "/uploads/page1.png"},
        "label": "PDF page 1",
    }

    response = client.post("/api/ignore-regions", json=payload, headers=TOKEN_HEADERS)
    assert response.status_code == 201
    entry = response.get_json()["entry"]
    assert entry["counts"]["objects"] == 3
    assert entry["counts"]["regions"] == 3

    json_rel = entry["storage"]["json"]
    assert isinstance(json_rel, str)
    json_path = Path(app.config["UPLOAD_FOLDER"]) / json_rel
    assert json_path.exists()

    stored_data = json_path.read_text(encoding="utf-8")
    assert "ignore_regions" in stored_data

    list_response = client.get("/api/ignore-regions")
    assert list_response.status_code == 200
    items = list_response.get_json()["items"]
    assert len(items) == 1
    assert "objects" not in items[0]

    list_response_full = client.get("/api/ignore-regions?includePayload=1")
    items_full = list_response_full.get_json()["items"]
    assert "objects" in items_full[0]

    entry_id = entry["id"]
    detail = client.get(f"/api/ignore-regions/{entry_id}")
    assert detail.status_code == 200
    detail_entry = detail.get_json()["entry"]
    assert len(detail_entry["objects"]) == 3

    update_payload = {
        "objects": [
            {
                "type": "poly",
                "points": [[5, 5], [40, 5], [40, 20], [5, 20]],
            }
        ],
        "imageShape": [200, 200],
        "label": "Zaktualizowana strefa",
    }

    update_resp = client.put(
        f"/api/ignore-regions/{entry_id}",
        json=update_payload,
        headers=TOKEN_HEADERS,
    )
    assert update_resp.status_code == 200
    updated_entry = update_resp.get_json()["entry"]
    assert updated_entry["counts"]["regions"] == 1
    assert updated_entry["label"] == "Zaktualizowana strefa"
    assert updated_entry["updatedAt"] != updated_entry["createdAt"]

    delete_resp = client.delete(f"/api/ignore-regions/{entry_id}", headers=TOKEN_HEADERS)
    assert delete_resp.status_code == 200
    assert client.get("/api/ignore-regions").get_json()["count"] == 0
    assert not json_path.exists()


def test_ignore_regions_permission_required(client):
    payload = {
        "objects": [{"type": "rect", "points": [[0, 0], [10, 10]]}],
        "imageShape": [10, 10],
    }
    response = client.post("/api/ignore-regions", json=payload)
    assert response.status_code == 403


def test_ignore_regions_validation_errors(client):
    bad_payload = {"objects": [], "imageShape": [0, 0]}
    response = client.post("/api/ignore-regions", json=bad_payload, headers=TOKEN_HEADERS)
    assert response.status_code == 400
    assert "wymagane" in response.get_json()["error"]


def test_ignore_region_artifacts_accessible_via_storage_urls(app, client):
    payload = {
        "objects": [
            {"type": "rect", "points": [[5, 5], [25, 25]]},
            {
                "type": "poly",
                "points": [[30, 10], [50, 10], [50, 30], [30, 30]],
            },
        ],
        "imageShape": [64, 64],
    }

    response = client.post("/api/ignore-regions", json=payload, headers=TOKEN_HEADERS)
    assert response.status_code == 201
    entry = response.get_json()["entry"]

    storage = entry.get("storage", {})
    mask_rel = storage.get("mask")
    json_rel = storage.get("json")
    assert isinstance(mask_rel, str) and mask_rel.endswith(".png")
    assert isinstance(json_rel, str) and json_rel.endswith(".json")

    urls = entry.get("storageUrls", {})
    mask_url = urls.get("mask")
    json_url = urls.get("json")
    assert isinstance(mask_url, str)
    assert isinstance(json_url, str)

    mask_response = client.get(mask_url)
    assert mask_response.status_code == 200
    assert mask_response.data.startswith(b"\x89PNG")

    json_response = client.get(json_url)
    assert json_response.status_code == 200
    assert b"ignoreRegions" in json_response.data or b"ignore_regions" in json_response.data

    upload_folder: Path = app.config["UPLOAD_FOLDER"]
    assert (upload_folder / mask_rel).exists()
    assert (upload_folder / json_rel).exists()
