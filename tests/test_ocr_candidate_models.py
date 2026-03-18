import importlib

import pytest


def try_import(names):
    for name in names:
        spec = importlib.util.find_spec(name)
        if spec is not None:
            return importlib.import_module(name)
    pytest.skip(f"None of the candidate packages found: {names}")


def test_doctr_importable():
    # DocTR / doctr
    mod = try_import(["doctr", "python_doctr", "doctr-models"])
    assert mod is not None


def test_surya_importable():
    # Try common package names for Surya OCR; skip if none available
    mod = try_import(["surya", "surya_ocr", "surya-ocr"])
    assert mod is not None


def test_easyocr_importable():
    mod = try_import(["easyocr"])  # easyocr.Reader
    assert mod is not None


def test_tesseract_importable():
    # pytesseract Python binding; tesseract binary should be present in PATH
    mod = try_import(["pytesseract"])  # skip if not installed
    assert mod is not None


def test_paddleocr_importable():
    mod = try_import(["paddleocr"])  # skip if not installed
    assert mod is not None
