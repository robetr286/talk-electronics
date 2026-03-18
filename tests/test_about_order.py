import pytest

from talk_electronic import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app({"UPLOAD_FOLDER": tmp_path})
    app.testing = True
    return app.test_client()


def test_about_entries_order(client):
    r = client.get("/")
    html = r.get_data(as_text=True)

    # Ensure Konserwacja appears in the document and date is present
    assert "🧹 Konserwacja" in html
    assert "2025-10-06" in html

    # Ensure segmentacja appears and date is present
    assert "📐 Segmentacja linii/węzłów" in html
    assert "2025-11-01" in html

    # Important check: Konserwacja block should occur before the 2025-11 block
    assert html.index("🧹 Konserwacja") < html.index("📐 Segmentacja linii/węzłów")

    # The 'Zmiany (historicznie)' summary should be placed at the end of the historical entries
    assert "🔔 Zmiany (historicznie)" in html
    # Ensure it appears after November sections
    assert html.index("🔔 Zmiany (historicznie)") > html.index("📐 Segmentacja linii/węzłów")
    assert html.index("🔔 Zmiany (historicznie)") > html.index("🔍 Detekcja symboli")


def test_about_rendered_from_data(client):
    # Load data file and check that entries are rendered in the same order
    from pathlib import Path

    import yaml

    project_root = Path(__file__).resolve().parents[1]
    data_file = project_root / "data" / "about_entries.yaml"
    assert data_file.exists(), "about_entries.yaml should exist"

    raw = yaml.safe_load(data_file.read_text(encoding="utf-8"))
    about_entries = raw.get("about_entries", [])

    r = client.get("/")
    html = r.get_data(as_text=True)

    # Ensure each title from data is present in the rendered HTML and appears in the same order
    indices = [html.index(entry["title"]) for entry in about_entries]
    assert indices == sorted(
        indices
    ), "About entries must be rendered in the same chronological order as data (oldest->newest)"
