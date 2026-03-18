"""Helpers for exporting netlists to SPICE-compatible text files."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from .component_values import parse_component_value
from .netlist import NetlistResult

SPICE_PREFIX_MAP: Mapping[str, str] = {
    "resistor": "R",
    "capacitor": "C",
    "inductor": "L",
    "diode": "D",
    "transistor": "Q",
    "op_amp": "X",
    "connector": "X",
    "power_rail": "V",
    "ground": "G",
    "ic_pin": "X",
    "net_label": "X",
    "measurement_point": "X",
    "misc_symbol": "X",
}

GROUND_ALIASES = {"0", "gnd", "ground"}


@dataclass(frozen=True)
class ComponentInstance:
    """Represents a component ready to be rendered in SPICE syntax."""

    kind: str
    nodes: Sequence[str]
    value: str | None = None
    reference: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def get_spice_value(self) -> str:
        """Get SPICE-compatible value string."""
        if not self.value:
            return "1"

        # Try to parse and normalize the value
        parsed = parse_component_value(self.value, self.kind)
        if parsed:
            return parsed.spice_value

        # Fallback to original value if parsing fails
        return str(self.value)

    def normalized_nodes(self, *, valid_nodes: set[str], valid_nets: set[str], ground_alias: str) -> list[str]:
        normalized: list[str] = []
        for node in self.nodes:
            candidate = node.strip()
            lower = candidate.lower()
            if lower in GROUND_ALIASES:
                normalized.append(ground_alias)
                continue
            if candidate in valid_nodes or candidate in valid_nets:
                normalized.append(candidate)
                continue
            raise ValueError(f"Node '{node}' is not present in the netlist result")
        return normalized


def _resolve_prefix(kind: str) -> str:
    return SPICE_PREFIX_MAP.get(kind, "X")


def _format_component_line(
    reference: str,
    nodes: Sequence[str],
    value: str | None,
    parameters: Mapping[str, Any],
) -> str:
    base = [reference, *nodes]
    if value:
        base.append(value)
    extras: list[str] = []
    for key, val in parameters.items():
        extras.append(f"{key}={val}")
    base.extend(extras)
    return " ".join(base)


def assign_references(components: Iterable[ComponentInstance]) -> list[tuple[str, ComponentInstance]]:
    counters: Counter[str] = Counter()
    resolved: list[tuple[str, ComponentInstance]] = []
    for component in components:
        if component.reference:
            reference = component.reference
        else:
            prefix = _resolve_prefix(component.kind)
            counters[prefix] += 1
            reference = f"{prefix}{counters[prefix]}"
        resolved.append((reference, component))
    return resolved


@dataclass(frozen=True)
class SpiceValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_spice_components(
    netlist: NetlistResult,
    components: Sequence[ComponentInstance],
    *,
    ground_alias: str = "0",
) -> SpiceValidationResult:
    """Validate component assignments against a netlist before SPICE export."""

    node_labels = {node.label for node in netlist.nodes}
    net_labels = set(netlist.metadata.get("net_labels", {}).values())
    known_nets = node_labels | net_labels | {ground_alias}

    errors: list[str] = []
    warnings: list[str] = []

    if not components:
        warnings.append("Brak zdefiniowanych komponentów – eksport zawiera tylko połączenia.")

    explicit_refs: set[str] = set()
    for idx, component in enumerate(components):
        if len(component.nodes) < 2:
            errors.append(f"Komponent #{idx + 1} ({component.kind}) ma mniej niż dwa węzły")

        if component.reference:
            ref = component.reference
            if ref in explicit_refs:
                warnings.append(f"Powtórzona referencja {ref} – numeracja może być niespójna")
            explicit_refs.add(ref)

        for node in component.nodes:
            candidate = node.strip()
            if candidate.lower() in {alias.lower() for alias in GROUND_ALIASES}:
                continue
            if candidate not in known_nets:
                errors.append(f"Nieznany węzeł '{candidate}' w komponencie {component.reference or component.kind}")

    return SpiceValidationResult(errors=errors, warnings=warnings)


def generate_spice_netlist(
    netlist: NetlistResult,
    components: Sequence[ComponentInstance],
    *,
    title: str = "Talk_electronic generated circuit",
    ground_alias: str = "0",
    validate: bool = True,
) -> str:
    """Render a SPICE deck from the logical netlist and component assignments."""

    validation = validate_spice_components(netlist, components, ground_alias=ground_alias) if validate else None
    if validation and validation.errors:
        raise ValueError("; ".join(validation.errors))

    node_labels = {node.label for node in netlist.nodes}
    net_labels = set(netlist.metadata.get("net_labels", {}).values())
    lines: list[str] = [f"* {title}"]

    resolved_components = assign_references(components)

    if not resolved_components:
        lines.append("* No components detected; wiring only")
    else:
        for reference, component in resolved_components:
            normalized_nodes = component.normalized_nodes(
                valid_nodes=node_labels,
                valid_nets=net_labels,
                ground_alias=ground_alias,
            )
            value = component.get_spice_value()
            line = _format_component_line(reference, normalized_nodes, value, component.parameters)
            lines.append(line)

    if validation and validation.warnings:
        for warning in validation.warnings:
            lines.append(f"* WARN: {warning}")

    lines.append(".end")
    return "\n".join(lines) + "\n"


def parse_component_instances(raw_components: Any) -> list[ComponentInstance]:
    """Convert a JSON payload into ``ComponentInstance`` objects."""

    if not raw_components:
        return []
    if not isinstance(raw_components, (list, tuple)):
        raise ValueError("components must be a list of objects")

    parsed: list[ComponentInstance] = []
    for entry in raw_components:
        if not isinstance(entry, MutableMapping):
            raise ValueError("each component must be an object")
        kind = entry.get("kind") or entry.get("type")
        if not isinstance(kind, str) or not kind:
            raise ValueError("component.kind is required")
        nodes = entry.get("nodes") or entry.get("pins")
        if not isinstance(nodes, (list, tuple)) or len(nodes) < 2:
            raise ValueError("component.nodes must contain at least two entries")
        nodes_str = [str(node) for node in nodes]
        value = entry.get("value")
        if value is not None:
            value = str(value)
        reference = entry.get("reference")
        if reference is not None:
            reference = str(reference)
        parameters = entry.get("parameters")
        if isinstance(parameters, MutableMapping):
            safe_parameters = {str(key): parameters[key] for key in parameters}
        else:
            safe_parameters = {}
        parsed.append(
            ComponentInstance(
                kind=str(kind),
                nodes=nodes_str,
                value=value,
                reference=reference,
                parameters=safe_parameters,
            )
        )
    return parsed
