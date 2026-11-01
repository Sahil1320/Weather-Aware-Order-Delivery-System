"""Unit tests for the Weather-Aware Apology Generator module."""

import pytest
from apology_generator import generate_apology, _extract_first_name


class TestApologyGenerator:
    """Test suite for generate_apology function."""

    def test_extract_first_name_full_name(self):
        """Should extract the first token as the first name."""
        assert _extract_first_name("Alice Smith") == "Alice"
        assert _extract_first_name("Bob Jones") == "Bob"
        assert _extract_first_name("Charlie Green") == "Charlie"

    def test_extract_first_name_single_name(self):
        """Should handle single name gracefully."""
        assert _extract_first_name("Alice") == "Alice"

    def test_extract_first_name_empty_or_whitespace(self):
        """Should fall back to polite generic greeting for empty names."""
        assert _extract_first_name("") == "Valued Customer"
        assert _extract_first_name("   ") == "Valued Customer"
        assert _extract_first_name(None) == "Valued Customer"

    def test_rain_apology_default_description(self):
        """Should generate empathetic rain message with default heavy rain text."""
        msg = generate_apology("Alice Smith", "New York", "Rain")
        assert "Hi Alice" in msg
        assert "New York" in msg
        assert "delayed" in msg.lower()
        assert "rain" in msg.lower()
        assert "patience" in msg.lower()

    def test_rain_apology_custom_description(self):
        """Should incorporate custom rain description into the apology message."""
        msg = generate_apology("Alice Smith", "New York", "Rain", description="torrential downpour and rain")
        assert "Hi Alice" in msg
        assert "New York" in msg
        assert "torrential downpour and rain" in msg

    def test_snow_apology_default(self):
        """Should generate empathetic snow message with icy roads warning."""
        msg = generate_apology("Bob Jones", "Mumbai", "Snow")
        assert "Hi Bob" in msg
        assert "Mumbai" in msg
        assert "delayed" in msg.lower()
        assert "snow" in msg.lower() or "icy" in msg.lower()
        assert "stay warm" in msg.lower()

    def test_snow_apology_custom_description(self):
        """Should incorporate custom snow description into the message."""
        msg = generate_apology("Charlie Green", "London", "Snow", description="heavy blizzard")
        assert "Hi Charlie" in msg
        assert "London" in msg
        assert "heavy blizzard" in msg

    def test_extreme_apology_default(self):
        """Should generate apology prioritizing safety for extreme weather."""
        msg = generate_apology("Alice Smith", "New York", "Extreme")
        assert "Hi Alice" in msg
        assert "New York" in msg
        assert "severe weather" in msg.lower()
        assert "safety is our top priority" in msg.lower()

    def test_extreme_apology_custom_description(self):
        """Should include specific severe weather alert description."""
        msg = generate_apology("Alice Smith", "New York", "Extreme", description="tornado warning")
        assert "Hi Alice" in msg
        assert "tornado warning" in msg

    def test_case_insensitivity(self):
        """Should recognize lowercase or uppercase weather conditions."""
        msg_lower = generate_apology("Alice", "Paris", "rain")
        assert "delayed due to heavy rain" in msg_lower

        msg_upper = generate_apology("Bob", "Tokyo", "SNOW")
        assert "delayed due to" in msg_upper
        assert "icy roads" in msg_upper

    def test_fallback_weather_condition(self):
        """Should provide sensible fallback for unusual weather condition."""
        msg = generate_apology("Charlie", "London", "Squall", description="sudden high winds")
        assert "Hi Charlie" in msg
        assert "London" in msg
        assert "sudden high winds" in msg
        assert "patience" in msg.lower()

