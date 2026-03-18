"""Tests for component value parsing and normalization."""

from __future__ import annotations

from talk_electronic.services.component_values import extract_metadata_value, parse_component_value


class TestParseComponentValue:
    """Test parsing of component values with units."""

    def test_capacitor_nanofarad(self):
        result = parse_component_value("100n", "capacitor")
        assert result is not None
        assert result.raw == "100n"
        assert result.value_si == 100e-9
        assert result.unit == "F"
        assert result.spice_value == "100n"
        assert "nF" in result.display_value

    def test_capacitor_microfarad(self):
        result = parse_component_value("470u", "capacitor")
        assert result is not None
        assert result.value_si == 470e-6
        assert result.spice_value == "470u"
        assert "µF" in result.display_value

    def test_capacitor_decimal_microfarad(self):
        result = parse_component_value("0.1u", "capacitor")
        assert result is not None
        assert result.value_si == 0.1e-6
        assert result.spice_value == "0.1u"

    def test_capacitor_picofarad(self):
        result = parse_component_value("22p", "capacitor")
        assert result is not None
        assert result.value_si == 22e-12
        assert result.spice_value == "22p"

    def test_resistor_ohms(self):
        result = parse_component_value("470", "resistor")
        assert result is not None
        assert result.value_si == 470.0
        assert result.unit == "Ω"

    def test_resistor_kilohms(self):
        result = parse_component_value("4.7K", "resistor")
        assert result is not None
        assert result.value_si == 4700.0
        assert result.spice_value == "4.7K"

    def test_resistor_megohms(self):
        result = parse_component_value("1M", "resistor")
        assert result is not None
        assert result.value_si == 1e6
        assert result.spice_value == "1Meg"  # SPICE uses 'Meg' for megaohms

    def test_inductor_microhenry(self):
        result = parse_component_value("10uH", "inductor")
        assert result is not None
        assert result.value_si == 10e-6
        assert result.unit == "H"
        assert result.spice_value == "10u"

    def test_inductor_millihenry(self):
        result = parse_component_value("1mH", "inductor")
        assert result is not None
        assert result.value_si == 1e-3
        assert result.spice_value == "1m"

    def test_invalid_value_returns_none(self):
        assert parse_component_value("invalid", "capacitor") is None
        assert parse_component_value("", "resistor") is None
        assert parse_component_value("unknown", "inductor") is None

    def test_no_unit_defaults_correctly(self):
        # Capacitor without unit should default to µF
        result = parse_component_value("100", "capacitor")
        assert result is not None
        assert result.value_si == 100e-6  # 100µF

        # Resistor without unit should default to Ω
        result = parse_component_value("100", "resistor")
        assert result is not None
        assert result.value_si == 100.0  # 100Ω

    def test_whitespace_handling(self):
        result = parse_component_value("  100n  ", "capacitor")
        assert result is not None
        assert result.value_si == 100e-9

    def test_case_insensitive_units(self):
        result1 = parse_component_value("100N", "capacitor")
        result2 = parse_component_value("100n", "capacitor")
        assert result1 is not None
        assert result2 is not None
        assert result1.value_si == result2.value_si

    def test_unicode_micro_symbol(self):
        result = parse_component_value("10µF", "capacitor")
        assert result is not None
        assert result.value_si == 10e-6


class TestExtractMetadataValue:
    """Test extraction of values from annotation metadata."""

    def test_extract_capacitor_value(self):
        metadata = {
            "designator": "C12",
            "type": "capacitor",
            "value": "100n",
            "polarity": "unknown",
        }
        result = extract_metadata_value(metadata, "capacitor")
        assert result is not None
        assert result.value_si == 100e-9

    def test_extract_resistor_value(self):
        metadata = {
            "designator": "R5",
            "type": "resistor",
            "value": "4.7K",
        }
        result = extract_metadata_value(metadata, "resistor")
        assert result is not None
        assert result.value_si == 4700.0

    def test_missing_value_returns_none(self):
        metadata = {
            "designator": "C1",
            "type": "capacitor",
        }
        result = extract_metadata_value(metadata, "capacitor")
        assert result is None

    def test_unknown_value_returns_none(self):
        metadata = {
            "designator": "L1",
            "type": "inductor",
            "value": "unknown",
        }
        result = extract_metadata_value(metadata, "inductor")
        assert result is None


class TestSpiceValueFormatting:
    """Test SPICE-compatible value formatting."""

    def test_capacitor_spice_format(self):
        result = parse_component_value("0.039µF", "capacitor")
        assert result is not None
        # Should convert to nanofarads for better readability
        assert result.spice_value == "39n" or result.spice_value.startswith("0.039u")

    def test_resistor_megohm_uses_meg(self):
        result = parse_component_value("2.2M", "resistor")
        assert result is not None
        assert "Meg" in result.spice_value  # SPICE standard for megaohms

    def test_small_capacitor_uses_pico(self):
        result = parse_component_value("100p", "capacitor")
        assert result is not None
        assert result.spice_value == "100p"


class TestDisplayValueFormatting:
    """Test human-readable display formatting."""

    def test_display_uses_unicode_micro(self):
        result = parse_component_value("100u", "capacitor")
        assert result is not None
        assert "µF" in result.display_value  # Unicode µ for display

    def test_display_uses_best_unit(self):
        # 0.1µF should display as 100nF
        result = parse_component_value("0.1u", "capacitor")
        assert result is not None
        assert "nF" in result.display_value or "µF" in result.display_value

    def test_resistor_display_kilohms(self):
        result = parse_component_value("4.7K", "resistor")
        assert result is not None
        assert "kΩ" in result.display_value or "K" in result.display_value
