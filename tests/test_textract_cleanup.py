"""Testy weryfikujące poprawność usunięcia martwego kodu Textract.

Sprawdzają:
1. Brak importu/rejestracji textract_bp w aplikacji Flask
2. Brak pliku talk_electronic/routes/textract.py
3. Brak plików testowych Textract
4. Brak plików skryptów Textract
5. Domyślne ścieżki w ocr_corrections.py wskazują na 'paddle', nie 'textract'
6. Endpointy /ocr/textract nie istnieją w aplikacji
7. Endpoint /ocr/paddle istnieje i odpowiada
"""

import importlib
import inspect
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1. Pliki martwego kodu nie istnieją
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel_path", [
    "talk_electronic/routes/textract.py",
    "tests/test_textract_integration.py",
    "tests/test_textract_limits.py",
    "tests/test_textract_corrections.py",
    "tests/test_textract_cd138_fixes.py",
    "tests/test_textract_bcc6f638_fixes.py",
    "scripts/textract_eval.py",
    "scripts/textract_make_gt_overlays.py",
])
def test_textract_file_deleted(rel_path):
    """Plik martwego kodu Textract nie powinien już istnieć."""
    assert not (PROJECT_ROOT / rel_path).exists(), (
        f"Plik {rel_path} nadal istnieje — powinien być usunięty."
    )


# ---------------------------------------------------------------------------
# 2. __init__.py nie importuje textract_bp
# ---------------------------------------------------------------------------

def test_init_py_no_textract_import():
    """__init__.py nie powinien zawierać importu textract_bp."""
    init_path = PROJECT_ROOT / "talk_electronic" / "__init__.py"
    content = init_path.read_text(encoding="utf-8")
    assert "textract_bp" not in content, (
        "__init__.py nadal zawiera 'textract_bp' — usuń import i register_blueprint."
    )
    assert "routes.textract" not in content, (
        "__init__.py nadal importuje z routes.textract."
    )


# ---------------------------------------------------------------------------
# 3. Domyślne ścieżki w ocr_corrections używają 'paddle'
# ---------------------------------------------------------------------------

def test_ocr_corrections_default_path_is_paddle():
    """Domyślne ścieżki w load_all_corrections i summarize_corrections
    powinny wskazywać na reports/paddle/corrections."""
    from talk_electronic import ocr_corrections

    load_sig = inspect.signature(ocr_corrections.load_all_corrections)
    load_default = str(load_sig.parameters["directory"].default)
    assert "paddle" in load_default, (
        f"load_all_corrections domyślna ścieżka to '{load_default}', "
        "oczekiwano ścieżki zawierającej 'paddle'."
    )
    assert "textract" not in load_default, (
        f"load_all_corrections nadal wskazuje na 'textract': '{load_default}'"
    )

    summ_sig = inspect.signature(ocr_corrections.summarize_corrections)
    summ_default = str(summ_sig.parameters["directory"].default)
    assert "paddle" in summ_default, (
        f"summarize_corrections domyślna ścieżka to '{summ_default}', "
        "oczekiwano ścieżki zawierającej 'paddle'."
    )
    assert "textract" not in summ_default, (
        f"summarize_corrections nadal wskazuje na 'textract': '{summ_default}'"
    )


# ---------------------------------------------------------------------------
# 4. Moduł textract nie jest zaimportowany w uruchomionej aplikacji
# ---------------------------------------------------------------------------

def test_textract_module_not_in_sys_modules(app):
    """Po uruchomieniu aplikacji moduł routes.textract nie powinien być
    obecny w sys.modules."""
    from talk_electronic import create_app  # noqa: F401 — import side-effects już wykonane
    for key in sys.modules:
        assert "routes.textract" not in key, (
            f"Moduł textract nadal widoczny w sys.modules: {key}"
        )


# ---------------------------------------------------------------------------
# 5. Endpointy /ocr/textract nie istnieją w aplikacji
# ---------------------------------------------------------------------------

def test_textract_endpoints_not_registered(app):
    """Endpointy /ocr/textract i /ocr/textract/corrections nie powinny
    być zarejestrowane w aplikacji Flask."""
    client = app.test_client()

    resp_post = client.post("/ocr/textract")
    assert resp_post.status_code == 404, (
        f"POST /ocr/textract zwrócił {resp_post.status_code}, oczekiwano 404."
    )

    resp_corr = client.post("/ocr/textract/corrections")
    assert resp_corr.status_code == 404, (
        f"POST /ocr/textract/corrections zwrócił {resp_corr.status_code}, oczekiwano 404."
    )


# ---------------------------------------------------------------------------
# 6. Endpoint /ocr/paddle jest zarejestrowany (nie zwraca 404)
# ---------------------------------------------------------------------------

def test_paddle_endpoint_registered(app):
    """POST /ocr/paddle powinien być zarejestrowany — nie może zwracać 404."""
    client = app.test_client()
    # Wysyłamy puste żądanie — oczekujemy błędu walidacji (400/422), ale nie 404
    resp = client.post("/ocr/paddle", data={}, content_type="multipart/form-data")
    assert resp.status_code != 404, (
        "POST /ocr/paddle zwrócił 404 — blueprint paddleocr_bp nie jest zarejestrowany."
    )

    resp_corr = client.post(
        "/ocr/paddle/corrections",
        data="{}",
        content_type="application/json",
    )
    assert resp_corr.status_code != 404, (
        "POST /ocr/paddle/corrections zwrócił 404 — endpoint nie jest zarejestrowany."
    )


# ---------------------------------------------------------------------------
# 7. summarize_ocr_corrections.py używa ścieżki 'paddle'
# ---------------------------------------------------------------------------

def test_summarize_script_uses_paddle_path():
    """Skrypt scripts/summarize_ocr_corrections.py powinien wskazywać
    na reports/paddle/corrections, nie reports/textract/corrections."""
    script_path = PROJECT_ROOT / "scripts" / "summarize_ocr_corrections.py"
    content = script_path.read_text(encoding="utf-8")
    assert "paddle" in content, (
        "scripts/summarize_ocr_corrections.py nie zawiera ścieżki 'paddle'."
    )
    assert "textract" not in content, (
        "scripts/summarize_ocr_corrections.py nadal zawiera odwołanie do 'textract'."
    )


# ---------------------------------------------------------------------------
# 8. ocr_tab.spec.js używa poprawnych URL-i mock
# ---------------------------------------------------------------------------

def test_e2e_spec_uses_paddle_mocks():
    """tests/e2e/ocr_tab.spec.js powinien mockować /ocr/paddle,
    nie /ocr/textract."""
    spec_path = PROJECT_ROOT / "tests" / "e2e" / "ocr_tab.spec.js"
    content = spec_path.read_text(encoding="utf-8")
    assert "**/ocr/paddle'" in content or '**/ocr/paddle"' in content, (
        "ocr_tab.spec.js nie zawiera mocka dla /ocr/paddle."
    )
    assert "**/ocr/textract'" not in content and '**/ocr/textract"' not in content, (
        "ocr_tab.spec.js nadal mockuje /ocr/textract — zmień na /ocr/paddle."
    )
