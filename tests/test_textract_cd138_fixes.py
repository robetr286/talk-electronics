import sys
import types

# Provide lightweight stubs for heavy optional imports used by the
# textract module so these unit tests can run in isolation.
if "boto3" not in sys.modules:
    sys.modules["boto3"] = types.SimpleNamespace()
# Provide a minimal 'botocore' package with a 'config' submodule so
# `from botocore.config import Config` succeeds during import.
if "botocore" not in sys.modules:
    botocore_pkg = types.ModuleType("botocore")
    botocore_pkg.exceptions = types.SimpleNamespace(BotoCoreError=Exception)
    sys.modules["botocore"] = botocore_pkg
    cfg_mod = types.ModuleType("botocore.config")
    cfg_mod.Config = lambda *a, **k: None
    sys.modules["botocore.config"] = cfg_mod

from talk_electronic.routes.textract import _merge_value_unit_suffix, _pair_components_to_values


def _bbox(cx, cy, w=10, h=10):
    return (cx - w / 2, cy - h / 2, w, h)


def test_merge_value_unit_suffix_merges_leading_digit():
    tokens = [
        {"text": "1", "confidence": 95.0, "bbox": _bbox(14, 15), "center": (14, 15), "category": "value"},
        {"text": ".2K", "confidence": 90.0, "bbox": _bbox(34, 15, 20, 10), "center": (34, 15), "category": "value"},
    ]

    out = _merge_value_unit_suffix(tokens)
    texts = [t["text"] for t in out]
    assert "1.2K" in texts
    assert "1" not in texts and ".2K" not in texts


def test_combine_vertical_values_normalises_01_47_for_capacitor():
    # C-component above a value token that textract read as '01/47'
    comp = {"text": "C403", "confidence": 98.0, "bbox": _bbox(120, 100), "center": (120, 100), "category": "component"}
    val = {
        "text": "01/47",
        "confidence": 92.0,
        "bbox": _bbox(120, 120, 30, 10),
        "center": (120, 120),
        "category": "value",
    }

    tokens = [comp, val]
    pairs = _pair_components_to_values(tokens)
    assert len(pairs) == 1
    assert pairs[0]["component"] == "C403"
    # Heuristic should rewrite "01/47" -> "47/10" for capacitors
    assert pairs[0]["value"] == "47/10"


def test_pair_components_to_values_semicon_threshold():
    comp = {"text": "Q1", "confidence": 98.0, "bbox": _bbox(100, 100), "center": (100, 100), "category": "component"}
    # passive value (initially chosen)
    passive = {"text": "47u", "confidence": 92.0, "bbox": _bbox(120, 100), "center": (120, 100), "category": "value"}
    # semicon placed further away (should NOT be chosen)
    semi_far = {
        "text": "2SA933",
        "confidence": 90.0,
        "bbox": _bbox(125, 100),
        "center": (125, 100),
        "category": "value",
    }
    # semicon very close (should be chosen)
    semi_near = {
        "text": "2SC123",
        "confidence": 90.0,
        "bbox": _bbox(103, 100),
        "center": (103, 100),
        "category": "value",
    }

    # Case A: semi_far is not closer -> passive remains
    tokens_a = [comp, passive, semi_far]
    pairs_a = _pair_components_to_values(tokens_a)
    assert pairs_a[0]["value"] == "47u"

    # Case B: semi_near is significantly closer -> semicon chosen
    tokens_b = [comp, passive, semi_near]
    pairs_b = _pair_components_to_values(tokens_b)
    assert pairs_b[0]["value"] == "2SC123"
