from __future__ import annotations

from pathlib import Path

import pytest

try:
    # talk_electronic.create_app imports Flask at top-level; in some CI gating
    # environments we intentionally avoid installing full runtime deps.
    # Import lazily and fall back to skipping fixtures/tests that require Flask.
    from talk_electronic import create_app
except Exception:  # ImportError / ModuleNotFoundError or other issues
    create_app = None


@pytest.fixture()
def app(tmp_path: Path):
    if create_app is None:
        pytest.skip("Flask / app factory not available in this environment")

    upload_dir = tmp_path / "uploads"
    config = {
        "TESTING": True,
        "UPLOAD_FOLDER": upload_dir,
        "AUTO_CLEAN_TEMP_ON_START": False,
        "IGNORE_REGIONS_TOKEN": "test-secret",
    }
    app = create_app(config)
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()
