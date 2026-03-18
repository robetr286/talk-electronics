import os
from pathlib import Path


def test_ocr_eval_ci_count():
    """Verify that `ocr_eval/ci` contains at least the expected number of JSON examples.

    Behavior:
    - Reads expected count from env var `OCR_EVAL_CI_COUNT` (default 20).
    - Asserts that the number of `*.json` files in `ocr_eval/ci` is >= expected.

    The test is intentionally permissive (>=) to allow CI to be flexible; set the env var to a smaller
    number locally when you have fewer samples (e.g., OCR_EVAL_CI_COUNT=1 pytest -q tests/test_ocr_eval_ci.py).
    """
    expected = int(os.environ.get("OCR_EVAL_CI_COUNT", "18"))
    ci_dir = Path("ocr_eval") / "ci"
    files = list(ci_dir.glob("*.json"))
    assert len(files) >= expected, f"Expected at least {expected} json files in {ci_dir}, found {len(files)}"
