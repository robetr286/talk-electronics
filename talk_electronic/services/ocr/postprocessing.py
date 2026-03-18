"""OCR token postprocessing for electronic schematics.

Migrated from textract.py — universal cleanup/merge/fix functions
that improve OCR accuracy regardless of OCR engine (Textract or PaddleOCR).

Pipeline:  raw tokens → clean text → drop noise → re-categorize
           → merge fragments → fix OCR confusions → deduplicate
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .pairing import categorize, SEMI_MODEL_RE
from .preprocessing import bbox_center

# ---------------------------------------------------------------------------
# Constants & regex patterns
# ---------------------------------------------------------------------------

# Ground-symbol noise: trailing "m" merged with value (e.g. "470Pm" → "470P")
_TRAILING_M_NOISE = re.compile(r"^(\d[\d.]*[PNFUKRΩ])[mM]$", re.IGNORECASE)

# Ohm misread as "s"/"S2" (e.g. "680Ks" → "680KΩ")
_TRAILING_OHM_NOISE = re.compile(r"^(\d[\d.]*[kKmMGg]?)(?:[sS]2?|[sS][23]?)$")

# Three-dot range → tilde (e.g. "10...30pF" → "10~30pF")
_THREE_DOTS = re.compile(r"\.{2,4}")

# Compound token: component + "=" + value (e.g. "R1=22K")
_COMPOUND_EQ = re.compile(r"^([A-Z]{1,3}\d*)=", re.IGNORECASE)

# Compound token WITHOUT "=": R46115K → R461 + 15K
_COMPOUND_NOEQ_COMP = re.compile(r"^(IC|[RCLQ])\d{2,3}$", re.IGNORECASE)
_COMPOUND_NOEQ_VAL = re.compile(r"^\d+[KMPRNUF]", re.IGNORECASE)

# Cyrillic → Latin transliteration
_CYRILLIC_TO_LATIN: Dict[str, str] = {
    "\u0410": "A", "\u0412": "B", "\u0421": "C", "\u0415": "E",
    "\u041D": "H", "\u041A": "K", "\u041C": "M", "\u041E": "O",
    "\u0420": "P", "\u0422": "T", "\u0425": "X",
    "\u0430": "a", "\u0441": "c", "\u0435": "e", "\u043E": "o",
    "\u0440": "p", "\u0442": "T", "\u0445": "x", "\u0443": "y",
}

_SUBSCRIPT_TO_NORMAL: Dict[str, str] = {
    "\u2090": "a", "\u2091": "e", "\u2092": "o", "\u2093": "x",
    "\u2095": "h", "\u2096": "k", "\u2097": "l", "\u2098": "m",
    "\u2099": "n", "\u209A": "p", "\u209B": "s", "\u209C": "t",
    "\u00B9": "1", "\u00B2": "2", "\u00B3": "3",
}

_TRANSLITERATION = str.maketrans({**_CYRILLIC_TO_LATIN, **_SUBSCRIPT_TO_NORMAL})

# Semiconductor fragment patterns
_SEMI_PREFIX_FRAGMENTS = {"2S", "2N", "1S", "1N", "1SS"}
_SEMI_BODY_RE = re.compile(r"^[ABCDJK]\d{3,4}[A-Z]{0,2}$", re.IGNORECASE)

# Unit suffixes for merge
_UNIT_SUFFIXES = {"K", "M", "G", "R", "P", "N", "F", "U"}
_MULTI_UNIT_SUFFIXES = {
    "kΩ", "KΩ", "MΩ", "GΩ", "Ω",
    "µF", "nF", "pF", "mF",
    "mV", "kV", "mA", "µA",
    "kg", "ks", "kQ", "Mg", "Ms", "MQ",
}

# IC OCR confusion: letter → digit
_IC_OCR_LETTER_TO_DIGIT: Dict[str, str] = {
    "B": "8", "O": "0", "S": "5", "I": "1", "Z": "2", "G": "6", "D": "0",
}


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def _split_compound_noeq(text: str) -> str | None:
    """Try to split 'R46115K' into 'R461' (returned) + '15K' (discarded)."""
    best = None
    for i in range(3, len(text) - 1):
        comp = text[:i]
        val = text[i:]
        if _COMPOUND_NOEQ_COMP.match(comp) and _COMPOUND_NOEQ_VAL.match(val):
            best = comp
    return best


def clean_token_text(text: str) -> str:
    """Remove known OCR artefacts from token text."""
    text = text.translate(_TRANSLITERATION)
    text = text.rstrip("\"'")

    # µ misread as ",L" / ",U" / ",Lit"
    text = re.sub(r",LF$", "µF", text, flags=re.IGNORECASE)
    text = re.sub(r",UF$", "µF", text, flags=re.IGNORECASE)
    text = re.sub(r",Lit$", "µF", text, flags=re.IGNORECASE)
    text = re.sub(r"(\d),([uU]F)$", r"\1µF", text)

    # Space between value and unit
    text = re.sub(r"^(\d+)\s+[uU]F$", r"\1µF", text)
    text = re.sub(r"^(\d+)\s+([KkMRPNFGpnΩ])$", r"\1\2", text)

    # Decimal-comma → dot
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)

    # Leading zero strip: "01" → "1"
    m_lz = re.match(r"^0(\d)$", text)
    if m_lz:
        text = m_lz.group(1)

    # Connector-circle artifact: "OA" → "A"
    if len(text) == 2 and text[0] in ("O", "0") and text[1].isalpha() and text[1].isupper():
        text = text[1]

    # Wire-endpoint circle + power rail: "O+UCC" → "+UCC"
    if re.match(r"^[Oo]\+[A-Za-z]", text):
        text = text[1:]

    # I↔1, O↔0 in value tokens
    io_fixed = text.replace("I", "1").replace("O", "0")
    if io_fixed != text and re.match(r"^\d+\.?\d*[PNFUKRMGpnfukrmgΩ]$", io_fixed):
        text = io_fixed.upper()

    # S↔5 in value tokens
    s_fixed = text.replace("S", "5").replace("s", "5")
    if s_fixed != text and re.match(r"^\d+\.?\d*[PNFUKRMGpnfukrmgΩ]$", s_fixed):
        text = s_fixed

    # "25C1740" → "2SC1740" (JIS semiconductor)
    if re.match(r"^25[A-Z]\d{3,4}$", text):
        text = "2S" + text[2:]

    # JIS model: I/O → 1/0 in model number
    m_jis = re.match(r"^(2S[A-Z])([\dIOlo]+)$", text)
    if m_jis:
        prefix, model = m_jis.group(1), m_jis.group(2)
        model_fixed = model.replace("I", "1").replace("O", "0").replace("l", "1").replace("o", "0")
        if model_fixed != model:
            text = prefix + model_fixed

    # "ISS133" → "1SS133", "IN4148" → "1N4148"
    if re.match(r"^I(SS|N)\d{3,5}$", text):
        text = "1" + text[1:]

    # "0413" → "D413" (diode misread)
    if re.match(r"^0[1-9]\d{2}$", text):
        text = "D" + text[1:]

    # "RB13" → "R813"
    if re.match(r"^RB\d{2,4}$", text):
        text = "R8" + text[2:]

    # "QBO6" → "Q806"
    if re.match(r"^Q[B8][O0]\d{1,3}$", text):
        text = "Q8" + text[2:].replace("O", "0")

    # "8" as "B" after decimal: "6.BC" → "6.8C"
    text = re.sub(r"(?<=\d\.)B", "8", text)

    # "LI02" → "L102"
    if re.match(r"^LI\d{2,3}$", text):
        text = "L1" + text[2:]

    # Ground-symbol prefix: "m5K" → "5K"
    if re.match(r"^m\d+\.?\d*[KkMRPNFUGpnfuΩ]$", text):
        text = text[1:]

    # Handwritten "7" as "/": standalone "/" → "7"
    if text == "/":
        text = "7"

    # Trailing comma/period from pin numbers: "19," → "19"
    if re.match(r"^\d{1,3}[,.]$", text):
        text = text[:-1]

    # "1C408" → "IC408"
    if re.match(r"^1C\d{2,4}", text):
        text = "IC" + text[2:]

    # Trailing "m" noise
    m = _TRAILING_M_NOISE.match(text)
    if m:
        return m.group(1)

    # Compound "=" split
    meq = _COMPOUND_EQ.match(text)
    if meq:
        return meq.group(1)

    # Compound no-eq split
    noeq_comp = _split_compound_noeq(text)
    if noeq_comp:
        return noeq_comp

    # Trailing ".00" → Ω
    m_dot00 = re.match(r"^(\d{2,})\.00$", text)
    if m_dot00:
        return m_dot00.group(1) + "Ω"

    # Trailing "g"/"o"/"Q" → Ω
    m_g_ohm = re.match(r"^(\d[\d.]*[kKM]?)[goQ]$", text)
    if m_g_ohm:
        return m_g_ohm.group(1) + "Ω"

    # Trailing "52" → Ω (handwritten)
    if re.match(r"^\d{1,3}52$", text) and len(text) >= 4:
        return text[:-2] + "Ω"

    # Trailing Ohm-as-"s"
    if text != "2S":
        mohm = _TRAILING_OHM_NOISE.match(text)
        if mohm:
            return mohm.group(1) + "Ω"

    # "..." → "~"
    if _THREE_DOTS.search(text):
        text = _THREE_DOTS.sub("~", text)

    return text


# ---------------------------------------------------------------------------
# Noise filtering
# ---------------------------------------------------------------------------

def _parse_sequential_pins(text: str) -> Optional[List[int]]:
    """Parse digit-only string as consecutive pin numbers (e.g. "12345678910")."""
    pos = 0
    expected = 1
    pins: List[int] = []
    while pos < len(text):
        s = str(expected)
        if text[pos:pos + len(s)] == s:
            pins.append(expected)
            pos += len(s)
            expected += 1
        else:
            return None
    return pins if len(pins) >= 3 else None


def should_drop_noise(
    text: str,
    bbox: Tuple[float, float, float, float],
    min_conf: float,
    conf: float,
) -> bool:
    """Determine if a token is noise that should be dropped."""
    # Low confidence with rescue for valid patterns
    if conf < min_conf:
        if conf >= 25 and re.match(r"^\d+\.?\d*[KkMRPNFUGpnfuΩ]{1,2}$", text):
            pass
        elif conf >= 15 and re.match(r"^\d+\.?\d*µF$", text):
            pass
        elif conf >= 40 and re.match(r"^\d{1,2}$", text):
            pass
        elif conf >= 40 and re.match(r"^\d{1,3}\s+\d{1,3}$", text):
            pass
        else:
            return True

    x, y, w, h = bbox
    area = w * h
    max_dim = max(w, h)

    if text in {"+", "-", "+/-"} and area < 0.02 * max_dim * max_dim:
        return True
    if text == "+":
        return True
    if text in {"-", "~"}:
        return True
    if text.upper() == "AND" and area < 0.05 * max_dim * max_dim:
        return True
    if area < 1.0:
        return True
    if len(text) <= 2 and not any(ch.isalnum() for ch in text) and area < 0.05 * max_dim * max_dim:
        return True
    if len(text) <= 3 and area < 0.002 * max(w, h) * max(w, h):
        if all(ch in {"7", "M", "W"} for ch in text.upper()):
            return True

    up = text.upper()
    if up in {"777", "77"} and len(text) <= 3:
        return True
    if re.match(r"^[IlT|]{2,4}$", text) and len(text) <= 4:
        return True
    if text == "m":
        return True
    if text == "M":
        return True
    if text == "1" and conf < 45:
        return True
    if text == "=":
        return True
    if text == ":":
        return True
    if text == "00":
        return True
    if text in {"O", "0", "o", "C", "c"} and conf < 55:
        return True
    if text == "#":
        return True
    if text in {"W", "Y"} and conf < 80:
        return True
    if text == "MA" and conf < 55:
        return True
    if text.strip("*") == "":
        return True
    if up in {"THE", "AND", "FOR", "NOT", "BUT", "ARE", "HAS", "HAD"}:
        return True
    if text.isdigit() and len(text) > 5:
        if _parse_sequential_pins(text) is None:
            return True
    return False


# ---------------------------------------------------------------------------
# Token-level transforms
# ---------------------------------------------------------------------------

def _split_merged_pins(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace merged pin-number tokens (e.g. "12345678910") with individual pins."""
    result: List[Dict[str, Any]] = []
    for tok in tokens:
        text = tok["text"]
        if not (text.isdigit() and len(text) > 5):
            result.append(tok)
            continue
        pins = _parse_sequential_pins(text)
        if pins is None:
            result.append(tok)
            continue
        x, y, w, h = tok["bbox"]
        conf = tok["confidence"]
        n = len(pins)
        landscape = w >= h
        for i, pin in enumerate(pins):
            if landscape:
                pw = w / n
                px = x + i * pw
                py, ph = y, h
            else:
                ph = h / n
                py = y + i * ph
                px, pw = x, w
            pin_text = str(pin)
            cx, cy = px + pw / 2, py + ph / 2
            result.append({
                "text": pin_text,
                "confidence": conf,
                "bbox": (px, py, pw, ph),
                "center": (cx, cy),
                "category": "net_label",
            })
    return result


def _split_space_separated_pins(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Split value tokens like '4 12' into separate net_label tokens."""
    result: List[Dict[str, Any]] = []
    for tok in tokens:
        if tok["category"] == "value":
            m = re.match(r"^(\d{1,3})\s+(\d{1,3})$", tok["text"])
            if m:
                pin1, pin2 = m.group(1), m.group(2)
                x, y, w, h = tok["bbox"]
                total_chars = len(pin1) + 1 + len(pin2)
                char_w = w / total_chars if total_chars > 0 else w
                w1 = char_w * len(pin1)
                gap = char_w
                w2 = char_w * len(pin2)
                bbox1 = (x, y, w1, h)
                bbox2 = (x + w1 + gap, y, w2, h)
                result.append({
                    "text": pin1, "confidence": tok["confidence"],
                    "bbox": bbox1, "center": bbox_center(bbox1),
                    "category": "net_label",
                })
                result.append({
                    "text": pin2, "confidence": tok["confidence"],
                    "bbox": bbox2, "center": bbox_center(bbox2),
                    "category": "net_label",
                })
                continue
        result.append(tok)
    return result


def _merge_value_unit_suffix(
    tokens: List[Dict[str, Any]],
    y_tol_ratio: float = 0.7,
    x_gap_max_px: float = 30.0,
) -> List[Dict[str, Any]]:
    """Merge standalone unit suffix (K, kΩ, µF, etc.) with adjacent numeric value."""
    consumed: set[int] = set()
    new_merged: List[Dict[str, Any]] = []

    for i, tok in enumerate(tokens):
        if i in consumed:
            continue
        tok_text = tok["text"]
        is_single = tok_text in _UNIT_SUFFIXES and len(tok_text) == 1
        is_multi = tok_text in _MULTI_UNIT_SUFFIXES
        if not (is_single or is_multi):
            continue

        # Strategy 1: horizontal (same Y band, unit to the right of number)
        best_j: int | None = None
        best_gap = float("inf")
        ux, uy, uw, uh = tok["bbox"]
        for j, val in enumerate(tokens):
            if j == i or j in consumed:
                continue
            vtext = val["text"]
            if not re.match(r"^\d+\.?\d*$", vtext):
                continue
            vx, vy, vw, vh = val["bbox"]
            max_h = max(uh, vh)
            if abs(tok["center"][1] - val["center"][1]) > y_tol_ratio * max_h:
                continue
            gap = ux - (vx + vw)
            if gap < 0 or gap > x_gap_max_px:
                continue
            if gap < best_gap:
                best_gap = gap
                best_j = j

        # Strategy 2: vertical (unit below number)
        if best_j is None:
            best_dy = float("inf")
            for j, val in enumerate(tokens):
                if j == i or j in consumed:
                    continue
                vtext = val["text"]
                if not re.match(r"^\d+[.,]?\d*$", vtext):
                    continue
                vx, vy, vw, vh = val["bbox"]
                dx = abs(tok["center"][0] - val["center"][0])
                max_w = max(uw, vw)
                if dx > max_w * 1.5:
                    continue
                dy = tok["center"][1] - val["center"][1]
                if dy <= 0:
                    continue
                if dy > max(uh, vh) * 3:
                    continue
                if dy < best_dy:
                    best_dy = dy
                    best_j = j

        if best_j is not None:
            val_tok = tokens[best_j]
            merged_text = clean_token_text(val_tok["text"] + tok["text"])
            vx, vy, vw, vh = val_tok["bbox"]
            min_x = min(vx, ux)
            min_y = min(vy, uy)
            max_x = max(vx + vw, ux + uw)
            max_y = max(vy + vh, uy + uh)
            merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
            avg_conf = (val_tok["confidence"] + tok["confidence"]) / 2
            consumed.add(i)
            consumed.add(best_j)
            new_merged.append({
                "text": merged_text,
                "confidence": avg_conf,
                "bbox": merged_bbox,
                "center": bbox_center(merged_bbox),
                "category": "value",
            })

    result = [tok for idx, tok in enumerate(tokens) if idx not in consumed]
    result.extend(new_merged)

    # Handle truncated leading digit: '1' + '.2K' → '1.2K'
    merged_indices: set[int] = set()
    adjusted: List[Dict[str, Any]] = []
    i = 0
    while i < len(result):
        if i in merged_indices:
            i += 1
            continue
        tok = result[i]
        if re.match(r"^\d$", tok["text"]) and i + 1 < len(result):
            right = result[i + 1]
            if re.match(r"^\.\d+", right["text"]):
                dx = right["center"][0] - tok["center"][0]
                dy = abs(right["center"][1] - tok["center"][1])
                if 0 < dx < 80 and dy < max(tok["bbox"][3], right["bbox"][3]) * 0.6:
                    merged_text = clean_token_text(tok["text"] + right["text"])
                    min_x = min(tok["bbox"][0], right["bbox"][0])
                    min_y = min(tok["bbox"][1], right["bbox"][1])
                    max_x = max(tok["bbox"][0] + tok["bbox"][2], right["bbox"][0] + right["bbox"][2])
                    max_y = max(tok["bbox"][1] + tok["bbox"][3], right["bbox"][1] + right["bbox"][3])
                    merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
                    avg_conf = (tok.get("confidence", 0) + right.get("confidence", 0)) / 2
                    adjusted.append({
                        "text": merged_text,
                        "confidence": avg_conf,
                        "bbox": merged_bbox,
                        "center": bbox_center(merged_bbox),
                        "category": "value",
                    })
                    merged_indices.add(i)
                    merged_indices.add(i + 1)
                    i += 2
                    continue
        adjusted.append(tok)
        i += 1
    return adjusted


def _dedup_substring_tokens(
    tokens: List[Dict[str, Any]],
    proximity: float = 80.0,
) -> List[Dict[str, Any]]:
    """Remove tokens whose text is a substring of a longer, nearby token."""
    drop: set[int] = set()
    for i, short in enumerate(tokens):
        if i in drop:
            continue
        st = short["text"]
        if len(st) < 2:
            continue
        if st.startswith("."):
            continue
        for j, long_ in enumerate(tokens):
            if j == i or j in drop:
                continue
            lt = long_["text"]
            if len(lt) <= len(st):
                continue
            if st not in lt:
                continue
            # Don't dedup digit-only pins against values (unless bbox overlap)
            if re.match(r"^\d{1,3}$", st) and long_.get("category") == "value":
                _lx, _ly, _lw, _lh = long_["bbox"]
                _sx, _sy = short["center"]
                if not (_lx <= _sx <= _lx + _lw and _ly <= _sy <= _ly + _lh):
                    continue
            sx, sy = short["center"]
            lx, ly = long_["center"]
            if abs(sx - lx) < proximity and abs(sy - ly) < proximity:
                drop.add(i)
                break

    # Drop single non-digit chars inside component bbox
    for i, single in enumerate(tokens):
        if i in drop:
            continue
        if len(single["text"]) != 1 or single["text"].isdigit():
            continue
        sx, sy = single["center"]
        for j, comp in enumerate(tokens):
            if j == i or j in drop:
                continue
            if len(comp["text"]) <= 1 or comp.get("category") != "component":
                continue
            lx, ly, lw, lh = comp["bbox"]
            if lx <= sx <= lx + lw and ly <= sy <= ly + lh:
                drop.add(i)
                break

    # Drop single-digit tokens inside longer value bbox
    for i, single in enumerate(tokens):
        if i in drop:
            continue
        st = single["text"]
        if len(st) != 1 or not st.isdigit():
            continue
        sx, sy = single["center"]
        for j, val in enumerate(tokens):
            if j == i or j in drop:
                continue
            if len(val["text"]) <= 1 or st not in val["text"]:
                continue
            vx, vy, vw, vh = val["bbox"]
            if vx <= sx <= vx + vw and vy <= sy <= vy + vh:
                drop.add(i)
                break

    # Drop "0" near inductor components (coil symbol misread)
    for i, single in enumerate(tokens):
        if i in drop:
            continue
        if single["text"] != "0":
            continue
        sx, sy = single["center"]
        for j, comp in enumerate(tokens):
            if j == i or j in drop or comp.get("category") != "component":
                continue
            if not re.match(r"^L\d", comp["text"]):
                continue
            cx, cy = comp["center"]
            if abs(sx - cx) < proximity and abs(sy - cy) < proximity:
                drop.add(i)
                break

    return [t for i, t in enumerate(tokens) if i not in drop]


def _merge_horizontal_others(
    tokens: List[Dict[str, Any]],
    y_tol_ratio: float = 0.5,
    x_gap_ratio: float = 3.0,
) -> List[Dict[str, Any]]:
    """Merge 'other' tokens on the same horizontal line."""
    others = [(i, t) for i, t in enumerate(tokens) if t["category"] == "other"]
    if len(others) < 2:
        return tokens
    others.sort(key=lambda pair: pair[1]["center"][0])
    merged_indices: set[int] = set()
    new_tokens: List[Dict[str, Any]] = []

    i = 0
    while i < len(others):
        idx_a, tok_a = others[i]
        if idx_a in merged_indices:
            i += 1
            continue
        group = [tok_a]
        group_indices = [idx_a]
        j = i + 1
        while j < len(others):
            idx_b, tok_b = others[j]
            if idx_b in merged_indices:
                j += 1
                continue
            last = group[-1]
            lx, ly, lw, lh = last["bbox"]
            rx, ry, rw, rh = tok_b["bbox"]
            ref_h = min(lh, rh)
            if abs(last["center"][1] - tok_b["center"][1]) > y_tol_ratio * ref_h:
                j += 1
                continue
            gap = rx - (lx + lw)
            if gap > x_gap_ratio * ref_h:
                j += 1
                continue
            group.append(tok_b)
            group_indices.append(idx_b)
            j += 1
        if len(group) > 1:
            merged_indices.update(group_indices)
            texts = [g["text"] for g in group]
            bboxes = [g["bbox"] for g in group]
            min_x = min(b[0] for b in bboxes)
            min_y = min(b[1] for b in bboxes)
            max_x = max(b[0] + b[2] for b in bboxes)
            max_y = max(b[1] + b[3] for b in bboxes)
            merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
            avg_conf = sum(g["confidence"] for g in group) / len(group)
            new_tokens.append({
                "text": " ".join(texts),
                "confidence": avg_conf,
                "bbox": merged_bbox,
                "center": bbox_center(merged_bbox),
                "category": "other",
            })
        i += 1

    result = [t for i, t in enumerate(tokens) if i not in merged_indices]
    result.extend(new_tokens)
    return result


def _merge_horizontal_net_labels(
    tokens: List[Dict[str, Any]],
    y_tol_ratio: float = 0.5,
    x_gap_ratio: float = 3.0,
) -> List[Dict[str, Any]]:
    """Merge 'net_label' word tokens on the same horizontal line."""
    labels = [(i, t) for i, t in enumerate(tokens) if t["category"] == "net_label"]
    if len(labels) < 2:
        return tokens

    def _is_mergeable_word(t: Dict[str, Any]) -> bool:
        txt = t["text"]
        if not re.match(r"^[A-Za-zÀ-ž]+$", txt):
            return False
        if len(txt) <= 6 and txt == txt.upper():
            return False
        return True

    word_labels = [(i, t) for i, t in labels if _is_mergeable_word(t)]
    if len(word_labels) < 2:
        return tokens

    word_labels.sort(key=lambda pair: pair[1]["center"][0])
    merged_indices: set[int] = set()
    new_tokens: List[Dict[str, Any]] = []

    idx = 0
    while idx < len(word_labels):
        idx_a, tok_a = word_labels[idx]
        if idx_a in merged_indices:
            idx += 1
            continue
        group = [tok_a]
        group_indices = [idx_a]
        jj = idx + 1
        while jj < len(word_labels):
            idx_b, tok_b = word_labels[jj]
            if idx_b in merged_indices:
                jj += 1
                continue
            last = group[-1]
            lx, ly, lw, lh = last["bbox"]
            rx, ry, rw, rh = tok_b["bbox"]
            max_h = max(lh, rh)
            if abs(last["center"][1] - tok_b["center"][1]) > y_tol_ratio * max_h:
                jj += 1
                continue
            gap = rx - (lx + lw)
            if gap > x_gap_ratio * max_h:
                jj += 1
                continue
            group.append(tok_b)
            group_indices.append(idx_b)
            jj += 1
        if len(group) > 1:
            merged_indices.update(group_indices)
            texts = [g["text"] for g in group]
            bboxes = [g["bbox"] for g in group]
            min_x = min(b[0] for b in bboxes)
            min_y = min(b[1] for b in bboxes)
            max_x = max(b[0] + b[2] for b in bboxes)
            max_y = max(b[1] + b[3] for b in bboxes)
            merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
            avg_conf = sum(g["confidence"] for g in group) / len(group)
            new_tokens.append({
                "text": " ".join(texts),
                "confidence": avg_conf,
                "bbox": merged_bbox,
                "center": bbox_center(merged_bbox),
                "category": "net_label",
            })
        idx += 1

    result = [t for i, t in enumerate(tokens) if i not in merged_indices]
    result.extend(new_tokens)
    return result


def _merge_slash_value_fragments(
    tokens: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge value tokens split by '/' across lines (e.g. '10µF/' + '25V')."""
    merge_map: Dict[int, int] = {}
    claimed: set[int] = set()

    for i, tok in enumerate(tokens):
        if i in claimed:
            continue
        text = tok["text"]

        # Case 1: value ending with "/"
        if text.endswith("/") and tok["category"] == "value":
            tx, ty = tok["center"]
            t_bbox = tok["bbox"]
            t_h = t_bbox[3]
            best_j: int | None = None
            best_dy = float("inf")
            for j, other in enumerate(tokens):
                if j == i or j in claimed:
                    continue
                ox, oy = other["center"]
                dx = abs(ox - tx)
                dy = oy - ty
                if dy <= 0 or dx > max(t_bbox[2], 40) or dy > t_h * 4:
                    continue
                if dy < best_dy:
                    best_dy = dy
                    best_j = j
            if best_j is not None:
                merge_map[i] = best_j
                claimed.update({i, best_j})
                continue

        # Case 2: token starting with "/"
        if text.startswith("/") and len(text) > 1 and i not in claimed:
            tx, ty = tok["center"]
            t_bbox = tok["bbox"]
            t_h = t_bbox[3]
            best_j = None
            best_dy = float("inf")
            for j, other in enumerate(tokens):
                if j == i or j in claimed:
                    continue
                if other["category"] not in {"value", "net_label"}:
                    continue
                ox, oy = other["center"]
                dx = abs(ox - tx)
                dy = ty - oy
                if dy <= 0 or dx > max(t_bbox[2], 40) or dy > t_h * 4:
                    continue
                if dy < best_dy:
                    best_dy = dy
                    best_j = j
            if best_j is not None:
                merge_map[best_j] = i
                claimed.update({i, best_j})

    # Build result
    result: List[Dict[str, Any]] = []
    for upper_idx, lower_idx in merge_map.items():
        upper = tokens[upper_idx]
        lower = tokens[lower_idx]
        upper_text = upper["text"]
        lower_text = lower["text"]
        if upper_text.endswith("/") and lower_text.startswith("/"):
            merged_text = upper_text + lower_text[1:]
        else:
            merged_text = upper_text + lower_text
        bboxes = [upper["bbox"], lower["bbox"]]
        min_x = min(b[0] for b in bboxes)
        min_y = min(b[1] for b in bboxes)
        max_x = max(b[0] + b[2] for b in bboxes)
        max_y = max(b[1] + b[3] for b in bboxes)
        merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
        result.append({
            "text": merged_text,
            "confidence": min(upper["confidence"], lower["confidence"]),
            "bbox": merged_bbox,
            "center": upper["center"],
            "category": "value",
        })
    for i, tok in enumerate(tokens):
        if i not in claimed:
            result.append(tok)
    return result


def _fix_overline_q(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rename misread overline Q̄ tokens from 'I' to '-Q'."""
    q_indices = [i for i, t in enumerate(tokens) if t.get("category") == "net_label" and t.get("text") == "Q"]
    i_indices = [i for i, t in enumerate(tokens)
                 if t.get("category") == "net_label" and t.get("text") in ("I", "-", "|", "—")]

    for i_idx in i_indices:
        i_tok = tokens[i_idx]
        i_cx, i_cy = i_tok["center"]
        i_h = i_tok["bbox"][3]
        for q_idx in q_indices:
            q_tok = tokens[q_idx]
            q_cx, q_cy = q_tok["center"]
            dx = abs(i_cx - q_cx)
            dy = i_cy - q_cy
            max_dx = max(20, i_h * 1.5)
            if dx < max_dx and 0 < dy < i_h * 10:
                tokens[i_idx] = {**i_tok, "text": "-Q"}
                break
    return tokens


def _merge_hyphenated_words(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge words broken across lines with trailing hyphen."""
    consumed: set[int] = set()
    result: List[Dict[str, Any]] = []

    for i, tok in enumerate(tokens):
        if i in consumed:
            continue
        text = tok["text"]
        if not (text.endswith("-") and len(text) >= 3):
            result.append(tok)
            continue
        # Skip net_labels (IN-, CS- are active-low indicators)
        if tok.get("category") == "net_label":
            result.append(tok)
            continue

        tx, ty = tok["center"]
        t_bbox = tok["bbox"]
        t_h = t_bbox[3]
        best_j: int | None = None
        best_dy = float("inf")
        for j, other in enumerate(tokens):
            if j == i or j in consumed:
                continue
            ox, oy = other["center"]
            dy = oy - ty
            if dy <= 0 or dy > t_h * 4:
                continue
            dx = abs(ox - tx)
            if dx > max(t_bbox[2], 80):
                continue
            if other.get("category") == "component":
                continue
            if dy < best_dy:
                best_dy = dy
                best_j = j

        if best_j is not None:
            lower = tokens[best_j]
            merged_text = text[:-1] + lower["text"]
            bboxes = [tok["bbox"], lower["bbox"]]
            min_x = min(b[0] for b in bboxes)
            min_y = min(b[1] for b in bboxes)
            max_x = max(b[0] + b[2] for b in bboxes)
            max_y = max(b[1] + b[3] for b in bboxes)
            merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
            avg_conf = (tok["confidence"] + lower["confidence"]) / 2
            consumed.update({i, best_j})
            result.append({
                "text": merged_text,
                "confidence": avg_conf,
                "bbox": merged_bbox,
                "center": tok["center"],
                "category": "other",
            })
        else:
            result.append(tok)
    return result


def _fix_wire_endpoint_digit_merge(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Split 2-digit 'X0' value tokens created by merging digit + wire-endpoint circle."""
    single_digit_labels = [
        t for t in tokens
        if t.get("category") == "net_label" and len(t["text"]) == 1 and t["text"].isdigit()
    ]
    result: List[Dict[str, Any]] = []
    for tok in tokens:
        text = tok["text"]
        conf = tok.get("confidence", 100.0)
        if (
            len(text) == 2 and text.isdigit() and text[1] == "0" and text[0] != "0"
            and tok.get("category") == "value" and conf < 85
        ):
            cx, cy = tok["center"]
            has_nearby = any(
                ((cx - l["center"][0]) ** 2 + (cy - l["center"][1]) ** 2) ** 0.5 <= 50
                for l in single_digit_labels
            )
            if has_nearby:
                new_text = text[0]
                x, y, w, h = tok["bbox"]
                new_w = w * 0.5
                new_bbox = (x, y, new_w, h)
                result.append({
                    "text": new_text,
                    "confidence": conf,
                    "bbox": new_bbox,
                    "center": (x + new_w / 2.0, y + h / 2.0),
                    "category": "net_label",
                })
                continue
        result.append(tok)
    return result


def _merge_vertical_fragments(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge single-char tokens arranged vertically into component designators."""
    if not tokens:
        return tokens
    short_indices = [i for i, t in enumerate(tokens) if len(t["text"]) == 1 and t["text"].strip()]
    if len(short_indices) < 2:
        return tokens

    used: set[int] = set()
    merged_tokens: List[Dict[str, Any]] = []
    short_sorted = sorted(short_indices, key=lambda i: (tokens[i]["center"][0], tokens[i]["center"][1]))

    for start_pos, si in enumerate(short_sorted):
        if si in used:
            continue
        t0 = tokens[si]
        char_w = t0["bbox"][2]
        char_h = t0["bbox"][3]
        x_tol = max(char_w * 1.2, 15)
        y_max_gap = max(char_h * 2.0, 25)

        column = [si]
        last_bottom = t0["bbox"][1] + t0["bbox"][3]
        for next_pos in range(start_pos + 1, len(short_sorted)):
            nj = short_sorted[next_pos]
            if nj in used:
                continue
            tn = tokens[nj]
            dx = abs(tn["center"][0] - t0["center"][0])
            if dx > x_tol:
                break
            gap = tn["bbox"][1] - last_bottom
            if gap < -char_h * 0.5:
                continue
            if gap > y_max_gap:
                continue
            column.append(nj)
            last_bottom = tn["bbox"][1] + tn["bbox"][3]

        if len(column) < 2:
            continue
        column.sort(key=lambda i: tokens[i]["center"][1])

        parts = [tokens[i] for i in column]
        merged_text = "".join(p["text"] for p in parts)
        merged_cat = categorize(merged_text)
        if merged_cat != "component" or len(merged_text) < 3:
            continue

        min_x = min(p["bbox"][0] for p in parts)
        min_y = min(p["bbox"][1] for p in parts)
        max_x = max(p["bbox"][0] + p["bbox"][2] for p in parts)
        max_y = max(p["bbox"][1] + p["bbox"][3] for p in parts)
        merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
        avg_conf = sum(p["confidence"] for p in parts) / len(parts)
        merged_tokens.append({
            "text": merged_text,
            "confidence": avg_conf,
            "bbox": merged_bbox,
            "center": bbox_center(merged_bbox),
            "category": merged_cat,
        })
        used.update(column)

    result = [t for i, t in enumerate(tokens) if i not in used]
    result.extend(merged_tokens)
    return result


def _fix_semicon_fragments(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fix semiconductor model mis-classification: merge split prefixes, restore lost prefixes."""
    consumed: set[int] = set()
    new_merged: List[Dict[str, Any]] = []

    # Case 1: merge existing prefix + body tokens (e.g. '2S' + 'C1740')
    for i, tok in enumerate(tokens):
        if i in consumed:
            continue
        tok_text_up = tok.get("text", "").upper()
        if tok_text_up not in _SEMI_PREFIX_FRAGMENTS:
            continue
        tx, ty = tok["center"]
        tw, th = tok["bbox"][2], tok["bbox"][3]
        best_j: int | None = None
        best_dist = float("inf")
        for j, body in enumerate(tokens):
            if j == i or j in consumed:
                continue
            body_text = body.get("text", "")
            if not _SEMI_BODY_RE.match(body_text):
                continue
            merged_cand = tok["text"] + body_text
            if not SEMI_MODEL_RE.match(merged_cand):
                continue
            bx, by = body["center"]
            dist = ((bx - tx) ** 2 + (by - ty) ** 2) ** 0.5
            if dist > max(tw, th) * 6:
                continue
            if dist < best_dist:
                best_dist = dist
                best_j = j

        if best_j is not None:
            body_tok = tokens[best_j]
            merged_text = tok["text"] + body_tok["text"]
            bboxes = [tok["bbox"], body_tok["bbox"]]
            min_x = min(b[0] for b in bboxes)
            min_y = min(b[1] for b in bboxes)
            max_x = max(b[0] + b[2] for b in bboxes)
            max_y = max(b[1] + b[3] for b in bboxes)
            merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
            avg_conf = (tok["confidence"] + body_tok["confidence"]) / 2
            consumed.update({i, best_j})
            new_merged.append({
                "text": merged_text,
                "confidence": avg_conf,
                "bbox": merged_bbox,
                "center": bbox_center(merged_bbox),
                "category": "value",
            })

    result = [tok for idx, tok in enumerate(tokens) if idx not in consumed]
    result.extend(new_merged)

    # Case 2: prefix lost — C+4digits near Q/D → restore '2S' prefix
    q_comps = [t for t in result if t.get("category") == "component" and t.get("text", "").upper()[:1] in {"Q", "D"}]
    if q_comps:
        for tok in result:
            if tok.get("category") != "component":
                continue
            txt = tok.get("text", "")
            if not re.match(r"^[ABCDJK]\d{4,}$", txt, re.IGNORECASE):
                continue
            candidate = "2S" + txt
            if not SEMI_MODEL_RE.match(candidate):
                continue
            tx, ty = tok["center"]
            tw, th = tok["bbox"][2], tok["bbox"][3]
            for qc in q_comps:
                qx, qy = qc["center"]
                dist = ((qx - tx) ** 2 + (qy - ty) ** 2) ** 0.5
                if dist <= max(tw, th) * 5:
                    tok["text"] = candidate
                    tok["category"] = "value"
                    break
    return result


def _fix_ic_ocr_confusion(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fix OCR confusion in IC designators (e.g. IC40B → IC408)."""
    for t in tokens:
        text = t["text"].strip()
        up = text.upper()
        if not up.startswith("IC") or len(up) < 4:
            continue
        suffix = up[2:]
        if suffix.isdigit():
            continue
        m = re.match(r"^(\d+)([A-Z])$", suffix)
        if not m:
            continue
        trailing = m.group(2)
        replacement = _IC_OCR_LETTER_TO_DIGIT.get(trailing)
        if replacement is None:
            continue
        t["text"] = f"IC{m.group(1)}{replacement}"
        t["category"] = "component"
    return tokens


def _extend_truncated_designators(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extend component designators that lost their last digit (e.g. C41 + 1 → C411)."""
    comp_indices = [i for i, t in enumerate(tokens) if t.get("category") == "component"]
    single_digit_indices = [i for i, t in enumerate(tokens) if len(t.get("text", "")) == 1 and t["text"].isdigit()]
    if not comp_indices or not single_digit_indices:
        return tokens

    absorbed: set[int] = set()
    for ci in comp_indices:
        comp = tokens[ci]
        comp_text = comp["text"]
        if not re.match(r"^[A-Z]{1,2}\d+$", comp_text, re.IGNORECASE):
            continue
        if comp_text.upper().startswith("IC"):
            continue
        cx, cy = comp["center"]
        cb = comp["bbox"]
        comp_bottom = cb[1] + cb[3]
        char_h = cb[3] / max(len(comp_text), 1)

        for di in single_digit_indices:
            if di in absorbed:
                continue
            digit = tokens[di]
            dx_val = abs(digit["center"][0] - cx)
            if dx_val > max(cb[2] * 1.5, 20):
                continue
            gap = digit["bbox"][1] - comp_bottom
            if gap < -char_h * 0.5 or gap > char_h * 2.5:
                continue
            ext_text = comp_text + digit["text"]
            if categorize(ext_text) != "component":
                continue
            comp["text"] = ext_text
            min_x = min(cb[0], digit["bbox"][0])
            min_y = min(cb[1], digit["bbox"][1])
            max_x = max(cb[0] + cb[2], digit["bbox"][0] + digit["bbox"][2])
            max_y = max(cb[1] + cb[3], digit["bbox"][1] + digit["bbox"][3])
            comp["bbox"] = (min_x, min_y, max_x - min_x, max_y - min_y)
            comp["center"] = bbox_center(comp["bbox"])
            cb = comp["bbox"]
            comp_bottom = cb[1] + cb[3]
            absorbed.add(di)
            break

    if absorbed:
        tokens = [t for i, t in enumerate(tokens) if i not in absorbed]
    return tokens


_IC_RE = re.compile(r"IC(\d{2,4})", re.IGNORECASE)
_LONE_C_RE = re.compile(r"^C(\d{3,4})$")


def fix_truncated_ic(
    tokens: List[Dict[str, Any]],
    pairs: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Detect C-designators that are really ICs with a truncated 'I'.

    Must be called AFTER pairing. If a C-designator shares the hundred-series
    of a known IC AND was NOT paired with any value, rename it to IC.
    """
    ic_hundreds: set[int] = set()
    for t in tokens:
        m = _IC_RE.search(t["text"])
        if m:
            ic_hundreds.add(int(m.group(1)) // 100)
    if not ic_hundreds:
        return tokens, pairs

    paired_comps = {p["component"] for p in pairs}
    for t in tokens:
        m2 = _LONE_C_RE.match(t["text"])
        if not m2:
            continue
        if t["text"] in paired_comps:
            continue
        num = int(m2.group(1))
        if num // 100 in ic_hundreds:
            t["text"] = f"IC{num}"
            t["category"] = "component"
    return tokens, pairs


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def postprocess_tokens(
    tokens: List[Dict[str, Any]],
    min_confidence: float = 30.0,
) -> List[Dict[str, Any]]:
    """Apply full postprocessing pipeline to raw OCR tokens.

    Steps:
    1. Clean token text (fix OCR artifacts, transliterate, normalise)
    2. Handle compound tokens (R1=22K → two separate tokens)
    3. Filter noise
    4. Re-categorize after cleaning
    5. Merge fragments (vertical, horizontal, slash, hyphen, unit suffix)
    6. Fix OCR confusions (semiconductors, ICs, wire endpoints)
    7. Deduplicate

    Args:
        tokens: Raw OCR tokens with text, confidence, bbox, center, category
        min_confidence: Minimum confidence threshold for noise filtering

    Returns:
        Cleaned, merged, deduplicated tokens
    """
    # --- Phase 1: clean text, handle compounds, filter noise, re-categorize ---
    processed: List[Dict[str, Any]] = []
    for tok in tokens:
        raw_text = tok["text"]
        text = clean_token_text(raw_text)
        conf = tok["confidence"]
        bbox = tok["bbox"]
        original_bbox = bbox

        # Handle compound-eq split (R1=22K → R1 + emit 22K)
        is_compound_eq = _COMPOUND_EQ.match(raw_text)
        noeq_comp = _split_compound_noeq(raw_text) if not is_compound_eq else None

        # Shrink bbox for compound splits
        if len(text) < len(raw_text) and len(raw_text) > 0:
            if is_compound_eq or noeq_comp:
                ratio = len(text) / len(raw_text)
                x, y, bw, bh = bbox
                bbox = (x, y, bw * ratio, bh)

        effective_min_conf = 25.0 if is_compound_eq else min_confidence

        if should_drop_noise(text, bbox, effective_min_conf, conf):
            continue

        cat = categorize(text)
        center = bbox_center(bbox)
        processed.append({
            "text": text,
            "confidence": conf,
            "bbox": bbox,
            "center": center,
            "category": cat,
        })

        # Emit value token from compound-eq split
        if is_compound_eq:
            val_raw = raw_text[is_compound_eq.end():]
            val_text = clean_token_text(val_raw)
            if val_text and not should_drop_noise(val_text, original_bbox, 25.0, conf):
                ox, oy, obw, obh = original_bbox
                comp_ratio = is_compound_eq.end() / len(raw_text) if raw_text else 0.5
                val_bbox = (ox + obw * comp_ratio, oy, obw * (1 - comp_ratio), obh)
                processed.append({
                    "text": val_text,
                    "confidence": conf,
                    "bbox": val_bbox,
                    "center": bbox_center(val_bbox),
                    "category": categorize(val_text),
                })

        # Emit value token from compound no-eq split
        if noeq_comp:
            val_raw = raw_text[len(noeq_comp):]
            val_text = clean_token_text(val_raw)
            if val_text and not should_drop_noise(val_text, original_bbox, min_confidence, conf):
                ox, oy, obw, obh = original_bbox
                comp_ratio = len(noeq_comp) / len(raw_text)
                val_bbox = (ox + obw * comp_ratio, oy, obw * (1 - comp_ratio), obh)
                processed.append({
                    "text": val_text,
                    "confidence": conf,
                    "bbox": val_bbox,
                    "center": bbox_center(val_bbox),
                    "category": categorize(val_text),
                })

    # --- Phase 2: merge/fix pipeline ---
    tokens = _split_merged_pins(processed)
    tokens = _merge_value_unit_suffix(tokens)
    tokens = _dedup_substring_tokens(tokens)
    tokens = _merge_horizontal_others(tokens)
    tokens = _merge_horizontal_net_labels(tokens)
    tokens = _split_space_separated_pins(tokens)
    tokens = _merge_slash_value_fragments(tokens)
    tokens = _fix_overline_q(tokens)
    tokens = _merge_hyphenated_words(tokens)
    tokens = _fix_wire_endpoint_digit_merge(tokens)
    tokens = _merge_vertical_fragments(tokens)
    tokens = _fix_semicon_fragments(tokens)
    tokens = _fix_ic_ocr_confusion(tokens)
    tokens = _extend_truncated_designators(tokens)

    return tokens
