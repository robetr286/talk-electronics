from __future__ import annotations

import datetime
import io
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import boto3
import botocore
import numpy as np
from botocore.config import Config
from flask import Blueprint, current_app, jsonify, request
from PIL import Image, ImageDraw, ImageFont, ImageOps

try:  # opcjonalna rasteryzacja PDF
    import fitz  # type: ignore
except Exception:  # pragma: no cover - brak zależności
    fitz = None

textract_bp = Blueprint("textract", __name__, url_prefix="/ocr")


def _norm_bbox_to_px(bbox: Dict[str, float], w: int, h: int) -> Tuple[float, float, float, float]:
    return bbox.get("Left", 0.0) * w, bbox.get("Top", 0.0) * h, bbox.get("Width", 0.0) * w, bbox.get("Height", 0.0) * h


def _bbox_center(bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    x, y, bw, bh = bbox
    return x + bw / 2.0, y + bh / 2.0


def _looks_like_value(t: str) -> bool:
    # P20f: Semiconductor part numbers are values (model/type numbers).
    # JIS: 2SA/2SB/2SC/2SD + 3-4 digits (+optional suffix), e.g. 2SC1740
    # European BJT: BC/BD/BF/BU + digits + optional suffix, e.g. BC109B
    # Diodes: 1N/1SS + digits, e.g. 1N4148, 1SS133
    # B8: MA-prefix diodes (e.g. MA29WA, MA150, MA167A).
    if re.match(r"^(2S[ABCD]|1S[SN]|B[CDFRU]|MA)\d{2,5}[A-Z]{0,2}$", t, re.IGNORECASE):
        return True
    # P20g: IC/op-amp model numbers are values (part type numbers).
    # Common prefixes: UL, TDA, TL, LM, NE, UA, MC, TA, AN, AD, etc.
    # e.g. UL1440T, TDA2030, LM741, NE555, TA7137
    if re.match(r"^(UL|TDA|TL|LM|NE|UA|UPC|MC|TA|AN|AD|OP|MAX|LF|CA)\d{2,5}[A-Z]{0,2}$", t, re.IGNORECASE):
        return True
    # P18e: Guard — pure-alphanumeric tokens starting with ≥2 letters
    # where letters and digits are INTERLEAVED (e.g. "FE0F") are IC pin
    # labels, not electronic values.
    # Part-number tokens (all letters first, then all digits — e.g.
    # "SVC211", "BA6208") ARE legitimate values and must pass through.
    # Tokens with separators like "-", "." (e.g. "TZ-6.8C") are also
    # legitimate values — the isalnum() check lets them through.
    if re.match(r"^[A-Za-z]{2}", t) and t.isalnum():
        if not re.match(r"^[A-Za-z]+\d+$", t):
            return False
    if any(unit in t for unit in ["K", "M", "R", "Ω", "OHM", "U", "N", "P", "F", "V"]):
        return True
    if any(sep in t for sep in [".", ",", "/"]):
        return True
    digits = [ch for ch in t if ch.isdigit()]
    return len(digits) >= 2


# B4: Compiled regex for semiconductor part numbers (transistors, diodes).
# Used by semantic-affinity logic in _pair_components_to_values to prevent
# transistor components (Q-prefix) from stealing passive values (1m0, 47u)
# and instead prefer their proper model numbers (2SC2631, BC547).
_SEMI_MODEL_RE = re.compile(
    r"^(?:2S[ABCDKJ]|2N|1S[SN]?|1N|B[CDFRUY]|TIP|IRF|MPS[AU]?|MJE?|MA)\d{2,5}[A-Z]{0,2}$",
    re.IGNORECASE,
)


def _categorize(text: str) -> str:
    t = text.strip()
    up = t.upper()
    if not t:
        return "other"
    if up.startswith("IC") and up[2:].isdigit():
        return "component"
    # B10: Potentiometer designators — e.g. RpL, QpL, RpP, QpP.
    # Pattern: component prefix letter + lowercase "p" (potentiometer)
    # + L/P (side indicator).  These are never net labels on schematics.
    if len(t) == 3 and t[0] in {"R", "C", "L", "Q", "D", "M", "T"} and t[1] == "p" and t[2] in {"L", "P"}:
        return "component"
    # P13a: Added "D" (diode) and "M" (module) — common designators
    # on Japanese/international schematics.
    # B12: Added "S" (switch) — e.g. S1, S2.
    # P24a: Allow optional single trailing letter after digits.
    # Many schematics use suffixes like L (layout), P (PCB/parts),
    # A/B (sub-circuit) in designators: R8L, C23P, Q1P, etc.
    if up[0] in {"R", "C", "L", "Q", "D", "M", "T", "S"} and re.match(r"^\d+[A-Z]?$", up[1:]):
        return "component"
    # P18d: "SF" prefix — safety fuse / switching fuse designator.
    # e.g. SF402, SF403.  Common on Japanese audio schematics.
    if re.match(r"^SF\d{2,4}$", up):
        return "component"
    # P16d: Power rail labels like "+5V", "+12V", "-12V", "+48V" are
    # net labels (power supply rails), not electronic values.
    # Pattern: optional sign (+/-) + digits + "V" at end.
    if re.match(r"^[+\-]?\d+V$", up):
        return "net_label"
    if any(ch.isdigit() for ch in t):
        if _looks_like_value(t):
            return "value"
    if up.replace("_", "").replace("-", "").isalnum() and len(up) <= 6:
        return "net_label"
    # P17f: Audio channel connectors — "L ch" / "R ch" (left/right channel)
    # are connector net labels on audio schematics.  Textract may return
    # them as a single token with a space.  Categorise as net_label.
    if re.match(r"^[LR]\s+ch$", t, re.IGNORECASE):
        return "net_label"
    # P15c: Net labels with "+" or "/" — e.g. KP+, FEM+, DM+, R/W.
    # These are valid signal names on schematics.  The "+" / "/" chars
    # cause isalnum() to fail above, so we check explicitly.
    stripped = up.replace("+", "").replace("/", "").replace("-", "").replace("_", "")
    if stripped.isalnum() and 2 <= len(up) <= 6:
        return "net_label"
    return "other"


def _should_drop_noise(text: str, bbox: Tuple[float, float, float, float], min_conf: float, conf: float) -> bool:
    # P19a: Rescue short value+unit tokens (e.g. "5K", "100K") that
    # have low confidence because Textract merged them with a ground-
    # symbol artefact.  After _clean_token_text strips the "m" prefix,
    # the cleaned text is a valid value but confidence stays low (~30).
    # Use a relaxed threshold (25) for these high-signal tokens.
    if conf < min_conf:
        if conf >= 25 and re.match(r"^\d+\.?\d*[KkMRPNFUGpnfuΩ]{1,2}$", text):
            pass  # rescue — allow through
        # P20l: Rescue value tokens with µF/nF/pF unit (after P20d cleanup).
        # e.g. "100µF" conf=21 — Textract assigns low confidence to µ tokens
        # but the value+unit pattern is high-signal.
        elif conf >= 15 and re.match(r"^\d+\.?\d*µF$", text):
            pass  # rescue µF values
        # P20m: Rescue IC pin numbers — short digit tokens (1-2 digits) near
        # IC bounding boxes.  conf≥40 is safe for pin numbers.
        elif conf >= 40 and re.match(r"^\d{1,2}$", text):
            pass  # rescue pin numbers
        # P20n: Rescue "<digit> <digit>" space-separated pin pairs.
        elif conf >= 40 and re.match(r"^\d{1,3}\s+\d{1,3}$", text):
            pass  # rescue split pins
        else:
            return True
    x, y, w, h = bbox
    area = w * h
    max_dim = max(w, h)
    if text in {"+", "-", "+/-"} and area < 0.02 * max_dim * max_dim:
        return True
    # P2: Standalone "+" is always op_amp input noise on schematics.
    # Real "+" is part of a value like "+5V" and wouldn't be a separate WORD block.
    if text == "+":
        return True
    # P16e: Standalone "-" and "~" are schematic drawing artefacts
    # (wire segments, range markers).  Never meaningful as separate tokens.
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
    # P1: Ground symbol → "777" / "m" noise (2026-02-09)
    # Textract reads the ground symbol (three horizontal lines) as "777".
    # Drop standalone "777" — this is never a real component value on schematics.
    # Keep tokens like "777K", "777R" (unlikely but safe).
    # P10a: Keep standalone "7" — it appears as a valid IC pin number.
    # P11c-fix: "11" is a valid pin number — do NOT filter it.
    #   Ground symbol misreads are: "III"/"II" (letter-I bars), "777"/"77".
    up = text.upper()
    if up in {"777", "77"} and len(text) <= 3:
        return True
    # P11c: Ground symbol bars read as uppercase letter-I sequences
    # (e.g. "III" for 3 bars, "II" for 2 bars).  These are never valid
    # component designators or values on schematics.
    # P12c: Include "T" — Textract sometimes reads horizontal bars as T
    # (e.g. "ITT" for ground symbol on page26).
    if re.match(r"^[IlT|]{2,4}$", text) and len(text) <= 4:
        return True
    # Standalone lowercase "m" is ground-symbol noise. Keep "mA", "mV", "mW" etc.
    if text == "m":
        return True
    # P14a: Standalone uppercase "M" is motor-symbol noise — Textract reads
    # the letter inside the motor circle graphic.  Real component M403 has
    # digits after the prefix and is unaffected.  As a net label, standalone
    # "M" is extremely unlikely on schematics.
    if text == "M":
        return True
    # P11a: Ground symbol — single horizontal line read as "1" with low
    # confidence.  Real pin-number "1" has high confidence (>90).
    # Drop standalone "1" only when confidence is very low (<45).
    # B11b: Lowered from 60 to 45 — after B11 leading-zero strip,
    # connector pin "01" → "1" arrives at conf ~48 and must survive.
    if text == "1" and conf < 45:
        return True
    # P5: Standalone "=" (assignment sign in Polish schematics like R2=680K).
    # Drop it — pairing uses spatial proximity, not "=", and the sign
    # inserts a gap that breaks component→value matching.
    if text == "=":
        return True
    # P12d: Standalone ":" is stray noise — never a meaningful token on
    # schematics.  It distorts pairing when _combine_vertical_values
    # glues it to a real value (e.g. C424 ↔ ": 100/10" → "100/10").
    if text == ":":
        return True
    # P17d: Standalone "00" — inductor coil loops misread by Textract as
    # "OO" then converted to "00" by I/O→1/0 rules.  Not a valid
    # electronic value or designator.
    if text == "00":
        return True
    # P20e / B1 / B7: Wire endpoint & component symbol circles misread
    # as "O", "0", "o", "C" or "c".  Schematics use small open circles at
    # measurement/test points, wire endpoints, and in resistor symbols.
    # Textract reads them as letters or digit "0" with low confidence.
    # Standalone instances with conf < 55 → noise.
    # (Real pins/net labels "O"/"C" would have higher confidence.)
    if text in {"O", "0", "o", "C", "c"} and conf < 55:
        return True
    # B9: Removed — leading-zero tokens ("01", "02") are now handled
    # in _clean_token_text (B11) by stripping the leading zero before
    # the noise filter runs.  e.g. "01" → "1" (pin number preserved).
    # P17d-2: Standalone "#" — stray noise from schematic graphics.
    # Never a meaningful token; distorts pairing (e.g. D813 ↔ "# 1SS133").
    if text == "#":
        return True
    # P13b: Standalone "W" and "Y" are schematic symbol shapes misread
    # as letters.  "W" = resistor zigzag, "Y" = zener diode arrow.
    # Real net labels W/Y would have high confidence; symbol misreads
    # typically have low-to-moderate confidence.
    if text in {"W", "Y"} and conf < 80:
        return True
    # P18a: Standalone "MA" — resistor zigzag shape misread as letters.
    # The diagonal strokes of the zigzag pattern resemble "M" + "A".
    # Real "MA" net labels have high confidence; symbol misreads are
    # typically ≤55.  Guard with confidence threshold.
    if text == "MA" and conf < 55:
        return True
    # P15a: Asterisk noise — Textract reads junction dots or graphical
    # artifacts as "***" / "**" / "*".  Never meaningful on schematics.
    if text.strip("*") == "":
        return True
    # P16c: Common English words are never valid tokens on electronic
    # schematics.  Textract reads graphical shapes as short words like
    # "THE", "AND", "FOR", etc.  Drop them regardless of confidence.
    if up in {"THE", "AND", "FOR", "NOT", "BUT", "ARE", "HAS", "HAD"}:
        return True
    # P13c/P14b: Long digit-only strings (>5 chars) — IC pin numbers merged
    # into one WORD block by Textract (e.g. "12345678910").  Instead of
    # dropping entirely, we let them through and split them into individual
    # pin tokens in _split_merged_pins().  Non-sequential long-digit strings
    # are still dropped here.
    if text.isdigit() and len(text) > 5:
        if _parse_sequential_pins(text) is None:
            return True
        # Sequential pin string — keep for later splitting
    return False


# ---------------------------------------------------------------------------
# P14b: Parse & split merged IC pin numbers (2026-02-11)
# ---------------------------------------------------------------------------


def _parse_sequential_pins(text: str) -> Optional[List[int]]:
    """Try to parse a digit-only string as consecutive pin numbers.

    Returns a list of ints if the string is exactly the concatenation
    of ascending consecutive integers starting from 1.
    E.g. "12345678910" → [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].
    Returns None if the string does not match this pattern or has
    fewer than 3 pins (too ambiguous — "12" could be the number 12).
    """
    pos = 0
    expected = 1
    pins: List[int] = []
    while pos < len(text):
        s = str(expected)
        if text[pos : pos + len(s)] == s:
            pins.append(expected)
            pos += len(s)
            expected += 1
        else:
            return None
    return pins if len(pins) >= 3 else None


def _split_merged_pins(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace merged pin-number tokens with individual pin tokens.

    A token whose text is a sequential pin string (e.g. "12345678910")
    is exploded into N individual tokens, each with a proportionally
    divided bounding box.  The pin tokens are categorised as "net_label"
    (pin numbers function as labels on schematic overlays).

    Bounding box splitting:
    - If the original bbox is landscape (w >= h): split horizontally.
    - If portrait (h > w): split vertically (pins stacked along IC edge).
    """
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
        # Explode into individual pin tokens
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
            result.append(
                {
                    "text": pin_text,
                    "confidence": conf,
                    "bbox": (px, py, pw, ph),
                    "center": (cx, cy),
                    "category": "net_label",
                }
            )
    return result


# P1 cont.: Strip trailing "m" noise from ground symbol merged into value tokens
# e.g. "470Pm" → "470P", "22Km" → "22K"
_TRAILING_M_NOISE = re.compile(r"^(\d[\d.]*[PNFUKRΩ])[mM]$", re.IGNORECASE)

# P7: Ohm symbol misread as "s" / "S2" (2026-02-10)
# Polish schematics write Ω explicitly (e.g. 680KΩ).  Textract reads Ω as
# lowercase "s" or "S2".  Patterns: "680Ks" → "680KΩ", "22MS2" → "22MΩ".
_TRAILING_OHM_NOISE = re.compile(r"^(\d[\d.]*[kKmMGg]?)(?:[sS]2?|[sS][23]?)$")

# P6: Three-dot range notation "..." → "~" (tilde) (2026-02-10)
# Polish schematics use "10...30pF" meaning 10~30 pF.  Normalise for clarity.
# Using tilde instead of en-dash because en-dash renders as invisible/spaces
# in small overlay fonts.
_THREE_DOTS = re.compile(r"\.{2,4}")

# P5+: Compound token with embedded "=" (2026-02-10)
# Textract sometimes merges component+"="+value into one WORD block,
# e.g. "R1=22MS2".  We split and return component part so the value part
# gets picked up separately (Textract emits it as a second WORD block too).
# P20h: Also match compound tokens where component has no digits
# e.g. "RL=4Ω" (speaker load resistance = 4 ohm).
_COMPOUND_EQ = re.compile(r"^([A-Z]{1,3}\d*)=", re.IGNORECASE)

# P9d: Compound token WITHOUT "=" — component+value glued together
# e.g. "R46115K" → "R461".  Detected via _split_compound_noeq() function
# instead of a single regex, to correctly find the longest valid comp part.
_COMPOUND_NOEQ_COMP = re.compile(r"^(IC|[RCLQ])\d{2,3}$", re.IGNORECASE)
_COMPOUND_NOEQ_VAL = re.compile(r"^\d+[KMPRNUF]", re.IGNORECASE)


def _split_compound_noeq(text: str) -> str | None:
    """Try to split 'R46115K' into 'R461' (returned) + '15K' (discarded).

    Iterate split points, require comp part = known prefix + 2-3 digits,
    value part = digits + unit multiplier.  Return longest valid comp.
    """
    best = None
    for i in range(3, len(text) - 1):
        comp = text[:i]
        val = text[i:]
        if _COMPOUND_NOEQ_COMP.match(comp) and _COMPOUND_NOEQ_VAL.match(val):
            best = comp
    return best


# P8: Cyrillic→Latin transliteration + subscript/superscript normalisation
# (2026-02-10)
# Textract sometimes outputs Cyrillic homoglyphs instead of Latin letters
# (e.g. С U+0421 instead of C, р U+0440 instead of p) and Unicode subscript
# characters (e.g. ₛ U+209B instead of s).  On electronic schematics ALL text
# is Latin/ASCII, so we transliterate unconditionally.
_CYRILLIC_TO_LATIN: Dict[str, str] = {
    "\u0410": "A",
    "\u0412": "B",
    "\u0421": "C",
    "\u0415": "E",
    "\u041D": "H",
    "\u041A": "K",
    "\u041C": "M",
    "\u041E": "O",
    "\u0420": "P",
    "\u0422": "T",
    "\u0425": "X",
    # lowercase (except т → T: Textract misreads uppercase Latin T as Cyrillic т)
    "\u0430": "a",
    "\u0441": "c",
    "\u0435": "e",
    "\u043E": "o",
    "\u0440": "p",
    "\u0442": "T",
    "\u0445": "x",
    "\u0443": "y",
}

_SUBSCRIPT_TO_NORMAL: Dict[str, str] = {
    "\u2090": "a",
    "\u2091": "e",
    "\u2092": "o",
    "\u2093": "x",
    "\u2095": "h",
    "\u2096": "k",
    "\u2097": "l",
    "\u2098": "m",
    "\u2099": "n",
    "\u209A": "p",
    "\u209B": "s",
    "\u209C": "t",
    # superscript digits
    "\u00B9": "1",
    "\u00B2": "2",
    "\u00B3": "3",
}

_TRANSLITERATION = str.maketrans({**_CYRILLIC_TO_LATIN, **_SUBSCRIPT_TO_NORMAL})


def _clean_token_text(text: str) -> str:
    """Remove known OCR artefacts from token text."""
    # P8: Transliterate Cyrillic homoglyphs & subscripts → Latin FIRST,
    # so that downstream regexes (like _COMPOUND_EQ) can match ASCII.
    text = text.translate(_TRANSLITERATION)
    # P9a: Strip trailing quotes / double-quotes — never valid on schematics.
    # Textract sometimes appends '"' when bbox overlaps a nearby line.
    text = text.rstrip("\"'")
    # P20d: Textract reads µ (micro) as ",L" or ",U" on hand-drawn
    # schematics where the µ character has a downward tail.
    # e.g. "0,1,LF" → "0,1µF", "100,UF" → "100µF", "1000,uF" → "1000µF".
    # Also handles ",Lit" variant ("0,1,Lit" → "0,1µF").
    # Must run BEFORE comma→dot normalisation (P20c) so that the
    # second comma in "0,1,LF" is not converted to a dot.
    text = re.sub(r",LF$", "µF", text, flags=re.IGNORECASE)
    text = re.sub(r",UF$", "µF", text, flags=re.IGNORECASE)
    text = re.sub(r",Lit$", "µF", text, flags=re.IGNORECASE)
    # P20d-2: Standalone ",uF" / ",UF" after digits — comma is µ artefact.
    # e.g. "220,uF" → "220µF", "1000,uF" → "1000µF".
    text = re.sub(r"(\d),([uU]F)$", r"\1µF", text)
    # P20k: Space between value and unit — Textract splits "100 UF" / "220 uF".
    # Remove space and normalise unit: "100 UF" → "100µF", "100 uF" → "100µF".
    text = re.sub(r"^(\d+)\s+[uU]F$", r"\1µF", text)
    text = re.sub(r"^(\d+)\s+([KkMRPNFGpnΩ])$", r"\1\2", text)
    # P20c: Decimal-comma → dot normalisation.
    # European / international schematics use comma as the decimal
    # separator (e.g. "2,2nF", "8,2kΩ").  Normalise to dot so that
    # downstream comparisons and netlist export are consistent.
    # Only convert when a digit precedes and follows the comma.
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    # B11: Strip leading zero from 2-digit tokens — "01"→"1", "02"→"2".
    # Textract merges wire-endpoint circle "0" with nearby pin digit,
    # creating "01", "02" etc.  Stripping restores the real pin number.
    m_leading_zero = re.match(r"^0(\d)$", text)
    if m_leading_zero:
        text = m_leading_zero.group(1)
    # P12a: Connector-circle artifact — empty circles at wire endpoints
    # are read by Textract as "O" or "0" and glued to the adjacent net
    # label letter.  E.g. "OA" → "A", "0K" → "K".
    # Strip leading O/0 from 2-char tokens that would become a single
    # uppercase letter (common net label on schematics).
    if len(text) == 2 and text[0] in ("O", "0") and text[1].isalpha() and text[1].isupper():
        text = text[1]
    # P20p: Wire-endpoint circle misread as "O" merged with power rail.
    # Textract reads the small open circle at a track endpoint as letter
    # "O" and glues it to the adjacent power rail label "+UCC" → "O+UCC".
    # Strip leading "O"/"o" when followed by "+" and a letter.
    if re.match(r"^[Oo]\+[A-Za-z]", text):
        text = text[1:]
    # P11b: Textract confuses I↔1 and O↔0 in value tokens.
    # e.g. "IOOP" → "100P" (100 picofarads).  Only convert
    # when the result is a valid electronic value WITH a unit suffix.
    io_fixed = text.replace("I", "1").replace("O", "0")
    if io_fixed != text and re.match(r"^\d+\.?\d*[PNFUKRMGpnfukrmgΩ]$", io_fixed):
        text = io_fixed.upper()
    # P12c: Textract confuses S↔5 in value tokens.
    # e.g. "SK" → "5K" (5 kilohm resistor value).
    # Only convert when the result is a valid electronic value.
    s_fixed = text.replace("S", "5").replace("s", "5")
    if s_fixed != text and re.match(r"^\d+\.?\d*[PNFUKRMGpnfukrmgΩ]$", s_fixed):
        text = s_fixed
    # P15b: Textract confuses "2SC" → "25C" in transistor model numbers.
    # e.g. "25C1740" → "2SC1740".  The prefix "2S" denotes a Japanese
    # semiconductor (JIS).  "25C" followed by 3-4 digits is never a valid
    # electronic value — always a misread transistor model.
    if re.match(r"^25[A-Z]\d{3,4}$", text):
        text = "2S" + text[2:]
    # P16a: Textract confuses I↔1 inside JIS semiconductor model numbers.
    # e.g. "2SCI740" → "2SC1740", "2SDI009" → "2SD1009".
    # The model portion after the letter prefix (2SC / 2SD / 2SA / 2SB)
    # must be all digits.  Replace stray "I" and "O" with "1" and "0".
    m_jis = re.match(r"^(2S[A-Z])([\dIOlo]+)$", text)
    if m_jis:
        prefix, model = m_jis.group(1), m_jis.group(2)
        model_fixed = model.replace("I", "1").replace("O", "0").replace("l", "1").replace("o", "0")
        if model_fixed != model:
            text = prefix + model_fixed
    # P16b: Textract reads leading "1" as "I" in JIS diode series.
    # e.g. "ISS133" → "1SS133", "IN4148" → "1N4148".
    # Pattern: I + SS/N + digits — always a semiconductor part number.
    if re.match(r"^I(SS|N)\d{3,5}$", text):
        text = "1" + text[1:]
    # P16h: Textract reads "D" (diode prefix) as "0" — e.g. "0413" → "D413".
    # A standalone 4-digit token starting with 0 is extremely unlikely as a
    # value or pin number; it's almost always a misread diode designator.
    # P18c: Guard — don't convert "00xx" tokens (capacitor values like
    # 0082 = 82nF, 0047 = 47nF).  Real diodes are D1xx–D9xx.
    if re.match(r"^0[1-9]\d{2}$", text):
        text = "D" + text[1:]
    # P17a: Textract reads "8" as "B" in resistor designators — e.g.
    # "RB13" → "R813", "RB14" → "R814".  No real resistor starts
    # with "RB"; it is always a misread of the digit 8.
    if re.match(r"^RB\d{2,4}$", text):
        text = "R8" + text[2:]
    # P17g: Textract reads "8" as "B" and "0" as "O" in transistor
    # designators — e.g. "QBO6" → "Q806".  Valid Q* designators never
    # contain letters after the prefix; only digits.  Convert safely.
    if re.match(r"^Q[B8][O0]\d{1,3}$", text):
        text = "Q8" + text[2:].replace("O", "0")
    # P17b: Textract reads "8" as "B" after a decimal point in values —
    # e.g. "TZ-6.BC" → "TZ-6.8C".  A letter "B" immediately after
    # "<digit>." is almost certainly a misread "8".
    text = re.sub(r"(?<=\d\.)B", "8", text)
    # P17e: Textract reads "1" as "I" in inductor designators — e.g.
    # "LI02" → "L102".  No real inductor starts with "LI";
    # it is always a misread of the digit 1 after the "L" prefix.
    if re.match(r"^LI\d{2,3}$", text):
        text = "L1" + text[2:]
    # P19a: Ground-symbol prefix — Textract reads the ground symbol
    # lines as "m" and glues it to an adjacent value token.
    # e.g. "m5K" → "5K" (5 kilohm).  Strip leading lowercase "m"
    # when the remainder is a valid value with unit suffix.
    if re.match(r"^m\d+\.?\d*[KkMRPNFUGpnfuΩ]$", text):
        text = text[1:]
    # P20s: Textract reads handwritten "7" as "/" — the diagonal
    # stroke of 7 looks like a slash.  A standalone "/" on schematics
    # is never meaningful; convert to "7" (IC pin number).
    if text == "/":
        text = "7"
    # P15d: Strip trailing comma/period from pin numbers — Textract
    # sometimes appends punctuation from nearby graphical elements.
    # e.g. "19," → "19".  Only for short numeric tokens (≤3 digits).
    if re.match(r"^\d{1,3}[,.]$", text):
        text = text[:-1]
    # P9b: Leading "1" misread for "I" in IC designators: "1C408" → "IC408"
    if re.match(r"^1C\d{2,4}", text):
        text = "IC" + text[2:]
    m = _TRAILING_M_NOISE.match(text)
    if m:
        return m.group(1)
    # P5+: Strip "=value" suffix from compound tokens like "R1=22MS2" → "R1"
    meq = _COMPOUND_EQ.match(text)
    if meq:
        return meq.group(1)
    # P9d: Component+value glued without "=" e.g. "R46115K" → "R461"
    noeq_comp = _split_compound_noeq(text)
    if noeq_comp:
        return noeq_comp
    # P20q: Trailing ".00" → Ω — Textract misreads Ω symbol as ".00".
    # e.g. "270.00" → "270Ω".  Only for values with 2+ leading digits.
    # On schematics, values like "270.00" without unit never appear;
    # they are always "270Ω" or "270K" etc.
    m_dot00 = re.match(r"^(\d{2,})\.00$", text)
    if m_dot00:
        return m_dot00.group(1) + "Ω"
    # P20b: Trailing "g", "o", or "Q" misread as Ω on hand-drawn schematics.
    # The Ω character sometimes resembles "g", "o", or "Q" in hand-writing.
    # e.g. "100g" → "100Ω", "33kg" → "33kΩ", "5.6ko" → "5.6kΩ", "3.9KQ" → "3.9KΩ".
    # Only convert when preceded by digits and an optional multiplier.
    m_g_ohm = re.match(r"^(\d[\d.]*[kKM]?)[goQ]$", text)
    if m_g_ohm:
        return m_g_ohm.group(1) + "Ω"
    # B13: Trailing "52" = Ω misread — Textract reads the handwritten Ω
    # symbol as two digits "52" (upper curve ≈ "5", lower feet ≈ "2").
    # e.g. "1852" → "18Ω".  Guard: prefix must be 1-3 digits AND token
    # must be ≥4 chars (so "52" alone is not converted).
    if re.match(r"^\d{1,3}52$", text) and len(text) >= 4:
        return text[:-2] + "Ω"
    # P7: Trailing Ohm-as-"s" cleanup: "680Ks" → "680KΩ", "22MS2" → "22MΩ"
    # P16f: Guard — don't convert "2S" to "2Ω".  "2S" is the JIS
    # semiconductor prefix (2SA / 2SB / 2SC / 2SD), not "2 ohm".
    if text != "2S":
        mohm = _TRAILING_OHM_NOISE.match(text)
        if mohm:
            return mohm.group(1) + "Ω"
    # P6: Normalise "..." range to tilde
    if _THREE_DOTS.search(text):
        text = _THREE_DOTS.sub("~", text)
    return text


def _filter_tokens(blocks: List[Dict[str, Any]], w: int, h: int, min_conf: float) -> List[Dict[str, Any]]:
    tokens: List[Dict[str, Any]] = []
    for b in blocks:
        if b.get("BlockType") != "WORD":
            continue
        raw_text = b.get("Text", "").strip()
        text = _clean_token_text(raw_text)  # P1: clean noise artefacts
        conf = float(b.get("Confidence", 0.0))
        bbox_norm = b.get("Geometry", {}).get("BoundingBox")
        if not bbox_norm:
            continue
        bbox = _norm_bbox_to_px(bbox_norm, w, h)
        original_bbox = bbox  # preserve for compound-split value token

        # P5+/P9d: If compound token was split (e.g. "R1=22MS2" → "R1"
        # or "R46115K" → "R461"), shrink bbox proportionally so the
        # component part doesn't have an artificially wide bounding box.
        noeq_comp = None
        if len(text) < len(raw_text) and len(raw_text) > 0:
            noeq_comp = _split_compound_noeq(raw_text)
            if _COMPOUND_EQ.match(raw_text) or noeq_comp:
                ratio = len(text) / len(raw_text)
                x, y, bw, bh = bbox
                bbox = (x, y, bw * ratio, bh)

        # P20r: Compound-eq tokens (e.g. "RL=40") are high-signal —
        # if Textract found "X=value", the designator part is almost
        # certainly real.  Use relaxed confidence for both parts and
        # also emit the value token (which the eq-split normally loses).
        is_compound_eq = _COMPOUND_EQ.match(raw_text)
        effective_min_conf = 25.0 if is_compound_eq else min_conf

        if _should_drop_noise(text, bbox, effective_min_conf, conf):
            continue
        cat = _categorize(text)
        cx, cy = _bbox_center(bbox)
        tokens.append(
            {
                "text": text,
                "confidence": conf,
                "bbox": bbox,
                "center": (cx, cy),
                "category": cat,
            }
        )

        # P20r-2: Emit value token from compound-eq split.
        # e.g. "RL=40" → component "RL" (appended above) + value "40".
        if is_compound_eq:
            val_raw_eq = raw_text[is_compound_eq.end() :]
            val_text_eq = _clean_token_text(val_raw_eq)
            if val_text_eq and not _should_drop_noise(val_text_eq, original_bbox, 25.0, conf):
                ox, oy, obw, obh = original_bbox
                comp_len = is_compound_eq.end()  # includes '='
                comp_ratio = comp_len / len(raw_text) if len(raw_text) > 0 else 0.5
                val_bbox_eq = (ox + obw * comp_ratio, oy, obw * (1 - comp_ratio), obh)
                val_cx_eq, val_cy_eq = _bbox_center(val_bbox_eq)
                val_cat_eq = _categorize(val_text_eq)
                tokens.append(
                    {
                        "text": val_text_eq,
                        "confidence": conf,
                        "bbox": val_bbox_eq,
                        "center": (val_cx_eq, val_cy_eq),
                        "category": val_cat_eq,
                    }
                )

        # P10c: Create value token from compound no-eq split remainder.
        # e.g. "R46115K" → component "R461" (appended above) + value "15K".
        if noeq_comp:
            val_raw = raw_text[len(noeq_comp) :]
            val_text = _clean_token_text(val_raw)
            if val_text and not _should_drop_noise(val_text, original_bbox, min_conf, conf):
                ox, oy, obw, obh = original_bbox
                comp_ratio = len(noeq_comp) / len(raw_text)
                val_bbox = (ox + obw * comp_ratio, oy, obw * (1 - comp_ratio), obh)
                val_cx, val_cy = _bbox_center(val_bbox)
                val_cat = _categorize(val_text)
                tokens.append(
                    {
                        "text": val_text,
                        "confidence": conf,
                        "bbox": val_bbox,
                        "center": (val_cx, val_cy),
                        "category": val_cat,
                    }
                )

    # P14b: Split merged pin-number tokens (e.g. "12345678910" → 10 pins).
    tokens = _split_merged_pins(tokens)

    # P16g: Merge standalone unit-suffix letters (K, M, G, R, P, N, F, U)
    # with an adjacent numeric value token.  Textract sometimes splits
    # "180K" into "180" + "K" when there is a slight gap between the
    # number and the unit character.
    tokens = _merge_value_unit_suffix(tokens)

    # P9e: General substring deduplication — remove tokens whose text is
    # a substring (or trailing portion) of a longer nearby token.
    # Example: "31" near "IC407YM3531" → drop "31".
    tokens = _dedup_substring_tokens(tokens)

    # P13d: Merge horizontally adjacent "other" tokens on the same line.
    # Textract splits labels like "LOADING M." into separate WORD blocks;
    # we rejoin them when they share the same Y band and are close in X.
    tokens = _merge_horizontal_others(tokens)

    # P20i: Merge horizontally adjacent "net_label" tokens on the same line.
    # Textract splits multi-word labels like "Do drugiego kanału" into
    # separate WORD blocks; rejoin when same Y band and close in X.
    tokens = _merge_horizontal_net_labels(tokens)

    # P20j: Split space-separated pin numbers merged into one value token.
    # e.g. "4 12" → two separate net_label tokens "4" and "12".
    tokens = _split_space_separated_pins(tokens)

    # P21b: Merge value fragments split across lines by "/" separator.
    # e.g. "10µF/" + "25V" → "10µF/25V", or "100µF" + "/25V" → "100µF/25V".
    tokens = _merge_slash_value_fragments(tokens)

    # P22: Fix misread overline Q̄ on IC chips — OCR reads the negation
    # bar above Q as "I"; rename to "-Q" when vertically aligned.
    tokens = _fix_overline_q(tokens)

    # P23b: Merge words split across lines with a hyphen.
    # e.g. "cerami-" + "czny" → "ceramiczny".
    tokens = _merge_hyphenated_words(tokens)

    # B2: Fix wire-endpoint circle merged with adjacent net-label digit.
    # Textract sometimes reads a small open circle at a wire endpoint as
    # "0" and merges it with a nearby single-digit net label into a 2-digit
    # number (e.g. net_label "2" + circle "0" → "20" at moderate conf).
    tokens = _fix_wire_endpoint_digit_merge(tokens)
    return tokens


# ---------------------------------------------------------------------------
# P21b: Merge value fragments split across lines by "/" (2026-02-15)
# ---------------------------------------------------------------------------


def _merge_slash_value_fragments(
    tokens: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge value tokens split across two lines connected by '/'.

    Capacitor values are often written on two lines:
      "10µF/"   ← upper line, ends with /
      "25V"     ← lower line, continuation
    or:
      "100µF"   ← upper line
      "/25V"    ← lower line, starts with /

    This function detects such pairs and merges them into a single
    value token (e.g. "10µF/25V") with a combined bounding box.
    """
    # Pass 1: identify merge pairs (upper_idx → lower_idx)
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
                if dy <= 0:
                    continue
                if dx > max(t_bbox[2], 40):
                    continue
                if dy > t_h * 4:
                    continue
                if dy < best_dy:
                    best_dy = dy
                    best_j = j
            if best_j is not None:
                merge_map[i] = best_j
                claimed.add(i)
                claimed.add(best_j)
                continue

        # Case 2: token starting with "/" — find main value above
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
                if dy <= 0:
                    continue
                if dx > max(t_bbox[2], 40):
                    continue
                if dy > t_h * 4:
                    continue
                if dy < best_dy:
                    best_dy = dy
                    best_j = j
            if best_j is not None:
                merge_map[best_j] = i  # upper → lower
                claimed.add(i)
                claimed.add(best_j)
                continue

    # Pass 2: build result
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
        # Use upper token's center for pairing distance — the main value
        # (e.g. "100µF") is in the upper part; using the geometric center
        # of the combined bbox would push the point too far down.
        result.append(
            {
                "text": merged_text,
                "confidence": min(upper["confidence"], lower["confidence"]),
                "bbox": merged_bbox,
                "center": upper["center"],
                "category": "value",
            }
        )
    for i, tok in enumerate(tokens):
        if i not in claimed:
            result.append(tok)
    return result


# ---------------------------------------------------------------------------
# P22: Fix misread overline Q̄ on IC chips (2026-02-15)
# ---------------------------------------------------------------------------


def _fix_overline_q(
    tokens: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Rename misread overline-Q tokens from 'I' to '-Q'.

    On IC chips (e.g. CD4538), the complementary output is labeled Q̄
    (Q with an overline bar indicating negation).  Textract sometimes
    reads the overline bar + Q glyph as a single tall 'I' character,
    positioned directly below the regular 'Q' pin label.

    This function detects when an 'I' net_label is vertically aligned
    with (and below) a 'Q' net_label and renames it to '-Q'.
    """
    q_indices: List[int] = []
    i_indices: List[int] = []
    for idx, tok in enumerate(tokens):
        if tok.get("category") != "net_label":
            continue
        txt = tok.get("text", "")
        if txt == "Q":
            q_indices.append(idx)
        elif txt in ("I", "-", "|", "—"):
            i_indices.append(idx)

    for i_idx in i_indices:
        i_tok = tokens[i_idx]
        i_cx, i_cy = i_tok["center"]
        i_h = i_tok["bbox"][3]

        for q_idx in q_indices:
            q_tok = tokens[q_idx]
            q_cx, q_cy = q_tok["center"]

            dx = abs(i_cx - q_cx)
            dy = i_cy - q_cy  # positive ⇒ I is below Q

            # I must be nearly same x as Q and below it (within 10× height)
            max_dx = max(20, i_h * 1.5)
            if dx < max_dx and 0 < dy < i_h * 10:
                tokens[i_idx] = {
                    **i_tok,
                    "text": "-Q",
                }
                break

    return tokens


# ---------------------------------------------------------------------------
# P23b: Merge words split across lines with a hyphen (2026-02-15)
# ---------------------------------------------------------------------------


def _merge_hyphenated_words(
    tokens: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge words broken across lines with a trailing hyphen.

    When a word does not fit on one line, it is split with a hyphen at
    the end of the first fragment (e.g. "cerami-" on line 1, "czny"
    on line 2 → "ceramiczny").  This function detects such pairs and
    merges them, removing the hyphen.
    """
    consumed: set[int] = set()
    result: List[Dict[str, Any]] = []

    for i, tok in enumerate(tokens):
        if i in consumed:
            continue
        text = tok["text"]
        # Must end with a hyphen (and have at least 2 chars before it)
        if not (text.endswith("-") and len(text) >= 3):
            result.append(tok)
            continue

        # B3: Skip net_label tokens ending with "-".  In schematics,
        # trailing "-" on a net_label is a negation indicator
        # (e.g. "IN-" = inverting input, "CS-" = chip-select active low).
        # These must NOT be merged with the token below (typically a pin
        # number) — that would create nonsense like "IN4" from "IN-" + "4".
        if tok.get("category") == "net_label":
            result.append(tok)
            continue

        tx, ty = tok["center"]
        t_bbox = tok["bbox"]
        t_h = t_bbox[3]

        # Find the best continuation token below
        best_j: int | None = None
        best_dy = float("inf")
        for j, other in enumerate(tokens):
            if j == i or j in consumed:
                continue
            ox, oy = other["center"]
            # Must be below
            dy = oy - ty
            if dy <= 0:
                continue
            # Reasonable vertical distance (max 4× height)
            if dy > t_h * 4:
                continue
            # Horizontally aligned (within bounding box width + margin)
            dx = abs(ox - tx)
            if dx > max(t_bbox[2], 80):
                continue
            # Continuation should be text, not a component designator
            if other.get("category") == "component":
                continue
            if dy < best_dy:
                best_dy = dy
                best_j = j

        if best_j is not None:
            lower = tokens[best_j]
            # Merge: remove trailing hyphen, concatenate
            merged_text = text[:-1] + lower["text"]
            bboxes = [tok["bbox"], lower["bbox"]]
            min_x = min(b[0] for b in bboxes)
            min_y = min(b[1] for b in bboxes)
            max_x = max(b[0] + b[2] for b in bboxes)
            max_y = max(b[1] + b[3] for b in bboxes)
            merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
            avg_conf = (tok["confidence"] + lower["confidence"]) / 2
            consumed.add(i)
            consumed.add(best_j)
            result.append(
                {
                    "text": merged_text,
                    "confidence": avg_conf,
                    "bbox": merged_bbox,
                    "center": tok["center"],
                    "category": "other",
                }
            )
        else:
            result.append(tok)

    return result


# ---------------------------------------------------------------------------
# B2: Fix wire-endpoint circle merged with adjacent digit (2026-02-17)
# ---------------------------------------------------------------------------


def _fix_wire_endpoint_digit_merge(
    tokens: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Split 2-digit "X0" value tokens created by Textract merging a
    net-label digit with a wire-endpoint circle misread as "0".

    Schematics contain small open circles at wire endpoints / test points.
    Textract occasionally reads them as "0" and glues them to an adjacent
    net-label digit, creating a false 2-digit value (e.g. "2" + circle →
    "20" at moderate confidence).

    Detection criteria (all must hold):
      - Token text is exactly 2 digits, ending in "0", first digit non-zero
        (pattern: "10", "20", "30", …)
      - Category is "value"
      - Confidence < 85 (real values / pin numbers have higher confidence)
      - A single-digit net_label exists within 50 px radius
        (evidence that we are in a pin-numbering area)

    Action: strip trailing "0", shrink bbox to left half, reclassify as
    net_label with the first digit only.
    """
    # Build lookup of single-digit net labels for proximity check
    single_digit_labels = [
        t for t in tokens if t.get("category") == "net_label" and len(t["text"]) == 1 and t["text"].isdigit()
    ]

    result: List[Dict[str, Any]] = []
    for tok in tokens:
        text = tok["text"]
        conf = tok.get("confidence", 100.0)
        if (
            len(text) == 2
            and text.isdigit()
            and text[1] == "0"
            and text[0] != "0"
            and tok.get("category") == "value"
            and conf < 85
        ):
            cx, cy = tok["center"]
            # Check for a nearby single-digit net_label
            has_nearby_label = False
            for lbl in single_digit_labels:
                lx, ly = lbl["center"]
                if ((cx - lx) ** 2 + (cy - ly) ** 2) ** 0.5 <= 50:
                    has_nearby_label = True
                    break
            if has_nearby_label:
                # Strip trailing "0": keep only first digit
                new_text = text[0]
                x, y, w, h = tok["bbox"]
                new_w = w * 0.5  # approximate: first digit occupies left half
                new_bbox = (x, y, new_w, h)
                new_cx = x + new_w / 2.0
                new_cy = y + h / 2.0
                result.append(
                    {
                        "text": new_text,
                        "confidence": conf,
                        "bbox": new_bbox,
                        "center": (new_cx, new_cy),
                        "category": "net_label",
                    }
                )
                continue
        result.append(tok)
    return result


# ---------------------------------------------------------------------------
# P13d: Merge horizontally adjacent "other" category tokens (2026-02-11)
# ---------------------------------------------------------------------------


def _merge_horizontal_others(
    tokens: List[Dict[str, Any]], y_tol_ratio: float = 0.5, x_gap_ratio: float = 3.0
) -> List[Dict[str, Any]]:
    """Merge 'other' tokens that sit on the same horizontal line.

    Two tokens are merged when:
      - both are category == 'other'
      - vertical centres are within y_tol_ratio * max(h1, h2)
      - horizontal gap between right edge of left token and left edge of
        right token is ≤ x_gap_ratio * max(h1, h2)  (char-height proxy)
    """
    others = [(i, t) for i, t in enumerate(tokens) if t["category"] == "other"]
    if len(others) < 2:
        return tokens

    # Sort others by X
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
            # P20o: Use min(h) instead of max(h) for Y-band tolerance.
            # Prevents merging tokens with very different heights
            # (e.g. "log." h=0.036 vs "Wysokie" h=0.093) that happen
            # to overlap in Y because the taller token spans multiple lines.
            ref_h = min(lh, rh)
            # Same Y band?
            if abs(last["center"][1] - tok_b["center"][1]) > y_tol_ratio * ref_h:
                j += 1
                continue
            # Close in X?
            gap = rx - (lx + lw)
            if gap > x_gap_ratio * ref_h:
                j += 1
                continue
            group.append(tok_b)
            group_indices.append(idx_b)
            j += 1
        if len(group) > 1:
            # Only mark indices as merged when actually combined
            merged_indices.update(group_indices)
            # Build merged token
            texts = [g["text"] for g in group]
            bboxes = [g["bbox"] for g in group]
            min_x = min(b[0] for b in bboxes)
            min_y = min(b[1] for b in bboxes)
            max_x = max(b[0] + b[2] for b in bboxes)
            max_y = max(b[1] + b[3] for b in bboxes)
            merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
            avg_conf = sum(g["confidence"] for g in group) / len(group)
            new_tokens.append(
                {
                    "text": " ".join(texts),
                    "confidence": avg_conf,
                    "bbox": merged_bbox,
                    "center": _bbox_center(merged_bbox),
                    "category": "other",
                }
            )
        i += 1

    # Rebuild: keep non-other tokens + non-merged others + new merged tokens
    result = [t for i, t in enumerate(tokens) if i not in merged_indices]
    result.extend(new_tokens)
    return result


# ---------------------------------------------------------------------------
# P20i: Merge horizontally adjacent "net_label" tokens (2026-02-14)
# ---------------------------------------------------------------------------


def _merge_horizontal_net_labels(
    tokens: List[Dict[str, Any]], y_tol_ratio: float = 0.5, x_gap_ratio: float = 3.0
) -> List[Dict[str, Any]]:
    """Merge 'net_label' tokens on the same horizontal line.

    Analogous to _merge_horizontal_others but for net_labels.
    E.g. "Do" + "drugiego" + "kanału" → "Do drugiego kanału".
    """
    labels = [(i, t) for i, t in enumerate(tokens) if t["category"] == "net_label"]
    if len(labels) < 2:
        return tokens

    # Only merge tokens that are purely alphabetic (no digits, no unit chars)
    # to avoid merging real designator-adjacent net labels like "+5V" "GND".
    def _is_word_label(t: Dict[str, Any]) -> bool:
        txt = t["text"]
        # Pure word (letters, spaces, accented) — not a designator or value
        return bool(re.match(r"^[A-Za-zÀ-ž]+$", txt))

    # B14b: Filter out ALL-CAPS short tokens (≤6 chars) — they are
    # likely separate IC pin labels (e.g. TRHD, VSS, DOUT, FCS) and
    # should NOT be merged.  Only mixed-case / longer words qualify
    # for horizontal merge (e.g. "Do" + "drugiego" + "kanału").
    def _is_mergeable_word(t: Dict[str, Any]) -> bool:
        txt = t["text"]
        if not _is_word_label(t):
            return False
        # Short ALL-CAPS tokens are IC pin labels — skip
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
            new_tokens.append(
                {
                    "text": " ".join(texts),
                    "confidence": avg_conf,
                    "bbox": merged_bbox,
                    "center": _bbox_center(merged_bbox),
                    "category": "net_label",
                }
            )
        idx += 1

    result = [t for i, t in enumerate(tokens) if i not in merged_indices]
    result.extend(new_tokens)
    return result


# ---------------------------------------------------------------------------
# P20j: Split space-separated IC pin numbers (2026-02-14)
# ---------------------------------------------------------------------------


def _split_space_separated_pins(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Split value tokens like '4 12' into separate net_label tokens.

    Textract sometimes merges two IC pin numbers into one WORD block
    with a space.  The result is classified as 'value' (two groups of
    digits).  We detect this pattern and split into individual
    net_label pin tokens.
    """
    result: List[Dict[str, Any]] = []
    for tok in tokens:
        # Only split value tokens that are exactly "<digits> <digits>"
        if tok["category"] == "value":
            m = re.match(r"^(\d{1,3})\s+(\d{1,3})$", tok["text"])
            if m:
                pin1, pin2 = m.group(1), m.group(2)
                x, y, w, h = tok["bbox"]
                # Split bbox with a gap between the two pins.
                # Use character-width proportional split: each char
                # (including the space) gets equal width.  The space
                # becomes the gap between the two pin bboxes.
                total_chars = len(pin1) + 1 + len(pin2)  # +1 for space
                char_w = w / total_chars if total_chars > 0 else w
                w1 = char_w * len(pin1)
                gap = char_w  # space width
                w2 = char_w * len(pin2)
                bbox1 = (x, y, w1, h)
                bbox2 = (x + w1 + gap, y, w2, h)
                result.append(
                    {
                        "text": pin1,
                        "confidence": tok["confidence"],
                        "bbox": bbox1,
                        "center": _bbox_center(bbox1),
                        "category": "net_label",
                    }
                )
                result.append(
                    {
                        "text": pin2,
                        "confidence": tok["confidence"],
                        "bbox": bbox2,
                        "center": _bbox_center(bbox2),
                        "category": "net_label",
                    }
                )
                continue
        result.append(tok)
    return result


# ---------------------------------------------------------------------------
# P16g: Merge standalone unit-suffix letter with adjacent numeric value
# P20a: Extended to support multi-char suffixes (kΩ, nF, µF, etc.)
# ---------------------------------------------------------------------------

_UNIT_SUFFIXES = {"K", "M", "G", "R", "P", "N", "F", "U"}

# P20a: Multi-character unit suffixes that Textract may split from the
# preceding numeric value.  Includes OCR-confusion variants where Ω is
# misread as g / s / Q — these are corrected after merge via
# _clean_token_text (P20b).
_MULTI_UNIT_SUFFIXES = {
    "kΩ",
    "KΩ",
    "MΩ",
    "GΩ",
    "Ω",  # ohm variants
    "µF",
    "nF",
    "pF",
    "mF",  # farad sub-multiples
    "mV",
    "kV",
    "mA",
    "µA",  # volt / amp sub-multiples
    "kg",
    "ks",
    "kQ",
    "Mg",
    "Ms",
    "MQ",  # OCR confusion: g/s/Q = Ω
}


def _merge_value_unit_suffix(
    tokens: List[Dict[str, Any]],
    y_tol_ratio: float = 0.7,
    x_gap_max_px: float = 30.0,
) -> List[Dict[str, Any]]:
    """Merge a standalone unit suffix into an adjacent numeric value.

    Textract sometimes splits e.g. "180K" into two WORD blocks: "180"
    (value) and "K" (net_label).  We merge them when the unit suffix is
    within *x_gap_max_px* horizontally and on the same Y band.

    P20a: Also handles multi-character suffixes like "kΩ", "nF", "µF".
    P23a: Also handles vertical layout where the unit is on the line
          below the number (same X column, different Y).
    """
    # Two-pass approach: first identify all merges, then build result.
    # This prevents the bug where a numeric value token is appended to
    # result before a later unit suffix claims it via consumed.
    consumed: set[int] = set()
    new_merged: List[Dict[str, Any]] = []

    for i, tok in enumerate(tokens):
        if i in consumed:
            continue
        # Is this a standalone potential unit suffix (single or multi-char)?
        tok_text = tok["text"]
        is_single = tok_text in _UNIT_SUFFIXES and len(tok_text) == 1
        is_multi = tok_text in _MULTI_UNIT_SUFFIXES
        if not (is_single or is_multi):
            continue

        # ---- Strategy 1: horizontal (same Y band, unit to the right) ----
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

        # ---- Strategy 2 (P23a): vertical (unit below number) ----
        if best_j is None:
            best_dy = float("inf")
            for j, val in enumerate(tokens):
                if j == i or j in consumed:
                    continue
                vtext = val["text"]
                if not re.match(r"^\d+[.,]?\d*$", vtext):
                    continue
                vx, vy, vw, vh = val["bbox"]
                # X centres must be close (same column)
                dx = abs(tok["center"][0] - val["center"][0])
                max_w = max(uw, vw)
                if dx > max_w * 1.5:
                    continue
                # Unit must be BELOW the number
                dy = tok["center"][1] - val["center"][1]
                if dy <= 0:
                    continue
                # Max vertical gap: 3× height
                if dy > max(uh, vh) * 3:
                    continue
                if dy < best_dy:
                    best_dy = dy
                    best_j = j

        if best_j is not None:
            val_tok = tokens[best_j]
            merged_text = _clean_token_text(val_tok["text"] + tok["text"])
            vx, vy, vw, vh = val_tok["bbox"]
            min_x = min(vx, ux)
            min_y = min(vy, uy)
            max_x = max(vx + vw, ux + uw)
            max_y = max(vy + vh, uy + uh)
            merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
            avg_conf = (val_tok["confidence"] + tok["confidence"]) / 2
            consumed.add(i)
            consumed.add(best_j)
            new_merged.append(
                {
                    "text": merged_text,
                    "confidence": avg_conf,
                    "bbox": merged_bbox,
                    "center": _bbox_center(merged_bbox),
                    "category": "value",
                }
            )

    # Build result: keep non-consumed tokens, append merged tokens
    result = [tok for idx, tok in enumerate(tokens) if idx not in consumed]
    result.extend(new_merged)

    # --- Handle truncated-leading-digit cases like: '1' + '.2K' -> '1.2K'
    # P16i extension: Textract occasionally returns the leading digit as
    # a separate token. If a single-digit token sits immediately to the
    # left of a value token that starts with '.' we merge them.
    merged_indices: set[int] = set()
    adjusted: List[Dict[str, Any]] = []
    i = 0
    while i < len(result):
        if i in merged_indices:
            i += 1
            continue
        tok = result[i]
        # single leading digit candidate
        if re.match(r"^\d$", tok["text"]):
            # look for a right-hand neighbor that is a truncated value
            if i + 1 < len(result):
                right = result[i + 1]
                if re.match(r"^\.\d+", right["text"]):
                    # spatial check: must be on same band and close
                    dx = right["center"][0] - tok["center"][0]
                    dy = abs(right["center"][1] - tok["center"][1])
                    if 0 < dx < 80 and dy < max(tok["bbox"][3], right["bbox"][3]) * 0.6:
                        merged_text = _clean_token_text(tok["text"] + right["text"])
                        min_x = min(tok["bbox"][0], right["bbox"][0])
                        min_y = min(tok["bbox"][1], right["bbox"][1])
                        max_x = max(tok["bbox"][0] + tok["bbox"][2], right["bbox"][0] + right["bbox"][2])
                        max_y = max(tok["bbox"][1] + tok["bbox"][3], right["bbox"][1] + right["bbox"][3])
                        merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
                        avg_conf = (tok.get("confidence", 0) + right.get("confidence", 0)) / 2
                        adjusted.append(
                            {
                                "text": merged_text,
                                "confidence": avg_conf,
                                "bbox": merged_bbox,
                                "center": _bbox_center(merged_bbox),
                                "category": "value",
                            }
                        )
                        merged_indices.add(i)
                        merged_indices.add(i + 1)
                        i += 2
                        continue
        # default: keep token
        adjusted.append(tok)
        i += 1

    return adjusted


def _dedup_substring_tokens(tokens: List[Dict[str, Any]], proximity: float = 80.0) -> List[Dict[str, Any]]:
    """Remove tokens that are substrings of a longer, nearby token."""
    drop: set[int] = set()
    for i, short in enumerate(tokens):
        if i in drop:
            continue
        st = short["text"]
        if len(st) < 2:
            continue
        # P16i: Tokens starting with "." are truncated values (leading
        # digit clipped), e.g. ".2K" from "1.2K".  Don't dedup them
        # even if they're substrings of a nearby token (e.g. "2.2K").
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
            # P20t: Don't dedup digit-only pin tokens (e.g. "10")
            # against value tokens (e.g. "100µF").  IC pin numbers
            # legitimately appear near component values and should
            # not be removed.  Pure-digit tokens of 1-3 chars can be
            # categorised as either "net_label" (1 digit) or "value"
            # (2+ digits), but in both cases they may be pin numbers.
            # Dedup against *component* tokens is still valid
            # (e.g. "31" inside "IC407YM3531").
            # B14a: UNLESS the short token's centre lies inside the
            # long token's bbox — that means Textract re-read a
            # digit fragment of the same text (phantom duplicate).
            if re.match(r"^\d{1,3}$", st) and long_.get("category") == "value":
                _lx, _ly, _lw, _lh = long_["bbox"]
                _sx, _sy = short["center"]
                if not (_lx <= _sx <= _lx + _lw and _ly <= _sy <= _ly + _lh):
                    continue
            # Check spatial proximity
            sx, sy = short["center"]
            lx, ly = long_["center"]
            if abs(sx - lx) < proximity and abs(sy - ly) < proximity:
                drop.add(i)
                break
    # P12c: Drop single non-digit characters whose centre falls inside
    # the bounding box of a component token.  These are partial re-
    # readings of a digit in the component name (e.g. Textract reads
    # the "5" in "C425" a second time as "S").
    for i, single in enumerate(tokens):
        if i in drop:
            continue
        if len(single["text"]) != 1 or single["text"].isdigit():
            continue
        sx, sy = single["center"]
        for j, comp in enumerate(tokens):
            if j == i or j in drop:
                continue
            if len(comp["text"]) <= 1:
                continue
            if comp.get("category") != "component":
                continue
            lx, ly, lw, lh = comp["bbox"]
            if lx <= sx <= lx + lw and ly <= sy <= ly + lh:
                drop.add(i)
                break
    # B14a: Drop single-digit tokens whose centre falls inside the
    # bounding box of a longer value token that contains that digit.
    # E.g. Textract reads "330" but also emits a phantom "3" whose
    # bbox overlaps with "330".  Single-digit IC pin numbers do NOT
    # overlap with value bboxes, so this is safe.
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
            if len(val["text"]) <= 1:
                continue
            if st not in val["text"]:
                continue
            vx, vy, vw, vh = val["bbox"]
            if vx <= sx <= vx + vw and vy <= sy <= vy + vh:
                drop.add(i)
                break
    # B15: Drop single "0" tokens near inductor components (L-prefix).
    # Textract misreads the coil/inductor schematic symbol as "00";
    # B11 then normalises "00" → "0".  The resulting phantom "0" has
    # no meaning and should be removed.  Real pin "0" labels do not
    # exist on standard schematics.
    for i, single in enumerate(tokens):
        if i in drop:
            continue
        if single["text"] != "0":
            continue
        sx, sy = single["center"]
        for j, comp in enumerate(tokens):
            if j == i or j in drop:
                continue
            if comp.get("category") != "component":
                continue
            if not re.match(r"^L\d", comp["text"]):
                continue
            cx, cy = comp["center"]
            if abs(sx - cx) < proximity and abs(sy - cy) < proximity:
                drop.add(i)
                break
    return [t for i, t in enumerate(tokens) if i not in drop]


# ---------------------------------------------------------------------------
# P4: Merge single-char tokens arranged vertically into one token (2026-02-09)
# ---------------------------------------------------------------------------


def _merge_vertical_fragments(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge isolated short tokens (1-2 chars) that form a vertical column.

    Textract often splits vertically-oriented text into individual characters.
    We detect groups of ≥2 short tokens that are:
      - close horizontally (|dx| ≤ max char width * 1.5)
      - stacked vertically with small gaps (dy ≤ char height * 2.0)
    and merge them into a single token ONLY if the merged text forms a
    recognised component designator (R/C/L/Q/IC + digits) or value pattern.
    This prevents merging unrelated pin numbers or net labels.
    """
    if not tokens:
        return tokens

    # Candidates: tokens with exactly 1 char
    short_indices = [i for i, t in enumerate(tokens) if len(t["text"]) == 1 and t["text"].strip()]
    if len(short_indices) < 2:
        return tokens

    used: set[int] = set()
    merged_tokens: List[Dict[str, Any]] = []

    # Sort short tokens by X (primary) then Y (secondary) to find columns
    short_sorted = sorted(short_indices, key=lambda i: (tokens[i]["center"][0], tokens[i]["center"][1]))

    for start_pos, si in enumerate(short_sorted):
        if si in used:
            continue
        t0 = tokens[si]
        char_w = t0["bbox"][2]
        char_h = t0["bbox"][3]
        x_tol = max(char_w * 1.2, 15)
        y_max_gap = max(char_h * 2.0, 25)

        # Build a column starting from this token
        column = [si]
        last_bottom = t0["bbox"][1] + t0["bbox"][3]

        for next_pos in range(start_pos + 1, len(short_sorted)):
            nj = short_sorted[next_pos]
            if nj in used:
                continue
            tn = tokens[nj]
            dx = abs(tn["center"][0] - t0["center"][0])
            if dx > x_tol:
                break  # sorted by X, so further tokens are even farther
            gap = tn["bbox"][1] - last_bottom
            if gap < -char_h * 0.5:
                continue  # overlapping or above — skip
            if gap > y_max_gap:
                continue
            column.append(nj)
            last_bottom = tn["bbox"][1] + tn["bbox"][3]

        if len(column) < 2:
            continue

        # Sort column by Y
        column.sort(key=lambda i: tokens[i]["center"][1])

        # Merge: concatenate text, union bboxes
        parts = [tokens[i] for i in column]
        merged_text = "".join(p["text"] for p in parts)

        # GATE: only accept merge if result is a recognised component designator
        # (R/C/L/Q/IC + digits). This is very conservative — we only merge
        # vertical fragments that form component names, NOT values or net labels,
        # to avoid merging pin numbers or unrelated short tokens.
        # Require at least 3 chars (e.g. C41, R46) to avoid false "L0" etc.
        merged_cat = _categorize(merged_text)
        if merged_cat != "component":
            continue
        if len(merged_text) < 3:
            continue

        min_x = min(p["bbox"][0] for p in parts)
        min_y = min(p["bbox"][1] for p in parts)
        max_x = max(p["bbox"][0] + p["bbox"][2] for p in parts)
        max_y = max(p["bbox"][1] + p["bbox"][3] for p in parts)
        merged_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
        avg_conf = sum(p["confidence"] for p in parts) / len(parts)

        mcx, mcy = _bbox_center(merged_bbox)

        merged_tokens.append(
            {
                "text": merged_text,
                "confidence": avg_conf,
                "bbox": merged_bbox,
                "center": (mcx, mcy),
                "category": merged_cat,
            }
        )
        used.update(column)

    # Rebuild token list: keep non-used originals + add merged
    result = [t for i, t in enumerate(tokens) if i not in used]
    result.extend(merged_tokens)
    return result


# ---------------------------------------------------------------------------
# P25b: Merge split semiconductor prefix + body tokens  (2026-02-20)
# ---------------------------------------------------------------------------
_SEMI_PREFIX_FRAGMENTS = {"2S", "2N", "1S", "1N", "1SS"}

# Semiconductor body pattern: single letter (ABCDJK) + 3-4 digits + opt suffix
_SEMI_BODY_RE = re.compile(r"^[ABCDJK]\d{3,4}[A-Z]{0,2}$", re.IGNORECASE)


def _fix_semicon_fragments(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fix semiconductor model mis-classification.

    Handles two cases:
    1. Prefix split: Textract emits '2S' + 'C1740' as separate tokens.
       Merge them into '2SC1740' (value).
    2. Prefix lost: Textract only reads 'C1740' (no '2S' token).
       If a Q/D component is nearby, prepend '2S' and reclassify as value.
    """
    consumed: set[int] = set()
    new_merged: List[Dict[str, Any]] = []

    # --- Case 1: merge existing prefix + body tokens ---
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
            if not _SEMI_MODEL_RE.match(merged_cand):
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
            consumed.add(i)
            consumed.add(best_j)
            new_merged.append(
                {
                    "text": merged_text,
                    "confidence": avg_conf,
                    "bbox": merged_bbox,
                    "center": _bbox_center(merged_bbox),
                    "category": "value",
                }
            )

    result = [tok for idx, tok in enumerate(tokens) if idx not in consumed]
    result.extend(new_merged)

    # --- Case 2: prefix lost — C+4digits near a Q/D → restore '2S' prefix ---
    q_comps = [t for t in result if t.get("category") == "component" and t.get("text", "").upper()[:1] in {"Q", "D"}]
    if q_comps:
        for tok in result:
            if tok.get("category") != "component":
                continue
            txt = tok.get("text", "")
            if not re.match(r"^[ABCDJK]\d{4,}$", txt, re.IGNORECASE):
                continue
            candidate = "2S" + txt
            if not _SEMI_MODEL_RE.match(candidate):
                continue
            # Check if a Q/D component is close
            tx, ty = tok["center"]
            tw = tok["bbox"][2]
            th = tok["bbox"][3]
            for qc in q_comps:
                qx, qy = qc["center"]
                dist = ((qx - tx) ** 2 + (qy - ty) ** 2) ** 0.5
                if dist <= max(tw, th) * 5:
                    tok["text"] = candidate
                    tok["category"] = "value"
                    break

    return result


# ---------------------------------------------------------------------------
# P25e: Fix OCR letter ↔ digit confusion in IC designators  (2026-02-20)
# ---------------------------------------------------------------------------

# Common OCR confusions where a digit is mis-read as a letter.
_IC_OCR_LETTER_TO_DIGIT: Dict[str, str] = {
    "B": "8",
    "O": "0",
    "S": "5",
    "I": "1",
    "Z": "2",
    "G": "6",
    "D": "0",
}


def _fix_ic_ocr_confusion(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fix OCR confusion in IC designators, e.g. IC40B → IC408.

    Textract sometimes reads trailing digits as visually similar letters
    (8→B, 0→O, 5→S, etc.).  If a token starts with "IC", followed by
    digits and a single trailing letter that maps to a common OCR-confused
    digit, correct it and recategorise as ``component``.
    """
    for t in tokens:
        text = t["text"].strip()
        up = text.upper()
        if not up.startswith("IC") or len(up) < 4:
            continue
        suffix = up[2:]  # e.g. "40B"
        if suffix.isdigit():
            continue  # already correct
        # Pattern: one or more digits + single confused letter
        m = re.match(r"^(\d+)([A-Z])$", suffix)
        if not m:
            continue
        trailing = m.group(2)
        replacement = _IC_OCR_LETTER_TO_DIGIT.get(trailing)
        if replacement is None:
            continue
        fixed = f"IC{m.group(1)}{replacement}"
        t["text"] = fixed
        t["category"] = "component"
    return tokens


# ---------------------------------------------------------------------------
# P25c: Extend truncated vertical-merge designators  (2026-02-20)
# ---------------------------------------------------------------------------


def _extend_truncated_designators(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extend component designators that lost their last digit during vertical merge.

    After _merge_vertical_fragments, a designator like 'C411' may become
    'C41' because the final '1' was in a separate cluster or had a larger gap.
    This function looks for standalone single-digit tokens adjacent to the
    bottom of such designators and absorbs them.
    """
    comp_indices = [i for i, t in enumerate(tokens) if t.get("category") == "component"]
    single_digit_indices = [i for i, t in enumerate(tokens) if len(t.get("text", "")) == 1 and t["text"].isdigit()]

    if not comp_indices or not single_digit_indices:
        return tokens

    absorbed: set[int] = set()

    for ci in comp_indices:
        comp = tokens[ci]
        comp_text = comp["text"]
        # Only extend if component has digits (R41, C41, Q41 etc.)
        if not re.match(r"^[A-Z]{1,2}\d+$", comp_text, re.IGNORECASE):
            continue
        # P25e-guard: IC designators are already complete (IC408, IC434
        # etc.) — extending them with a nearby digit would create
        # invalid designators like IC4086.  Skip.
        if comp_text.upper().startswith("IC"):
            continue
        cx, cy = comp["center"]
        cb = comp["bbox"]  # (x, y, w, h)
        comp_bottom = cb[1] + cb[3]
        char_h = cb[3] / max(len(comp_text), 1)

        for di in single_digit_indices:
            if di in absorbed:
                continue
            digit = tokens[di]
            dx_val = abs(digit["center"][0] - cx)
            # Must be horizontally aligned
            if dx_val > max(cb[2] * 1.5, 20):
                continue
            # Must be directly below the component (small gap)
            gap = digit["bbox"][1] - comp_bottom
            if gap < -char_h * 0.5:
                continue
            if gap > char_h * 2.5:
                continue
            # Check that extended text is still a valid component
            ext_text = comp_text + digit["text"]
            if _categorize(ext_text) != "component":
                continue
            # Absorb
            comp["text"] = ext_text
            # Extend bbox
            min_x = min(cb[0], digit["bbox"][0])
            min_y = min(cb[1], digit["bbox"][1])
            max_x = max(cb[0] + cb[2], digit["bbox"][0] + digit["bbox"][2])
            max_y = max(cb[1] + cb[3], digit["bbox"][1] + digit["bbox"][3])
            comp["bbox"] = (min_x, min_y, max_x - min_x, max_y - min_y)
            comp["center"] = _bbox_center(comp["bbox"])
            cb = comp["bbox"]
            comp_bottom = cb[1] + cb[3]
            absorbed.add(di)
            break  # only one extension per designator per pass

    if absorbed:
        tokens = [t for i, t in enumerate(tokens) if i not in absorbed]
    return tokens


# ---------------------------------------------------------------------------
# P4+: Vertical-text rescue – crop+rotate+scale uncovered strips (2026-02-09)
# ---------------------------------------------------------------------------

_RESCUE_SCALE = 3
_RESCUE_PAD = 30
_RESCUE_ROTATE = 90  # CCW – turns top-to-bottom text into left-to-right
_RESCUE_MIN_CONF = 40.0
_RESCUE_MAX_STRIPS = 3
_RESCUE_SHORT_MAX_CHARS = 2  # tokens with ≤ this many chars are "short"
_RESCUE_SHORT_LOW_CONF = 70.0  # short tokens below this confidence are suspicious
_RESCUE_CLUSTER_X_TOL = 60  # px – max horizontal gap to group short tokens
_RESCUE_STRIP_MARGIN = 60  # px – margin added around detected clusters
_RESCUE_STRIP_WIDTH = 130  # px – preferred strip width (matched empirically)


def _detect_rescue_strips(
    tokens: List[Dict[str, Any]], img_w: int, img_h: int, _gray_array: Any = None
) -> List[Tuple[int, int, int, int]]:
    """Find vertical strips likely containing unread vertical text.

    Strategy: look for clusters of short (1-2 char), low-confidence tokens.
    These are typically fragments of vertical text that Textract split into
    individual characters instead of reading as whole words.
    Expand each cluster into a strip for re-OCR with rotation.
    """
    # 1. Gather short, low-confidence "fragment" tokens
    fragments = [
        t for t in tokens if len(t["text"]) <= _RESCUE_SHORT_MAX_CHARS and t["confidence"] < _RESCUE_SHORT_LOW_CONF
    ]
    if not fragments:
        return []

    # 2. Cluster fragments by X position
    fragments.sort(key=lambda t: t["center"][0])
    clusters: List[List[Dict[str, Any]]] = [[fragments[0]]]
    for t in fragments[1:]:
        if t["center"][0] - clusters[-1][-1]["center"][0] <= _RESCUE_CLUSTER_X_TOL:
            clusters[-1].append(t)
        else:
            clusters.append([t])

    # 3. Build strip boxes from clusters (full image height)
    strips: List[Tuple[int, int, int, int]] = []
    for cluster in clusters:
        min_x = min(t["bbox"][0] for t in cluster)
        max_x = max(t["bbox"][0] + t["bbox"][2] for t in cluster)
        center_x = (min_x + max_x) / 2.0
        cluster_span = max_x - min_x
        # Use preferred fixed width, but widen if cluster is broader
        strip_w = max(_RESCUE_STRIP_WIDTH, cluster_span + 20)
        half_w = strip_w / 2.0
        x1 = max(0, int(center_x - half_w))
        x2 = min(img_w, int(center_x + half_w))
        if x2 - x1 < 40:
            continue
        strips.append((x1, 0, x2, img_h))

    # 4. Merge overlapping strips
    if len(strips) > 1:
        strips.sort()
        merged: List[List[int]] = [list(strips[0])]
        for s in strips[1:]:
            if s[0] <= merged[-1][2]:
                merged[-1][2] = max(merged[-1][2], s[2])
            else:
                merged.append(list(s))
        strips = [tuple(m) for m in merged]  # type: ignore[misc]

    return strips[:_RESCUE_MAX_STRIPS]


def _rescue_vertical_text(
    image_path: Path,
    tokens: List[Dict[str, Any]],
    textract_client: Any,
    img_w: int,
    img_h: int,
) -> List[Dict[str, Any]]:
    """Detect uncovered vertical strips, crop+rotate+scale, re-OCR, map back.

    For each strip we try TWO preprocessing variants (padded, binarised) to
    counter Textract non-determinism, then merge all discovered tokens.

    Returns NEW tokens only (caller should deduplicate & extend).
    """
    strips = _detect_rescue_strips(tokens, img_w, img_h, None)
    if not strips:
        return []

    img_rgb = Image.open(image_path).convert("RGB")
    all_new: List[Dict[str, Any]] = []

    for sx1, sy1, sx2, sy2 in strips:
        crop_w = sx2 - sx1
        crop_h = sy2 - sy1
        crop = img_rgb.crop((sx1, sy1, sx2, sy2))

        # Build preprocessing variants
        # Try both rotation directions for vertical rescue (CCW and CW),
        # but *choose* the rotation whose OCR output is spatially consistent
        # with nearby component tokens (e.g. values should be below designators).
        per_rotation_tokens: dict[int, list[dict]] = {}
        comps = [t for t in tokens if t.get("category") == "component"]

        for rotation in (_RESCUE_ROTATE, -_RESCUE_ROTATE):
            collected: list[dict] = []

            # Variant A: rotate + scale + white padding
            rotated = crop.rotate(rotation, expand=True)
            rw, rh = rotated.size
            scaled = rotated.resize((rw * _RESCUE_SCALE, rh * _RESCUE_SCALE), Image.LANCZOS)
            variant_imgs = [ImageOps.expand(scaled, border=_RESCUE_PAD, fill="white")]

            # Variant B: rotate + scale + binarise (Otsu-like threshold)
            gray_crop = crop.convert("L")
            bin_arr = np.array(gray_crop)
            bin_arr = ((bin_arr >= 128) * 255).astype(np.uint8)
            bin_img = Image.fromarray(bin_arr).convert("RGB")
            rot_bin = bin_img.rotate(rotation, expand=True)
            rw2, rh2 = rot_bin.size
            scaled_bin = rot_bin.resize((rw2 * _RESCUE_SCALE, rh2 * _RESCUE_SCALE), Image.LANCZOS)
            variant_imgs.append(ImageOps.expand(scaled_bin, border=_RESCUE_PAD, fill="white"))

            # Collect WORDs from both preprocessing variants for this rotation
            for variant_img in variant_imgs:
                buf = io.BytesIO()
                variant_img.save(buf, format="PNG")

                try:
                    result = textract_client.analyze_document(
                        Document={"Bytes": buf.getvalue()},
                        FeatureTypes=["FORMS", "TABLES"],
                    )
                except Exception:
                    continue

                padded_w_px, padded_h_px = variant_img.size

                for block in result.get("Blocks", []):
                    if block.get("BlockType") != "WORD":
                        continue
                    text = block.get("Text", "").strip()
                    text = _clean_token_text(text)
                    conf = float(block.get("Confidence", 0))
                    if conf < _RESCUE_MIN_CONF:
                        continue

                    bb = block["Geometry"]["BoundingBox"]
                    # Textract normalised → padded pixel coords
                    px_left = bb["Left"] * padded_w_px
                    px_top = bb["Top"] * padded_h_px
                    px_w = bb["Width"] * padded_w_px
                    px_h = bb["Height"] * padded_h_px

                    # Remove padding
                    sc_left = px_left - _RESCUE_PAD
                    sc_top = px_top - _RESCUE_PAD

                    # Remove scaling
                    rot_left = sc_left / _RESCUE_SCALE
                    rot_top = sc_top / _RESCUE_SCALE
                    rot_w = px_w / _RESCUE_SCALE
                    rot_h = px_h / _RESCUE_SCALE

                    # Inverse rotation mapping depends on rotation angle.
                    if rotation == _RESCUE_ROTATE:  # 90° CCW (original behaviour)
                        orig_x = crop_w - rot_top - rot_h
                        orig_y = rot_left
                    else:  # -90° (CW)
                        orig_x = rot_top
                        orig_y = crop_h - rot_left - rot_w
                    orig_w = rot_h
                    orig_h = rot_w

                    # Map to full image coordinates
                    final_x = sx1 + orig_x
                    final_y = sy1 + orig_y
                    if final_x < 0 or final_y < 0:
                        continue

                    bbox = (final_x, final_y, orig_w, orig_h)
                    if _should_drop_noise(text, bbox, _RESCUE_MIN_CONF, conf):
                        continue

                    cat = _categorize(text)
                    cx = final_x + orig_w / 2.0
                    cy = final_y + orig_h / 2.0

                    collected.append(
                        {
                            "text": text,
                            "confidence": conf,
                            "bbox": bbox,
                            "center": (cx, cy),
                            "category": cat,
                            # tag rotation for later selection
                            "vertical_rotation": rotation,
                            "source": "vertical_rescue",
                        }
                    )

            # Deduplicate collected tokens for this rotation (keep highest-conf per approx center)
            deduped: list[dict] = []
            seen_centers: list[tuple[float, float]] = []
            for tok in sorted(collected, key=lambda t: -t["confidence"]):
                cx, cy = tok["center"]
                if any(abs(cx - sx) < 6 and abs(cy - sy) < 6 for sx, sy in seen_centers):
                    continue
                seen_centers.append((cx, cy))
                deduped.append(tok)

            per_rotation_tokens[rotation] = deduped

        # Choose the best rotation for this strip based on spatial consistency
        # with nearby components (values typically appear *below* designators).
        def _rotation_score(rot_toks: list[dict]) -> float:
            if not rot_toks:
                return 0.0
            sum_conf = sum(t.get("confidence", 0.0) for t in rot_toks)
            consistent = 0
            semicon_near = 0
            for t in rot_toks:
                # Count semicon-like tokens that appear near transistor/diode components
                tt = t.get("text", "")
                if _SEMI_MODEL_RE.match(tt):
                    # find nearest component
                    nearest = None
                    best_dx = float("inf")
                    for c in comps:
                        cx_c, cy_c = c["center"]
                        dx = abs(cx_c - t["center"][0])
                        if dx < best_dx:
                            best_dx = dx
                            nearest = c
                    if nearest is not None:
                        pref = nearest.get("text", "").upper()[:1]
                        if pref in {"Q", "D"} and best_dx <= max(nearest["bbox"][2] * 1.5, 60):
                            semicon_near += 1

                if t.get("category") != "value":
                    continue
                tx_cx, tx_cy = t["center"]
                # find nearest component horizontally
                nearest = None
                best_dx = float("inf")
                for c in comps:
                    cx_c, cy_c = c["center"]
                    dx = abs(cx_c - tx_cx)
                    if dx < best_dx:
                        best_dx = dx
                        nearest = c
                if nearest is None:
                    continue
                # distance threshold (allow fairly wide match)
                comp_w = nearest["bbox"][2]
                if best_dx > max(comp_w * 1.5, 60):
                    continue
                # value should be *below* component
                if tx_cy >= nearest["center"][1]:
                    consistent += 1
            # weighted score: semicon matches are strongest, then spatial consistency, then confidence
            return semicon_near * 5000.0 + consistent * 1000.0 + sum_conf

        rot_a = _RESCUE_ROTATE
        rot_b = -_RESCUE_ROTATE
        toks_a = per_rotation_tokens.get(rot_a, [])
        toks_b = per_rotation_tokens.get(rot_b, [])

        chosen_rot = None
        if toks_a and not toks_b:
            chosen_rot = rot_a
        elif toks_b and not toks_a:
            chosen_rot = rot_b
        else:
            score_a = _rotation_score(toks_a)
            score_b = _rotation_score(toks_b)
            if score_a > score_b:
                chosen_rot = rot_a
            elif score_b > score_a:
                chosen_rot = rot_b
            else:
                # tie-breaker: higher total confidence
                conf_a = sum(t.get("confidence", 0.0) for t in toks_a)
                conf_b = sum(t.get("confidence", 0.0) for t in toks_b)
                chosen_rot = rot_a if conf_a >= conf_b else rot_b

        # Append tokens from chosen rotation (dedup across global result)
        chosen_tokens = per_rotation_tokens.get(chosen_rot, []) if chosen_rot is not None else []
        for tok in chosen_tokens:
            # avoid adding duplicates already present in all_new
            cx, cy = tok["center"]
            if any(abs(cx - ex["center"][0]) < 6 and abs(cy - ex["center"][1]) < 6 for ex in all_new):
                continue
            all_new.append(tok)

    # Deduplicate: remove new tokens that overlap existing ones
    # First deduplicate rescue tokens against existing tokens
    unique = _deduplicate_tokens(tokens, all_new)
    # Then deduplicate among rescue tokens themselves (both variants may find same text)
    final: List[Dict[str, Any]] = []
    for t in unique:
        if not any(_bbox_iou(t["bbox"], f["bbox"]) > 0.3 for f in final):
            final.append(t)

    # Quality gate: only keep component designators and values with ≥ 2 chars.
    # Single-char and net_label/other noise (circuit lines read as "I", "y" etc.)
    # are common false positives in rotated crops.
    final = [t for t in final if t["category"] in ("component", "value") and len(t["text"]) >= 2]
    return final


def _bbox_iou(b1: Tuple[float, ...], b2: Tuple[float, ...]) -> float:
    """Intersection-over-union for two (x, y, w, h) bounding boxes."""
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[0] + b1[2], b2[0] + b2[2])
    y2 = min(b1[1] + b1[3], b2[1] + b2[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    a1 = b1[2] * b1[3]
    a2 = b2[2] * b2[3]
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def _deduplicate_tokens(
    existing: List[Dict[str, Any]],
    new_tokens: List[Dict[str, Any]],
    iou_threshold: float = 0.3,
) -> List[Dict[str, Any]]:
    """Return *new_tokens* that don't overlap significantly with *existing*.

    Also drops rescue tokens whose text is a substring of an existing token
    in the same spatial vicinity (even if IoU is low), to avoid partial
    duplicates like rescue "10–" vs. original "10–30pF".
    """
    unique: List[Dict[str, Any]] = []
    for nt in new_tokens:
        if any(_bbox_iou(nt["bbox"], et["bbox"]) > iou_threshold for et in existing):
            continue
        # P14c: Containment check — if more than 50% of the rescue token's
        # area overlaps with existing tokens (combined), it is a spurious
        # partial re-read of those tokens.
        # E.g. rescue "56" whose bbox spans the trailing digits of "D405"
        # and "TZ-5.6" stacked vertically → containment ≈ 88%.
        nt_bbox = nt["bbox"]
        nt_area = nt_bbox[2] * nt_bbox[3]
        if nt_area > 0:
            overlap_sum = 0.0
            for et in existing:
                eb = et["bbox"]
                ix1 = max(nt_bbox[0], eb[0])
                iy1 = max(nt_bbox[1], eb[1])
                ix2 = min(nt_bbox[0] + nt_bbox[2], eb[0] + eb[2])
                iy2 = min(nt_bbox[1] + nt_bbox[3], eb[1] + eb[3])
                if ix2 > ix1 and iy2 > iy1:
                    overlap_sum += (ix2 - ix1) * (iy2 - iy1)
            if overlap_sum / nt_area > 0.5:
                continue
        # P5+ substring guard: if rescue text is contained in an existing
        # token's text and their bboxes are nearby, skip the rescue token.
        # Also catch partial OCR variants like "10." vs "10–30pF" by comparing
        # leading digits.
        nt_text = nt.get("text", "")
        nt_digits = re.match(r"\d+", nt_text)
        nt_prefix = nt_digits.group() if nt_digits else ""
        skip = False
        for et in existing:
            et_text = et.get("text", "")
            if len(nt_text) >= len(et_text):
                continue
            # Check spatial proximity: centers within 50 px
            ncx, ncy = nt["center"]
            ecx, ecy = et["center"]
            if abs(ncx - ecx) >= 50 or abs(ncy - ecy) >= 50:
                continue
            # Exact substring match
            if nt_text in et_text:
                skip = True
                break
            # Leading-digits match: "10." is a partial read of "10–30pF"
            if nt_prefix and len(nt_prefix) >= 2 and et_text.startswith(nt_prefix):
                skip = True
                break
        if skip:
            continue
        unique.append(nt)
    return unique


def _pair_components_to_values(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    comps = [t for t in tokens if t["category"] == "component"]
    vals = [t for t in tokens if t["category"] == "value"]
    pairs: List[Dict[str, Any]] = []

    def _combine_vertical_values(
        main_val: Dict[str, Any],
        comp: Dict[str, Any],
        exclude_ids: set[int] | None = None,
    ) -> Tuple[str, Tuple[float, float, float, float]]:
        cx, cy = comp["center"]
        comp_w = comp["bbox"][2]
        comp_h = comp["bbox"][3]
        max_dim = max(comp_w, comp_h)
        parts = [(main_val["text"], main_val["bbox"])]

        # Szukaj sąsiednich wartości/tekstów w kolumnie pod komponentem
        # (blisko osi X komponentu i w krótkiej odległości)
        candidates = []
        main_w = main_val["bbox"][2]
        main_h = main_val["bbox"][3]
        horiz_tol = max(comp_w * 1.0, main_w * 1.0)
        max_step = max(main_h, comp_h) * 1.0
        max_span = max_dim * 1.0
        comp_text_up = comp.get("text", "").upper()
        if comp_text_up.startswith("IC"):
            horiz_tol *= 0.6
            max_step *= 0.5
            max_span = max_dim * 0.5
        # P25a: Capacitors often have value/voltage stacked (47 + 16)
        # which needs a slightly larger vertical span.
        elif comp_text_up.startswith("C"):
            max_span = max_dim * 1.5
        for val in tokens:
            if val is main_val:
                continue
            if exclude_ids and id(val) in exclude_ids:
                continue
            if comp_text_up.startswith("IC"):
                if val.get("category") not in {"net_label", "other"}:
                    continue
            else:
                if val.get("category") not in {"value", "net_label", "other"}:
                    continue
            val_text = val.get("text", "")
            # P25d: For transistors/diodes, skip pure-numeric passive values
            # in secondary combination — they are never part of a
            # semiconductor model string (e.g. 0.068 near Q418).
            if comp_text_up[:1] in {"Q", "D"} and re.match(r"^[\d.,/]+$", val_text):
                continue
            # P9f: Skip tokens that look like IC pin numbers (1-2 digit
            # standalone numbers) or component designators — these should
            # never be combined into a value string.
            # P25a: Exception for capacitors — allow short digit tokens
            # as the voltage part of capacitance/voltage notation (e.g.
            # "47" + "16" → "47/16" meaning 47µF/16V).  Only if the
            # token is close below the main value.
            if val_text.isdigit() and len(val_text) <= 2:
                if comp_text_up.startswith("C") and main_val["text"].isdigit():
                    vx_c, vy_c = val["center"]
                    dy_from_main = vy_c - main_val["center"][1]
                    dx_from_main = abs(vx_c - main_val["center"][0])
                    if dy_from_main <= 0 or dy_from_main > main_h * 3.0:
                        continue
                    if dx_from_main > max(main_w, comp_w) * 1.5:
                        continue
                    # passes — treat as voltage part
                else:
                    continue
            val_up = val_text.upper()
            if re.match(r"^(IC|[RCLQ])\d{2,4}$", val_up):
                continue
            vx, vy = val["center"]
            dx = abs(vx - cx)
            dy = vy - cy
            if dy < 0:  # tylko poniżej lub na tym samym poziomie
                continue
            if dy > max_span:
                continue
            if dx > horiz_tol:
                continue
            candidates.append((val["text"], val["bbox"], vy))

        # Sortuj po Y, potem X, ale dodawaj tylko jeśli odległość w pionie jest niewielka (ciągła kolumna)
        candidates.sort(key=lambda p: (p[1][1], p[1][0]))
        last_bottom = main_val["bbox"][1] + main_val["bbox"][3]
        added = 0
        for text, bb, _ in candidates:
            gap = bb[1] - last_bottom
            if gap > max_step:
                continue
            parts.append((text, bb))
            last_bottom = bb[1] + bb[3]
            added += 1
            if comp_text_up.startswith("IC") and added >= 1:
                break
            if not comp_text_up.startswith("IC") and added >= 2:
                break

        parts_sorted = sorted(parts, key=lambda p: (p[1][1], p[1][0]))
        texts = [p[0] for p in parts_sorted]
        bboxes = [p[1] for p in parts_sorted]

        # Heuristic normalisation for fraction-like values observed in cd138d40
        # (e.g. Textract produced "01/47" for a capacitor that is likely
        # "47/10" meaning 47µF/10V).  Only apply when component is a
        # capacitor to avoid incorrect rewrites for other component types.
        if comp_text_up.startswith("C"):
            norm_texts: list[str] = []
            for t in texts:
                if re.match(r"^0?1/\d{2}$", t):
                    # Swap and normalise leading '01' → voltage '10'
                    m = re.match(r"^0?1/(\d{2})$", t)
                    if m:
                        norm_texts.append(f"{m.group(1)}/10")
                        continue
                norm_texts.append(t)
            texts = norm_texts

        # P25a: For capacitors with two pure-digit parts, join with
        # '/' to form capacitance/voltage notation (e.g. "47" + "16" → "47/16").
        if comp_text_up.startswith("C") and len(texts) == 2 and all(t.isdigit() for t in texts):
            combined = "/".join(texts)
        else:
            combined = " ".join(texts)

        min_x = min(b[0] for b in bboxes)
        min_y = min(b[1] for b in bboxes)
        max_x = max(b[0] + b[2] for b in bboxes)
        max_y = max(b[1] + b[3] for b in bboxes)
        return combined, (min_x, min_y, max_x - min_x, max_y - min_y)

    # --- Pass 1: find primary value for each component ---
    primary_assignments: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []

    for comp in comps:
        best = None
        cx, cy = comp["center"]
        comp_w = comp["bbox"][2]
        comp_h = comp["bbox"][3]
        max_dim = max(comp_w, comp_h)
        max_dist = max_dim * 3.5
        comp_text_up = comp.get("text", "").upper()
        candidate_vals = vals
        if comp_text_up.startswith("IC"):
            extra = [t for t in tokens if t["category"] in {"net_label", "other"} and len(t.get("text", "")) >= 3]
            candidate_vals = vals + extra

        vertical_band_down: list[tuple[float, Dict[str, Any]]] = []
        right_band: list[tuple[float, Dict[str, Any]]] = []

        for val in candidate_vals:
            # P10d: For IC components, skip standalone 1-2 digit numbers —
            # typically IC pin numbers, not valid IC values.
            # For passive components (R, C, L, Q) these ARE valid values
            # (e.g. 56Ω, 33Ω).
            vt = val.get("text", "")
            if comp_text_up.startswith("IC") and vt.isdigit() and len(vt) <= 2:
                continue
            # P25e: For IC components, skip passive-style values (e.g.
            # "15K", "100K", "22K", "100P").  IC values are model
            # numbers (e.g. "YM3531", "LM741"), never digit+unit.
            if comp_text_up.startswith("IC") and re.match(r"^\d+\.?\d*[KkMΩRPNFGpnfuUV]$", vt):
                continue
            vx, vy = val["center"]
            dx = abs(vx - cx)
            dy = vy - cy
            if (dx * dx + dy * dy) ** 0.5 > max_dist:
                continue
            # pion w dół: wąski pas
            # P9c: Rozluźniony dx z 0.2 na 0.5 — wartości nie zawsze
            # są idealnie wycentrowane pod komponentem.
            # B6: Rozszerzony zasięg dy z 1.0× na 2.0× max_dim — na
            # schematach japońskich wartość bywa nieco dalej pod
            # designatorem (np. L1L→2u0, R7L→10k, C24P→680p).
            if vy >= cy and dx <= comp_w * 0.5 and dy <= max_dim * 2.0:
                vertical_band_down.append((dy, val))
            # prawa strona: prawie poziomo, krótki zasięg w Y
            # P5: Rozluźniony zasięg dx (3× max_dim) — w polskich schematach
            # wartość stoi po "=" dalej od komponentu niż w japońskich.
            if vx >= cx and abs(dy) <= comp_h * 0.5 and dx <= max_dim * 3.0:
                right_band.append((dx, val))
            # B5: Usunięty vertical_band_up — na schematach elektronicznych
            # designator jest zawsze NAD wartością (czytamy od góry do dołu).
            # Wartość nie może być wyżej od designatora.

        chosen = None
        if vertical_band_down:
            vertical_band_down.sort(key=lambda t: t[0])
            # P10e: If the closest candidate is a plain 1-2 digit number
            # but there's a "richer" value (contains '.', letter, or unit)
            # in the same band, prefer the richer value.  Plain 2-digit
            # numbers near ICs are usually pin numbers, not values.
            best_vbd = vertical_band_down[0][1]
            best_text = best_vbd.get("text", "")
            if best_text.isdigit() and len(best_text) <= 2 and len(vertical_band_down) > 1:
                for _, alt_val in vertical_band_down[1:]:
                    alt_text = alt_val.get("text", "")
                    if not (alt_text.isdigit() and len(alt_text) <= 2):
                        best_vbd = alt_val
                        break
            chosen = best_vbd
        elif right_band:
            right_band.sort(key=lambda t: t[0])
            chosen = right_band[0][1]

        # P21d: If chosen is a plain 1-2 digit number (likely IC pin),
        # check for a richer alternative (with unit letters) nearby.
        # Plain 2-digit numbers CAN be valid values (e.g. 56Ω) but if
        # a descriptive value exists within range, it’s almost always the
        # correct pairing for a passive component.
        if chosen and not comp_text_up.startswith("IC"):
            ct = chosen.get("text", "")
            if ct.isdigit() and len(ct) <= 2:
                chosen_dist = ((cx - chosen["center"][0]) ** 2 + (cy - chosen["center"][1]) ** 2) ** 0.5
                alt_best: Dict[str, Any] | None = None
                alt_best_dist = float("inf")
                for val in candidate_vals:
                    if val is chosen:
                        continue
                    vt2 = val.get("text", "")
                    if vt2.isdigit() and len(vt2) <= 2:
                        continue
                    if not any(ch.isalpha() for ch in vt2):
                        continue
                    # B5: Skip semiconductor model numbers for passive
                    # components (R/C/L/T) — e.g. don't swap R25L's "10"
                    # for a distant 1N4007.
                    if _SEMI_MODEL_RE.match(vt2) and comp_text_up[:1] in {"C", "R", "L", "T"}:
                        continue
                    vx2, vy2 = val["center"]
                    # B5: Value cannot be significantly above designator
                    # (top-to-bottom rule).  Allow comp_h*0.5 tolerance
                    # for same-level values with minor vertical offset.
                    if vy2 < cy - comp_h * 0.5:
                        continue
                    d2 = ((cx - vx2) ** 2 + (cy - vy2) ** 2) ** 0.5
                    if d2 <= max_dist and d2 <= chosen_dist * 2.5 and d2 < alt_best_dist:
                        alt_best_dist = d2
                        alt_best = val
                if alt_best is not None:
                    chosen = alt_best

        # P21a: General nearest fallback — if no geometric band matched,
        # pick the nearest value within max_dist.  Lowest priority.
        # B5: Enforce top-to-bottom — value must not be above designator.
        if not chosen:
            general_nearby: list[tuple[float, Dict[str, Any]]] = []
            for val in candidate_vals:
                vt = val.get("text", "")
                if comp_text_up.startswith("IC") and vt.isdigit() and len(vt) <= 2:
                    continue
                # P25e: IC — skip passive-style values in fallback too.
                if comp_text_up.startswith("IC") and re.match(r"^\d+\.?\d*[KkMΩRPNFGpnfuUV]$", vt):
                    continue
                vx, vy = val["center"]
                # B5: Value cannot be significantly above designator
                # (top-to-bottom rule).  Allow comp_h*0.5 tolerance
                # for same-level values with minor vertical offset.
                if vy < cy - comp_h * 0.5:
                    continue
                dist = ((cx - vx) ** 2 + (cy - vy) ** 2) ** 0.5
                if dist <= max_dist:
                    general_nearby.append((dist, val))
            if general_nearby:
                general_nearby.sort(key=lambda t: t[0])
                chosen = general_nearby[0][1]

        # B4: Semantic affinity — transistors (Q-prefix) should pair with
        # semiconductor model numbers (2SC2631, BC547, 2SA1015) rather than
        # passive values (1m0, 47u, 680p).  Without this, a Q-component
        # can steal a nearby capacitor value from a C-component and end up
        # paired with a wrong model number via retry.
        # Symmetric rule: passive components (C/R/L-prefix) prefer
        # non-semiconductor values when a semiconductor model was chosen.
        if chosen:
            chosen_text = chosen.get("text", "")
            chosen_is_semi = bool(_SEMI_MODEL_RE.match(chosen_text))
            prefix = comp_text_up[:1]
            # Distance to the currently-chosen value (used by override checks)
            chosen_dist = ((cx - chosen["center"][0]) ** 2 + (cy - chosen["center"][1]) ** 2) ** 0.5

            if prefix in {"Q", "D"} and not chosen_is_semi:
                # P25d: Transistors/diodes NEVER have pure-numeric passive
                # values like "0.068", "47", "100" — these are always
                # capacitor/resistor values.  Check if the chosen value is
                # a clearly-passive pattern (digits + optional decimal).
                _is_clearly_passive = bool(re.match(r"^[\d.,/]+$", chosen_text))

                # Transistor/diode picked a passive value — prefer a
                # semiconductor model.  If the value is clearly passive
                # (pure numeric), use a much more relaxed threshold
                # (1.5×) so semi models win even if slightly farther.
                semi_nearby: list[tuple[float, Dict[str, Any]]] = []
                for val in candidate_vals:
                    vt = val.get("text", "")
                    if _SEMI_MODEL_RE.match(vt):
                        vx, vy = val["center"]
                        # B5: Value cannot be significantly above designator.
                        if vy < cy - comp_h * 0.5:
                            continue
                        dist = ((cx - vx) ** 2 + (cy - vy) ** 2) ** 0.5
                        if dist <= max_dist:
                            semi_nearby.append((dist, val))
                if semi_nearby:
                    semi_nearby.sort(key=lambda t: t[0])
                    semi_dist, semi_val = semi_nearby[0]
                    # Relaxed threshold for clearly-passive values;
                    # strict threshold otherwise.
                    threshold = 1.5 if _is_clearly_passive else 0.75
                    if semi_dist < chosen_dist * threshold:
                        chosen = semi_val
                elif _is_clearly_passive:
                    # No semiconductor model available, and the value is
                    # clearly passive — refuse pairing so that the correct
                    # passive component (C/R/L) can claim it instead.
                    chosen = None

            elif prefix in {"C", "R", "L", "T"} and chosen_is_semi:
                # Passive component picked a semiconductor model — prefer a
                # non-semiconductor value only if it's clearly closer.
                passive_nearby: list[tuple[float, Dict[str, Any]]] = []
                for val in candidate_vals:
                    vt = val.get("text", "")
                    if not _SEMI_MODEL_RE.match(vt):
                        vx, vy = val["center"]
                        # B5: Value cannot be significantly above designator.
                        if vy < cy - comp_h * 0.5:
                            continue
                        dist = ((cx - vx) ** 2 + (cy - vy) ** 2) ** 0.5
                        if dist <= max_dist:
                            passive_nearby.append((dist, val))
                if passive_nearby:
                    passive_nearby.sort(key=lambda t: t[0])
                    pass_dist, pass_val = passive_nearby[0]
                    if pass_dist < chosen_dist * 0.75:
                        chosen = pass_val

        if chosen:
            best = chosen
        if best:
            primary_assignments.append((comp, best))

    # P10b: Exclusive pairing — if multiple components claim the same
    # value token, the closest component wins.  Prevents e.g. IC408
    # from stealing R819's "100" or R461 from stealing C815's "10/16".
    val_claims: Dict[int, List[Tuple[float, int]]] = {}
    for i, (comp, val) in enumerate(primary_assignments):
        cx2, cy2 = comp["center"]
        vx2, vy2 = val["center"]
        dist = ((cx2 - vx2) ** 2 + (cy2 - vy2) ** 2) ** 0.5
        key = id(val)
        if key not in val_claims:
            val_claims[key] = []
        val_claims[key].append((dist, i))
    losers: set[int] = set()
    for claims in val_claims.values():
        if len(claims) > 1:
            claims.sort()
            for _, idx in claims[1:]:
                losers.add(idx)
    # P21c: Save original assignments before removing losers for retry.
    original_primary = list(primary_assignments)
    if losers:
        primary_assignments = [(c, v) for i, (c, v) in enumerate(primary_assignments) if i not in losers]

    # P21c: Retry for exclusive-pairing losers — when a component loses
    # its value to a closer component, try to find next-nearest unassigned value.
    if losers:
        assigned_val_ids_retry = {id(v) for _, v in primary_assignments}
        loser_comps = [c for i, (c, _v) in enumerate(original_primary) if i in losers]
        for comp_l in loser_comps:
            cx_l, cy_l = comp_l["center"]
            comp_w_l = comp_l["bbox"][2]
            comp_h_l = comp_l["bbox"][3]
            max_dim_l = max(comp_w_l, comp_h_l)
            max_dist_l = max_dim_l * 3.5
            comp_text_up_l = comp_l.get("text", "").upper()
            nearby: list[tuple[float, Dict[str, Any]]] = []
            for val in vals:
                if id(val) in assigned_val_ids_retry:
                    continue
                vt_l = val.get("text", "")
                # P25e: IC retry — skip passive values (same as Pass 1).
                if comp_text_up_l.startswith("IC") and re.match(r"^\d+\.?\d*[KkMΩRPNFGpnfuUV]$", vt_l):
                    continue
                vx, vy = val["center"]
                # B5: Value cannot be significantly above designator.
                if vy < cy_l - comp_h_l * 0.5:
                    continue
                dist = ((cx_l - vx) ** 2 + (cy_l - vy) ** 2) ** 0.5
                if dist <= max_dist_l:
                    nearby.append((dist, val))
            if nearby:
                nearby.sort(key=lambda t: t[0])
                best_retry = nearby[0][1]
                primary_assignments.append((comp_l, best_retry))
                assigned_val_ids_retry.add(id(best_retry))

    # --- Pass 2: combine with secondary values, excluding other primaries ---
    primary_val_ids = {id(val) for _, val in primary_assignments}

    for comp, primary_val in primary_assignments:
        # Exclude other components' primary values from the combine step
        exclude = primary_val_ids - {id(primary_val)}
        combined_text, combined_bbox = _combine_vertical_values(primary_val, comp, exclude_ids=exclude)
        cbx, cby, cbw, cbh = combined_bbox
        combined_center = (cbx + cbw / 2.0, cby + cbh / 2.0)
        pairs.append(
            {
                "component": comp["text"],
                "value": combined_text,
                "component_bbox": comp["bbox"],
                "value_bbox": combined_bbox,
                "component_center": comp["center"],
                "value_center": combined_center,
                "cost": 0.0,
            }
        )
    return pairs


# ---------------------------------------------------------------------------
# P3: Repair truncated IC designators ("C408" → "IC408")  (2026-02-09)
# ---------------------------------------------------------------------------
_IC_RE = re.compile(r"IC(\d{2,4})", re.IGNORECASE)
_LONE_C_RE = re.compile(r"^C(\d{3,4})$")


def _fix_truncated_ic(
    tokens: List[Dict[str, Any]], pairs: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Detect C-designators that are really ICs with a truncated 'I'.

    Must be called AFTER _pair_components_to_values().
    Heuristic: if a C-designator shares the hundred-series of a known IC
    AND was NOT paired with any value (no capacitance found), rename it.
    """
    # 1. Collect hundred-series of known ICs (e.g. IC407 → 4)
    ic_hundreds: set[int] = set()
    for t in tokens:
        m = _IC_RE.search(t["text"])
        if m:
            num = int(m.group(1))
            ic_hundreds.add(num // 100)

    if not ic_hundreds:
        return tokens, pairs

    # 2. Build set of paired component names
    paired_comps = {p["component"] for p in pairs}

    # 3. Fix unpaired C-designators whose hundred matches an IC series
    for t in tokens:
        m2 = _LONE_C_RE.match(t["text"])
        if not m2:
            continue
        if t["text"] in paired_comps:
            continue  # real capacitor — it has a paired value
        num = int(m2.group(1))
        if num // 100 in ic_hundreds:
            t["text"] = f"IC{num}"
            t["category"] = "component"

    return tokens, pairs


def _draw_overlay(image_path: Path, tokens: List[Dict[str, Any]], pairs: List[Dict[str, Any]], out_path: Path) -> None:
    im = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(im)
    # P8+: Use a TrueType font that supports Unicode (Ω, –, etc.)
    # instead of PIL's built-in bitmap font which shows □ for non-ASCII.
    # P14d: Increased size 14→18 so that thin glyphs (dash "-", dot ".")
    # are clearly visible on large overlay images.
    font = ImageFont.load_default()
    for candidate in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "consola.ttf"):
        try:
            font = ImageFont.truetype(candidate, size=18)
            break
        except (OSError, IOError):
            continue
    colors = {
        "component": (255, 0, 0),
        "value": (0, 128, 255),
        "net_label": (0, 0, 255),
        "other": (0, 200, 0),
    }
    for t in tokens:
        x, y, w, h = t["bbox"]
        c = colors.get(t["category"], (0, 200, 0))
        draw.rectangle([x, y, x + w, y + h], outline=c, width=3)
        draw.text((x, max(0, y - 10)), t["text"], fill=c, font=font)
    for p in pairs:
        (cx, cy) = p["component_center"]
        (vx, vy) = p["value_center"]
        draw.line([cx, cy, vx, vy], fill=(255, 0, 255), width=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_path)


def _rasterize_pdf(pdf_path: Path, req_id: str) -> Path | None:
    if fitz is None:
        return None
    try:
        doc = fitz.open(pdf_path)
        if not doc:
            return None
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=200)
        out_path = pdf_path.with_suffix("").parent / f"{req_id}_{pdf_path.stem}.png"
        pix.save(out_path)
        return out_path
    except Exception:  # pragma: no cover - best effort
        return None


def _rasterize_pdf_pages(pdf_path: Path, req_id: str, page_numbers: List[int], dpi: int = 200) -> Dict[int, Path]:
    """Rasteryzuje wybrane strony PDF do PNG. Zwraca mapę: nr_strony -> ścieżka."""
    if fitz is None:
        return {}
    try:
        doc = fitz.open(pdf_path)
        result: Dict[int, Path] = {}
        for pnum in page_numbers:
            idx = pnum - 1
            if idx < 0 or idx >= len(doc):
                continue
            page = doc.load_page(idx)
            pix = page.get_pixmap(dpi=dpi)
            out_path = pdf_path.with_suffix("").parent / f"{req_id}_{pdf_path.stem}_p{pnum}.png"
            pix.save(out_path)
            result[pnum] = out_path
        return result
    except Exception:  # pragma: no cover
        return {}


def _parse_pages_param(raw: str | None) -> List[int]:
    if not raw:
        return []
    pages: set[int] = set()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for part in parts:
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                s, e = int(start), int(end)
                if s <= e:
                    for n in range(s, e + 1):
                        pages.add(n)
            except ValueError:
                continue
        else:
            try:
                pages.add(int(part))
            except ValueError:
                continue
    return sorted(pages)


def _run_textract_on_image(client: Any, image_path: Path) -> Dict[str, Any]:
    data = image_path.read_bytes()
    return client.analyze_document(Document={"Bytes": data}, FeatureTypes=["FORMS", "TABLES"])


def _textract_client():
    region = current_app.config.get("AWS_REGION") or os.getenv("AWS_REGION") or "eu-central-1"
    connect_timeout = float(current_app.config.get("TEXTRACT_CONNECT_TIMEOUT", 5))
    read_timeout = float(current_app.config.get("TEXTRACT_READ_TIMEOUT", 15))
    max_attempts = int(current_app.config.get("TEXTRACT_MAX_ATTEMPTS", 3))
    cfg = Config(
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        retries={"max_attempts": max_attempts, "mode": "standard"},
    )
    return boto3.client("textract", region_name=region, config=cfg)


def _cost_guard(max_requests: int, usage_path: Path) -> tuple[bool, int]:
    if max_requests <= 0:
        return True, 0
    today = datetime.date.today().isoformat()
    usage_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"date": today, "count": 0}
    if usage_path.exists():
        try:
            data = json.loads(usage_path.read_text(encoding="utf-8"))
        except Exception:
            data = {"date": today, "count": 0}
    if data.get("date") != today:
        data = {"date": today, "count": 0}
    if int(data.get("count", 0)) >= max_requests:
        return False, int(data.get("count", 0))
    data["count"] = int(data.get("count", 0)) + 1
    usage_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True, int(data["count"])


@textract_bp.post("/textract")
def textract_run() -> tuple[Any, int]:
    """Endpoint Textract: upload → AWS Textract → postprocessing → JSON response.

    PDF: opcjonalny parametr `pages` (np. "2-4,6,8") pozwala wskazać, które strony zrasteryzować
    i wysłać do Textracta (każda strona osobno). Jeśli brak `pages`, bierzemy pierwszą stronę.
    """

    req_id = str(uuid.uuid4())
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "brak pliku 'file'", "request_id": req_id}), 400

    upload_dir = Path(current_app.config.get("UPLOAD_FOLDER", "uploads")).resolve() / "textract"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{req_id}_{file.filename}"
    file.save(dest)

    usage_path = Path(current_app.config.get("TEXTRACT_USAGE_FILE", "reports/textract/usage.json")).resolve()
    daily_limit = int(current_app.config.get("TEXTRACT_DAILY_LIMIT", 0))
    allowed, usage_count = _cost_guard(daily_limit, usage_path)
    if not allowed:
        msg = f"limit wywołań Textract na dziś ({daily_limit}) został przekroczony"
        return jsonify({"error": msg, "request_id": req_id, "warnings": [msg]}), 429

    client = _textract_client()
    reports_dir = Path("reports/textract").resolve()
    raw_dir = reports_dir / "raw"
    post_dir = reports_dir / "post"
    overlay_dir = post_dir / "overlays"
    raw_dir.mkdir(parents=True, exist_ok=True)
    post_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)

    warnings_global: List[str] = []
    pages_param = request.form.get("pages") or request.args.get("pages")
    pages_selected = _parse_pages_param(pages_param)

    max_pages = int(current_app.config.get("TEXTRACT_MAX_PDF_PAGES", 8))
    max_raster_dpi = int(current_app.config.get("TEXTRACT_MAX_RASTER_DPI", 300))
    default_raster_dpi = int(current_app.config.get("TEXTRACT_DEFAULT_RASTER_DPI", 200))
    dpi_param = request.form.get("dpi") or request.args.get("dpi")
    raster_dpi = default_raster_dpi
    if dpi_param:
        try:
            raster_dpi = int(dpi_param)
        except ValueError:
            warnings_global.append("parametr dpi nie jest liczbą – używam domyślnego")
    if raster_dpi > max_raster_dpi:
        warnings_global.append(f"dpi obcięte do {max_raster_dpi}")
        raster_dpi = max_raster_dpi
    if raster_dpi < 72:
        warnings_global.append("dpi poniżej 72 nieobsługiwane – używam 72")
        raster_dpi = 72

    pages_out: List[Dict[str, Any]] = []

    def process_single_image(image_path: Path, page_label: int | str) -> Dict[str, Any]:
        page_warnings: List[str] = []
        try:
            response = _run_textract_on_image(client, image_path)
        except botocore.exceptions.BotoCoreError as exc:  # pragma: no cover - sieć/AWS
            current_app.logger.exception("[textract] błąd boto %s", exc)
            return {"page": page_label, "error": "Textract niedostępny"}
        except Exception:  # pragma: no cover - inne
            current_app.logger.exception("[textract] błąd wywołania Textract")
            return {"page": page_label, "error": "błąd Textract"}

        raw_path = raw_dir / f"{req_id}_{dest.stem}_p{page_label}.json"
        raw_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")

        try:
            im = Image.open(image_path)
            w, h = im.size
        except Exception:
            w = h = 0
            page_warnings.append("nie udało się otworzyć obrazu do postprocessingu")

        blocks = response.get("Blocks", [])
        tokens = _filter_tokens(blocks, w, h, min_conf=40.0) if w and h else []
        tokens = _merge_vertical_fragments(tokens)  # P4: merge vertical chars
        tokens = _extend_truncated_designators(tokens)  # P25c: C41 → C411
        tokens = _fix_semicon_fragments(tokens)  # P25b: 2S+C1740 → 2SC1740
        tokens = _fix_ic_ocr_confusion(tokens)  # P25e: IC40B → IC408

        # P4+: Rescue unread vertical text from uncovered strips
        if tokens and w and h:
            try:
                rescued = _rescue_vertical_text(image_path, tokens, client, w, h)
                if rescued:
                    tokens.extend(rescued)
                    page_warnings.append(f"vertical_rescue: +{len(rescued)} tokenów")
            except Exception:  # pragma: no cover
                current_app.logger.debug("[textract] vertical rescue failed", exc_info=True)

        # P9e: General substring deduplication (catches rescue dupes too)
        tokens = _dedup_substring_tokens(tokens)

        pairs = _pair_components_to_values(tokens) if tokens else []
        tokens, pairs = _fix_truncated_ic(tokens, pairs)  # P3: C408 → IC408

        post_path = post_dir / f"{req_id}_{dest.stem}_p{page_label}_post.json"
        post_payload = {
            "request_id": req_id,
            "file": dest.name,
            "page": page_label,
            "image": str(image_path),
            "tokens": tokens,
            "pairs": pairs,
        }
        post_path.write_text(json.dumps(post_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        overlay_path = overlay_dir / f"{req_id}_{dest.stem}_p{page_label}_post.png"
        if tokens and w and h:
            try:
                _draw_overlay(image_path, tokens, pairs, overlay_path)
            except Exception:  # pragma: no cover
                page_warnings.append("nie udało się wygenerować overlay")
        else:
            page_warnings.append("brak tokenów lub rozmiaru obrazu – bez overlay")

        return {
            "page": page_label,
            "raw_json": str(raw_path),
            "post_json": str(post_path),
            "overlay": str(overlay_path) if overlay_path.exists() else None,
            "tokens": tokens,
            "pairs": pairs,
            "warnings": page_warnings,
        }

    if dest.suffix.lower() == ".pdf":
        if fitz is None:
            warnings_global.append("brak PyMuPDF (fitz) – PDF nie został zrasteryzowany")
        else:
            try:
                doc = fitz.open(dest)
                total_pages = len(doc)
                if not pages_selected:
                    pages_selected = [1]
                pages_selected = [p for p in pages_selected if 1 <= p <= total_pages]
                if not pages_selected:
                    pages_selected = [1]
                if len(pages_selected) > max_pages:
                    warnings_global.append(
                        (
                            f"przycięto liczbę stron do {max_pages} – dla pełnego pliku "
                            f"(ma {total_pages} stron) potrzebny tryb async Textract"
                        )
                    )
                elif total_pages > max_pages and not pages_param:
                    warnings_global.append(
                        (
                            f"plik ma {total_pages} stron, ale synchronicznie przetwarzamy tylko {max_pages} "
                            f"– pełen zakres wymaga trybu async Textract"
                        )
                    )
                    pages_selected = pages_selected[:max_pages]
                rasters = _rasterize_pdf_pages(dest, req_id, pages_selected, dpi=raster_dpi)
                for p in pages_selected:
                    img_path = rasters.get(p)
                    if not img_path:
                        warnings_global.append(f"strona {p}: nie udało się zrasteryzować")
                        continue
                    pages_out.append(process_single_image(img_path, p))
            except Exception:
                warnings_global.append("błąd otwierania PDF – brak przetwarzania")
    else:
        pages_out.append(process_single_image(dest, 1))

    current_app.logger.info("[textract] przetworzono %s (req_id=%s), pages=%s", dest, req_id, len(pages_out))

    # Dla kompatybilności: tokens/pairs pierwszej strony jeśli są
    first_tokens = pages_out[0].get("tokens") if pages_out else []
    first_pairs = pages_out[0].get("pairs") if pages_out else []

    return (
        jsonify(
            {
                "request_id": req_id,
                "status": "ok",
                "pages": pages_out,
                "tokens": first_tokens,
                "pairs": first_pairs,
                "warnings": warnings_global,
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# Helper for applying corrections


def _apply_corrections_to_post(req_id: str, corrections: list[dict]) -> Optional[Dict[str, Any]]:
    """Given a request ID and a list of correction dicts, try to update the
    existing post-json file and return the new pairs/tokens payload.

    Corrections are expected to have keys ``component`` and ``value`` (both
    strings).  We overwrite any matching pair by component name and also
    update tokens if the component designator itself changed.  This is
    intentionally simple: we only touch the pairs list and, if possible,
    adjust a token text in place.

    Returns the new post_payload (same structure as produced by
    ``textract_run``) or ``None`` if no post file was found.
    """
    post_dir = Path("reports/textract").resolve() / "post"
    # search for single page file matching req_id (could be multi);
    # if multiple, just update all.
    updated = None
    for post_path in post_dir.glob(f"{req_id}_*_post.json"):
        try:
            data = json.loads(post_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        pairs = data.get("pairs", []) or []
        tokens = data.get("tokens", []) or []
        # apply each correction
        for corr in corrections:
            comp = corr.get("component", "").strip()
            val = corr.get("value", "").strip()
            if not comp and not val:
                continue
            # find existing pair by component
            found = False
            for p in pairs:
                if p.get("component") == comp:
                    if val:
                        p["value"] = val
                    found = True
                    break
            if not found and comp and val:
                pairs.append({"component": comp, "value": val})
            # also update token text if a component was changed
            for t in tokens:
                if t.get("text") == comp:
                    t["text"] = comp
        data["pairs"] = pairs
        data["tokens"] = tokens

        # rewrite the post file with the updated contents
        try:
            post_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            current_app.logger.warning("Failed to rewrite post file %s", post_path)

        # attempt to regenerate overlay if we know the source image
        img_str = data.get("image")
        if img_str:
            try:
                img_path = Path(img_str)
                overlay_path = post_path.parent / "overlays" / post_path.name.replace("_post.json", "_post.png")
                _draw_overlay(img_path, tokens, pairs, overlay_path)
                data["overlay"] = str(overlay_path)
            except Exception:
                current_app.logger.warning("Overlay regeneration failed for %s", post_path)

        # optional netlist regeneration: look for a segmentation file containing req_id
        try:
            from talk_electronic.routes.segment import (
                _processed_folder,
                _store_netlist_result,
                line_detection_result_from_dict,
            )
            from talk_electronic.services.netlist import generate_netlist
        except ImportError:
            _processed_folder = None

        if _processed_folder:
            seg_dir = _processed_folder() / "segments"
            for seg_file in seg_dir.glob(f"*{req_id}*.json"):
                try:
                    seg_data = json.loads(seg_file.read_text(encoding="utf-8"))
                    det = line_detection_result_from_dict(seg_data)
                    net = generate_netlist(det)
                    net_entry = _store_netlist_result(net)
                    data.setdefault("netlist", {}).update(net_entry)
                except Exception as exc:
                    # log full exception for debugging
                    current_app.logger.exception("Netlist regeneration failed from %s: %s", seg_file, exc)

        updated = data
    return updated


@textract_bp.post("/textract/corrections")
def textract_save_corrections():
    """Save user edits from OCR panel.

    The frontend will POST JSON with at least ``request_id`` and
    ``corrections`` (array of token objects). We store the data for later
    analysis and additionally try to apply the corrections to any
    postprocessing JSON that already exists for the same request id.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "expected JSON body"}), 400

    req_id = payload.get("request_id", "unknown")
    corr_dir = Path("reports/textract/corrections").resolve()
    corr_dir.mkdir(parents=True, exist_ok=True)
    out_path = corr_dir / f"{req_id}_corrections.json"
    try:
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # pragma: no cover - unlikely
        current_app.logger.exception("Unable to save corrections %s", exc)
        return jsonify({"error": "failed to save"}), 500

    # attempt to merge into any existing post JSON
    merged = None
    try:
        merged = _apply_corrections_to_post(req_id, payload.get("corrections", []))
    except Exception:  # pragma: no cover
        current_app.logger.exception("Error applying corrections to post files")
    resp = {"status": "ok", "path": str(out_path)}
    if merged is not None:
        resp["merged"] = merged
    return jsonify(resp), 200
