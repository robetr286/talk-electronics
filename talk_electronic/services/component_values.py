"""Parse and normalize electronic component values with units."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Optional, Tuple


@dataclass(frozen=True)
class ComponentValue:
    """Represents a component value with unit information."""

    raw: str  # Original string from annotation (e.g., "100n", "0.1u")
    value_si: float  # Normalized to base SI unit (F, H, Ω)
    unit: str  # Base unit: "F" (farad), "H" (henry), "Ω" (ohm)
    display_value: str  # Human-readable with unit (e.g., "100nF", "0.1µF")
    spice_value: str  # SPICE-compatible format (e.g., "100n", "0.1u")


# Use high-precision decimal arithmetic when parsing user input to avoid
# floating point artifacts (e.g., 0.1e-6 becoming 9.999...e-8).
getcontext().prec = 28

# Threshold prefixes shared by capacitance/inductance units.
REACTIVE_PREFIXES: dict[str, Tuple[Decimal, str]] = {
    "": (Decimal("1"), ""),
    "p": (Decimal("1e-12"), "p"),
    "n": (Decimal("1e-9"), "n"),
    "u": (Decimal("1e-6"), "u"),
    "m": (Decimal("1e-3"), "m"),
}

# Pattern to parse value strings like "100n", "0.1u", "4.7K", "470"
VALUE_PATTERN = re.compile(r"^\s*([0-9]+\.?[0-9]*|\.[0-9]+)\s*([a-zA-ZµΩ]+)?\s*$", re.IGNORECASE)


def parse_component_value(
    value_str: str,
    component_type: str,
) -> Optional[ComponentValue]:
    """
    Parse a component value string into a ComponentValue object.

    Args:
        value_str: Value string from annotation (e.g., "100n", "4.7K")
        component_type: Type of component ("capacitor", "resistor", "inductor")

    Returns:
        ComponentValue object or None if parsing fails

    Examples:
        >>> parse_component_value("100n", "capacitor")
        ComponentValue(raw="100n", value_si=1e-07, unit="F", ...)

        >>> parse_component_value("4.7K", "resistor")
        ComponentValue(raw="4.7K", value_si=4700.0, unit="Ω", ...)
    """
    if not value_str or not isinstance(value_str, str):
        return None

    value_str = value_str.strip()
    if not value_str or value_str.lower() == "unknown":
        return None

    match = VALUE_PATTERN.match(value_str)
    if not match:
        return None

    number_str, unit_str = match.groups()

    try:
        number_decimal = Decimal(number_str)
    except (ValueError, TypeError):
        return None

    # Determine base unit based on component type
    if component_type == "capacitor":
        base_unit = "F"
        default_multiplier = Decimal("1e-6")  # Default to µF if no unit specified
        default_suffix = "u"
    elif component_type == "inductor":
        base_unit = "H"
        default_multiplier = Decimal("1e-6")
        default_suffix = "u"
    elif component_type == "resistor":
        base_unit = "Ω"
        default_multiplier = Decimal("1.0")
        default_suffix = ""
    else:
        return None

    multiplier, preferred_suffix = _resolve_multiplier(unit_str, component_type, default_multiplier, default_suffix)
    if multiplier is None:
        return None

    value_decimal = number_decimal * multiplier
    value_si = float(value_decimal)

    # Generate display and SPICE formats
    display_value = _format_display_value(value_si, base_unit)
    spice_value = _format_spice_value(value_decimal, base_unit, multiplier, preferred_suffix)

    return ComponentValue(
        raw=value_str,
        value_si=value_si,
        unit=base_unit,
        display_value=display_value,
        spice_value=spice_value,
    )


def _resolve_multiplier(
    unit_str: Optional[str],
    component_type: str,
    default_multiplier: Decimal,
    default_suffix: str,
) -> Tuple[Optional[Decimal], str]:
    """Return multiplier (as Decimal) and preferred SPICE suffix."""

    if not unit_str:
        return default_multiplier, default_suffix

    normalized = unit_str.strip().replace("µ", "u").replace("μ", "u")
    if not normalized:
        return default_multiplier, default_suffix

    if component_type in {"capacitor", "inductor"}:
        normalized_lower = normalized.lower()
        if normalized_lower.endswith("f") or normalized_lower.endswith("h"):
            normalized_lower = normalized_lower[:-1]
        prefix = normalized_lower
        info = REACTIVE_PREFIXES.get(prefix)
        if info:
            return info
        return None, ""

    # Resistor handling
    normalized_ascii = normalized.replace("Ω", "Ω")
    normalized_ascii = normalized_ascii.replace("Ω", "ohm").replace("ω", "ohm")
    raw_prefix = normalized_ascii.replace("ohm", "").strip()
    raw_prefix_lower = raw_prefix.lower()

    if raw_prefix == "M":
        return Decimal("1e6"), "Meg"
    if raw_prefix_lower in ("", "r"):
        return Decimal("1"), ""
    if raw_prefix_lower == "k":
        suffix = "K" if raw_prefix.isupper() else "k"
        return Decimal("1e3"), suffix
    if raw_prefix_lower == "m" and raw_prefix != "M":
        return Decimal("1e-3"), "m"
    if raw_prefix_lower == "g":
        return Decimal("1e9"), "G"
    if raw_prefix_lower in {"meg", "megohm"}:
        return Decimal("1e6"), "Meg"
    if raw_prefix_lower in {"ohm", "ohms"}:
        return Decimal("1"), ""
    if normalized_lower == "mohm":
        return Decimal("1e-3"), "m"
    if normalized_lower == "megohm":
        return Decimal("1e6"), "Meg"
    if normalized_lower == "ohms":
        return Decimal("1"), ""

    return None, ""


def _format_display_value(value_si: float, base_unit: str) -> str:
    """Format value for human-readable display."""
    if base_unit == "F":
        if value_si >= 1e-3:
            return f"{value_si*1e3:.6g}mF"
        elif value_si >= 1e-6:
            return f"{value_si*1e6:.6g}µF"
        elif value_si >= 1e-9:
            return f"{value_si*1e9:.6g}nF"
        else:
            return f"{value_si*1e12:.6g}pF"
    elif base_unit == "H":
        if value_si >= 1e-3:
            return f"{value_si*1e3:.6g}mH"
        elif value_si >= 1e-6:
            return f"{value_si*1e6:.6g}µH"
        elif value_si >= 1e-9:
            return f"{value_si*1e9:.6g}nH"
        else:
            return f"{value_si*1e12:.6g}pH"
    elif base_unit == "Ω":
        if value_si >= 1e9:
            return f"{value_si/1e9:.6g}GΩ"
        elif value_si >= 1e6:
            return f"{value_si/1e6:.6g}MΩ"
        elif value_si >= 1e3:
            return f"{value_si/1e3:.6g}kΩ"
        else:
            return f"{value_si:.6g}Ω"
    else:
        return f"{value_si:.6g}{base_unit}"


def _format_spice_value(
    value_decimal: Decimal,
    base_unit: str,
    preferred_multiplier: Decimal,
    preferred_suffix: str,
) -> str:
    """Format value for SPICE compatibility, preferring the user provided unit."""

    if preferred_multiplier is not None:
        scaled = value_decimal / preferred_multiplier
        return f"{_format_decimal(scaled)}{preferred_suffix}"

    value_si = float(value_decimal)
    if base_unit in {"F", "H"}:
        if value_si >= 1e-3:
            return f"{value_si*1e3:.6g}m"
        elif value_si >= 1e-6:
            return f"{value_si*1e6:.6g}u"
        elif value_si >= 1e-9:
            return f"{value_si*1e9:.6g}n"
        else:
            return f"{value_si*1e12:.6g}p"
    elif base_unit == "Ω":
        if value_si >= 1e9:
            return f"{value_si/1e9:.6g}G"
        elif value_si >= 1e6:
            return f"{value_si/1e6:.6g}Meg"
        elif value_si >= 1e3:
            return f"{value_si/1e3:.6g}K"
        else:
            return f"{value_si:.6g}"
    return f"{value_si:.6g}"


def _format_decimal(value: Decimal) -> str:
    """Convert Decimal to string without scientific notation or trailing zeros."""

    quantized = value.normalize()
    if quantized == quantized.to_integral():
        return format(quantized, "f")
    formatted = format(quantized, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted or "0"


def extract_metadata_value(
    metadata: dict,
    component_type: str,
) -> Optional[ComponentValue]:
    """
    Extract and parse component value from annotation metadata.

    Args:
        metadata: Dictionary containing component metadata (from region_comment)
        component_type: Type of component (e.g., "capacitor", "resistor")

    Returns:
        ComponentValue object or None if value not found/parseable

    Example metadata:
        {"designator": "C12", "type": "capacitor", "value": "100n", "polarity": "unknown"}
    """
    value_str = metadata.get("value")
    if not value_str:
        return None

    return parse_component_value(value_str, component_type)
