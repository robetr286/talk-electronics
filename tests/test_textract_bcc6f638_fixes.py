"""Tests for bcc6f638 postprocessing fixes (P25a-P25e).

Covers:
  P25a – Merge capacitor value/voltage (47 + 16 → 47/16)
  P25b – Merge split semiconductor prefix (2S + C1740 → 2SC1740)
  P25b-2 – Restore lost prefix near Q (C1740 → 2SC1740)
  P25c – Extend truncated designators (C41 → C411)
  P25d – Reject passive values for Q/D (Q418 ≠ 0.068)
  P25e – Fix IC OCR confusion (IC40B → IC408)
"""

import sys
import types

# Stub heavy optional imports
if "boto3" not in sys.modules:
    sys.modules["boto3"] = types.SimpleNamespace()
if "botocore" not in sys.modules:
    botocore_pkg = types.ModuleType("botocore")
    botocore_pkg.exceptions = types.SimpleNamespace(BotoCoreError=Exception)
    sys.modules["botocore"] = botocore_pkg
    cfg_mod = types.ModuleType("botocore.config")
    cfg_mod.Config = lambda *a, **k: None
    sys.modules["botocore.config"] = cfg_mod

from talk_electronic.routes.textract import (
    _extend_truncated_designators,
    _fix_semicon_fragments,
    _pair_components_to_values,
)


def _bbox(cx, cy, w=10, h=10):
    return (cx - w / 2, cy - h / 2, w, h)


# ── P25a: capacitor value/voltage merge ─────────────────────────────────


def test_combine_capacitor_value_voltage_47_16():
    """C413 with separate '47' and '16' tokens → paired value '47/16'."""
    comp = {
        "text": "C413",
        "confidence": 98.0,
        "bbox": _bbox(200, 100, 30, 12),
        "center": (200, 100),
        "category": "component",
    }
    val_47 = {
        "text": "47",
        "confidence": 94.0,
        "bbox": _bbox(200, 118, 14, 10),
        "center": (200, 118),
        "category": "value",
    }
    val_16 = {
        "text": "16",
        "confidence": 93.0,
        "bbox": _bbox(200, 132, 14, 10),
        "center": (200, 132),
        "category": "value",
    }

    tokens = [comp, val_47, val_16]
    pairs = _pair_components_to_values(tokens)

    c413_pairs = [p for p in pairs if p["component"] == "C413"]
    assert len(c413_pairs) == 1
    assert c413_pairs[0]["value"] == "47/16"


# ── P25b: merge split semiconductor prefix ──────────────────────────────


def test_merge_semicon_prefix_2S_C1740():
    """'2S' + 'C1740' nearby → merged '2SC1740' (value)."""
    prefix_tok = {
        "text": "2S",
        "confidence": 80.0,
        "bbox": _bbox(300, 200, 12, 10),
        "center": (300, 200),
        "category": "net_label",
    }
    body_tok = {
        "text": "C1740",
        "confidence": 92.0,
        "bbox": _bbox(316, 200, 30, 10),
        "center": (316, 200),
        "category": "component",
    }

    tokens = [prefix_tok, body_tok]
    result = _fix_semicon_fragments(tokens)

    texts = [t["text"] for t in result]
    assert "2SC1740" in texts
    # merged token should be a value
    merged = [t for t in result if t["text"] == "2SC1740"][0]
    assert merged["category"] == "value"
    # originals should be gone
    assert "2S" not in texts
    assert "C1740" not in texts


# ── P25b-2: restore lost prefix near Q ──────────────────────────────────


def test_restore_lost_prefix_C1740_near_Q():
    """'C1740' near Q418 → reclassified as '2SC1740' (value)."""
    q_tok = {
        "text": "Q418",
        "confidence": 97.0,
        "bbox": _bbox(300, 180, 30, 12),
        "center": (300, 180),
        "category": "component",
    }
    body_tok = {
        "text": "C1740",
        "confidence": 92.0,
        "bbox": _bbox(300, 200, 30, 10),
        "center": (300, 200),
        "category": "component",
    }

    tokens = [q_tok, body_tok]
    result = _fix_semicon_fragments(tokens)

    merged = [t for t in result if t["text"] == "2SC1740"]
    assert len(merged) == 1
    assert merged[0]["category"] == "value"


# ── P25c: extend truncated designators ───────────────────────────────────


def test_extend_C41_to_C411():
    """C41 + standalone '1' below → extended to C411."""
    comp = {
        "text": "C41",
        "confidence": 95.0,
        "bbox": _bbox(100, 50, 10, 30),
        "center": (100, 50),
        "category": "component",
    }
    digit = {
        "text": "1",
        "confidence": 88.0,
        "bbox": _bbox(100, 72, 8, 10),
        "center": (100, 72),
        "category": "other",
    }

    tokens = [comp, digit]
    result = _extend_truncated_designators(tokens)

    comps = [t for t in result if t.get("category") == "component"]
    assert len(comps) == 1
    assert comps[0]["text"] == "C411"
    # digit token should be consumed
    assert len(result) == 1


# ── P25d: reject passive values for Q/D ──────────────────────────────────


def test_q_rejects_passive_decimal_value():
    """Q418 should NOT pair with '0.068' (passive capacitor value)."""
    q_comp = {
        "text": "Q418",
        "confidence": 98.0,
        "bbox": _bbox(200, 200, 30, 12),
        "center": (200, 200),
        "category": "component",
    }
    passive_val = {
        "text": "0.068",
        "confidence": 94.0,
        "bbox": _bbox(200, 220, 30, 10),
        "center": (200, 220),
        "category": "value",
    }

    tokens = [q_comp, passive_val]
    pairs = _pair_components_to_values(tokens)

    q_pairs = [p for p in pairs if p["component"] == "Q418"]
    # Q418 should NOT be paired with passive value
    assert len(q_pairs) == 0 or q_pairs[0]["value"] != "0.068"


def test_q_prefers_semi_over_passive_with_relaxed_threshold():
    """Q picks semiconductor even if passive is slightly closer."""
    q_comp = {
        "text": "Q418",
        "confidence": 98.0,
        "bbox": _bbox(200, 200, 30, 12),
        "center": (200, 200),
        "category": "component",
    }
    # passive slightly closer
    passive_val = {
        "text": "0.068",
        "confidence": 94.0,
        "bbox": _bbox(205, 216, 30, 10),
        "center": (205, 216),
        "category": "value",
    }
    # semi model a bit farther (within 1.5× distance)
    semi_val = {
        "text": "2SC1740",
        "confidence": 90.0,
        "bbox": _bbox(210, 222, 40, 10),
        "center": (210, 222),
        "category": "value",
    }

    tokens = [q_comp, passive_val, semi_val]
    pairs = _pair_components_to_values(tokens)

    q_pairs = [p for p in pairs if p["component"] == "Q418"]
    assert len(q_pairs) == 1
    assert q_pairs[0]["value"] == "2SC1740"


def test_c_still_gets_passive_value():
    """C412 should still pair with '0.068' (passive value is correct for C)."""
    c_comp = {
        "text": "C412",
        "confidence": 98.0,
        "bbox": _bbox(200, 200, 30, 12),
        "center": (200, 200),
        "category": "component",
    }
    passive_val = {
        "text": "0.068",
        "confidence": 94.0,
        "bbox": _bbox(200, 220, 30, 10),
        "center": (200, 220),
        "category": "value",
    }

    tokens = [c_comp, passive_val]
    pairs = _pair_components_to_values(tokens)

    c_pairs = [p for p in pairs if p["component"] == "C412"]
    assert len(c_pairs) == 1
    assert c_pairs[0]["value"] == "0.068"


# ---- P25e: IC OCR confusion fix -------------------------------------------


class TestFixICOCRConfusion:
    """P25e – Fix trailing letter→digit OCR confusion in IC designators."""

    def test_ic40b_becomes_ic408(self):
        """IC40B (B misread as 8) → IC408, recategorised as component."""
        from talk_electronic.routes.textract import _fix_ic_ocr_confusion

        tok = {
            "text": "IC40B",
            "confidence": 90.0,
            "bbox": _bbox(850, 390, 70, 18),
            "center": (885, 399),
            "category": "net_label",
        }
        result = _fix_ic_ocr_confusion([tok])
        assert result[0]["text"] == "IC408"
        assert result[0]["category"] == "component"

    def test_ic_already_correct_unchanged(self):
        """IC407 (already correct) stays unchanged."""
        from talk_electronic.routes.textract import _fix_ic_ocr_confusion

        tok = {
            "text": "IC407",
            "confidence": 95.0,
            "bbox": _bbox(100, 100, 60, 18),
            "center": (130, 109),
            "category": "component",
        }
        result = _fix_ic_ocr_confusion([tok])
        assert result[0]["text"] == "IC407"
        assert result[0]["category"] == "component"

    def test_ic40b_not_paired_with_r458(self):
        """After IC40B→IC408 fix, R458 pairs with 100K only (not IC40B)."""
        from talk_electronic.routes.textract import _fix_ic_ocr_confusion, _pair_components_to_values

        r458 = {
            "text": "R458",
            "confidence": 92.0,
            "bbox": _bbox(898, 342, 58, 18),
            "center": (927, 351),
            "category": "component",
        }
        val_100k = {
            "text": "100K",
            "confidence": 91.0,
            "bbox": _bbox(898, 360, 55, 18),
            "center": (925, 369),
            "category": "value",
        }
        ic40b = {
            "text": "IC40B",
            "confidence": 88.0,
            "bbox": _bbox(853, 395, 72, 19),
            "center": (889, 404),
            "category": "net_label",
        }
        tokens = [r458, val_100k, ic40b]
        tokens = _fix_ic_ocr_confusion(tokens)
        pairs = _pair_components_to_values(tokens)

        r_pairs = [p for p in pairs if p["component"] == "R458"]
        assert len(r_pairs) == 1
        assert r_pairs[0]["value"] == "100K"

        ic_pairs = [p for p in pairs if p["component"] == "IC408"]
        # IC408 is a component — it shouldn't have a passive value paired
        assert len(ic_pairs) <= 1  # may or may not find a value
