"""Component-to-value pairing algorithms for OCR tokens.

Contains:
- Token categorization (component, value, net_label, other)
- Semantic affinity rules for component-value matching
- Geometric pairing based on proximity and position
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# Semiconductor model number pattern (transistors, diodes)
# Used for semantic-affinity to prevent wrong passive <-> semiconductor pairings
SEMI_MODEL_RE = re.compile(
    r"^(?:2S[ABCDKJ]|2N|1S[SN]?|1N|B[CDFRUY]|TIP|IRF|MPS[AU]?|MJE?|MA)\d{2,5}[A-Z]{0,2}$",
    re.IGNORECASE,
)


def looks_like_value(text: str) -> bool:
    """Check if text looks like an electronic component value.
    
    Recognizes:
    - Semiconductor part numbers (2SC1740, BC109B, 1N4148, MA150)
    - IC model numbers (TDA2030, LM741, NE555)
    - Values with units (K, M, R, Ω, etc.)
    - Values with decimal separators (., ,, /)
    
    Args:
        text: Token text to check
        
    Returns:
        True if text looks like a component value
    """
    t = text.strip()
    
    # Semiconductor part numbers (JIS, European BJT, Diodes)
    if re.match(r"^(2S[ABCD]|1S[SN]|B[CDFRU]|MA)\d{2,5}[A-Z]{0,2}$", t, re.IGNORECASE):
        return True
    
    # IC/op-amp model numbers
    if re.match(r"^(UL|TDA|TL|LM|NE|UA|UPC|MC|TA|AN|AD|OP|MAX|LF|CA)\d{2,5}[A-Z]{0,2}$", t, re.IGNORECASE):
        return True
    
    # Guard: interleaved letters+digits (like "FE0F") are IC pin labels, not values
    if re.match(r"^[A-Za-z]{2}", t) and t.isalnum():
        if not re.match(r"^[A-Za-z]+\d+$", t):
            return False
    
    # Values with units
    if any(unit in t for unit in ["K", "M", "R", "Ω", "OHM", "U", "N", "P", "F", "V"]):
        return True
    
    # Values with decimal separators
    if any(sep in t for sep in [".", ",", "/"]):
        return True
    
    # Multi-digit numbers are likely values
    digits = [ch for ch in t if ch.isdigit()]
    return len(digits) >= 2


def categorize(text: str) -> str:
    """Categorize OCR token into component, value, net_label, or other.
    
    Args:
        text: Token text to categorize
        
    Returns:
        Category string: "component", "value", "net_label", or "other"
    """
    t = text.strip()
    up = t.upper()
    
    if not t:
        return "other"
    
    # IC designators
    if up.startswith("IC") and up[2:].isdigit():
        return "component"
    
    # Potentiometer designators (RpL, QpL, etc.)
    if len(t) == 3 and t[0] in {"R", "C", "L", "Q", "D", "M", "T"} and t[1] == "p" and t[2] in {"L", "P"}:
        return "component"
    
    # Standard component designators (R, C, L, Q, D, M, T, S + digits)
    if up[0] in {"R", "C", "L", "Q", "D", "M", "T", "S"} and re.match(r"^\d+[A-Z]?$", up[1:]):
        return "component"
    
    # Safety fuse designators (SF402, SF403)
    if re.match(r"^SF\d{2,4}$", up):
        return "component"
    
    # Power rail labels (+5V, +12V, -12V)
    if re.match(r"^[+\-]?\d+V$", up):
        return "net_label"
    
    # Check for value patterns
    if any(ch.isdigit() for ch in t):
        if looks_like_value(t):
            return "value"
    
    # Short alphanumeric tokens are likely net labels
    if up.replace("_", "").replace("-", "").isalnum() and len(up) <= 6:
        return "net_label"
    
    # Audio channel labels (L ch, R ch)
    if re.match(r"^[LR]\s+ch$", t, re.IGNORECASE):
        return "net_label"
    
    # Net labels with special chars (+, /, -)
    stripped = up.replace("+", "").replace("/", "").replace("-", "").replace("_", "")
    if stripped.isalnum() and 2 <= len(up) <= 6:
        return "net_label"
    
    return "other"


def pair_components_to_values(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Match component designators to their values based on proximity and semantics.
    
    Uses geometric analysis (vertical/horizontal bands) and semantic affinity
    (e.g., transistors prefer semiconductor models over passive values).
    
    Args:
        tokens: List of OCR tokens with "text", "bbox", "center", "category"
        
    Returns:
        List of pairing dicts with component, value, bboxes, centers
    """
    comps = [t for t in tokens if t["category"] == "component"]
    vals = [t for t in tokens if t["category"] == "value"]
    pairs: List[Dict[str, Any]] = []

    def _combine_vertical_values(
        main_val: Dict[str, Any],
        comp: Dict[str, Any],
        exclude_ids: set[int] | None = None,
    ) -> Tuple[str, Tuple[float, float, float, float]]:
        """Combine vertically stacked value tokens (e.g., 47 + 16 → 47/16)."""
        cx, cy = comp["center"]
        comp_w = comp["bbox"][2]
        comp_h = comp["bbox"][3]
        max_dim = max(comp_w, comp_h)
        parts = [(main_val["text"], main_val["bbox"])]

        # Search for adjacent values in column below component
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
            
            # For transistors/diodes, skip pure-numeric passive values
            if comp_text_up[:1] in {"Q", "D"} and re.match(r"^[\d.,/]+$", val_text):
                continue
            
            # Skip IC pin numbers and component designators
            if val_text.isdigit() and len(val_text) <= 2:
                if comp_text_up.startswith("C") and main_val["text"].isdigit():
                    vx_c, vy_c = val["center"]
                    dy_from_main = vy_c - main_val["center"][1]
                    dx_from_main = abs(vx_c - main_val["center"][0])
                    if dy_from_main <= 0 or dy_from_main > main_h * 3.0:
                        continue
                    if dx_from_main > max(main_w, comp_w) * 1.5:
                        continue
                else:
                    continue
            
            val_up = val_text.upper()
            if re.match(r"^(IC|[RCLQ])\d{2,4}$", val_up):
                continue
                
            vx, vy = val["center"]
            dx = abs(vx - cx)
            dy = vy - cy
            
            if dy < 0:
                continue
            if dy > max_span:
                continue
            if dx > horiz_tol:
                continue
            candidates.append((val["text"], val["bbox"], vy))

        # Sort by Y, add only if continuous column
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

        # Heuristic: fix "01/47" → "47/10" for capacitors
        if comp_text_up.startswith("C"):
            norm_texts: list[str] = []
            for t in texts:
                if re.match(r"^0?1/\d{2}$", t):
                    m = re.match(r"^0?1/(\d{2})$", t)
                    if m:
                        norm_texts.append(f"{m.group(1)}/10")
                        continue
                norm_texts.append(t)
            texts = norm_texts

        # For capacitors with two digit parts, join with '/'
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
            vt = val.get("text", "")
            if comp_text_up.startswith("IC") and vt.isdigit() and len(vt) <= 2:
                continue
            if comp_text_up.startswith("IC") and re.match(r"^\d+\.?\d*[KkMΩRPNFGpnfuUV]$", vt):
                continue
                
            vx, vy = val["center"]
            dx = abs(vx - cx)
            dy = vy - cy
            
            if (dx * dx + dy * dy) ** 0.5 > max_dist:
                continue
            
            # Vertical band down
            if vy >= cy and dx <= comp_w * 0.5 and dy <= max_dim * 2.0:
                vertical_band_down.append((dy, val))
            # Right band
            if vx >= cx and abs(dy) <= comp_h * 0.5 and dx <= max_dim * 3.0:
                right_band.append((dx, val))

        chosen = None
        if vertical_band_down:
            vertical_band_down.sort(key=lambda t: t[0])
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

        # Check for richer alternative for plain digit values
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
                    if SEMI_MODEL_RE.match(vt2) and comp_text_up[:1] in {"C", "R", "L", "T"}:
                        continue
                    vx2, vy2 = val["center"]
                    if vy2 < cy - comp_h * 0.5:
                        continue
                    d2 = ((cx - vx2) ** 2 + (cy - vy2) ** 2) ** 0.5
                    if d2 <= max_dist and d2 <= chosen_dist * 2.5 and d2 < alt_best_dist:
                        alt_best_dist = d2
                        alt_best = val
                if alt_best is not None:
                    chosen = alt_best

        # General nearest fallback
        if not chosen:
            general_nearby: list[tuple[float, Dict[str, Any]]] = []
            for val in candidate_vals:
                vt = val.get("text", "")
                if comp_text_up.startswith("IC") and vt.isdigit() and len(vt) <= 2:
                    continue
                if comp_text_up.startswith("IC") and re.match(r"^\d+\.?\d*[KkMΩRPNFGpnfuUV]$", vt):
                    continue
                vx, vy = val["center"]
                if vy < cy - comp_h * 0.5:
                    continue
                dist = ((cx - vx) ** 2 + (cy - vy) ** 2) ** 0.5
                if dist <= max_dist:
                    general_nearby.append((dist, val))
            if general_nearby:
                general_nearby.sort(key=lambda t: t[0])
                chosen = general_nearby[0][1]

        # Semantic affinity: transistors prefer semiconductor models
        if chosen:
            chosen_text = chosen.get("text", "")
            chosen_is_semi = bool(SEMI_MODEL_RE.match(chosen_text))
            prefix = comp_text_up[:1]
            chosen_dist = ((cx - chosen["center"][0]) ** 2 + (cy - chosen["center"][1]) ** 2) ** 0.5

            if prefix in {"Q", "D"} and not chosen_is_semi:
                _is_clearly_passive = bool(re.match(r"^[\d.,/]+$", chosen_text))
                semi_nearby: list[tuple[float, Dict[str, Any]]] = []
                for val in candidate_vals:
                    vt = val.get("text", "")
                    if SEMI_MODEL_RE.match(vt):
                        vx, vy = val["center"]
                        if vy < cy - comp_h * 0.5:
                            continue
                        dist = ((cx - vx) ** 2 + (cy - vy) ** 2) ** 0.5
                        if dist <= max_dist:
                            semi_nearby.append((dist, val))
                if semi_nearby:
                    semi_nearby.sort(key=lambda t: t[0])
                    semi_dist, semi_val = semi_nearby[0]
                    threshold = 1.5 if _is_clearly_passive else 0.75
                    if semi_dist < chosen_dist * threshold:
                        chosen = semi_val
                elif _is_clearly_passive:
                    chosen = None

            elif prefix in {"C", "R", "L", "T"} and chosen_is_semi:
                passive_nearby: list[tuple[float, Dict[str, Any]]] = []
                for val in candidate_vals:
                    vt = val.get("text", "")
                    if not SEMI_MODEL_RE.match(vt):
                        vx, vy = val["center"]
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

    # Exclusive pairing: closest component wins
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
    original_primary = list(primary_assignments)
    if losers:
        primary_assignments = [(c, v) for i, (c, v) in enumerate(primary_assignments) if i not in losers]

    # Retry for losers with next-nearest unassigned value
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
                if comp_text_up_l.startswith("IC") and re.match(r"^\d+\.?\d*[KkMΩRPNFGpnfuUV]$", vt_l):
                    continue
                vx, vy = val["center"]
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

    # --- Pass 2: combine with secondary values ---
    primary_val_ids = {id(val) for _, val in primary_assignments}

    for comp, primary_val in primary_assignments:
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
