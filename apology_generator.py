"""Weather-Aware Apology Generator.

Provides human-like, empathetic, and personalized apology messages
for orders delayed by severe or inclement weather conditions.
"""

from typing import Optional


def _extract_first_name(customer_name: str) -> str:
    """Extract first name from full customer name for a friendly tone."""
    if not customer_name or not customer_name.strip():
        return "Valued Customer"
    return customer_name.strip().split()[0]


def generate_apology(
    customer: str,
    city: str,
    weather: str,
    description: Optional[str] = None,
) -> str:
    """Generate a personalized, weather-aware apology message for delayed orders.

    Args:
        customer: Full name or greeting name of customer (e.g., 'Alice Smith').
        city: Destination city name (e.g., 'New York').
        weather: Weather condition category ('Rain', 'Snow', 'Extreme', etc.).
        description: Detailed weather description (e.g., 'heavy intensity rain').

    Returns:
        A personalized apology string.
    """
    first_name = _extract_first_name(customer)
    city_name = (city or "your destination").strip()
    weather_key = (weather or "").strip().capitalize()
    
    # Clean up description or fall back to sensible defaults
    clean_desc = (description or "").strip().lower()

    if weather_key == "Rain":
        cause = clean_desc if clean_desc and "rain" in clean_desc else "heavy rain"
        return (
            f"Hi {first_name}, your order to {city_name} is delayed due to {cause}. "
            "We appreciate your patience while our delivery team navigates the roads safely!"
        )

    if weather_key == "Snow":
        cause = clean_desc if clean_desc and ("snow" in clean_desc or "blizzard" in clean_desc or "ice" in clean_desc) else "snowy road conditions"
        return (
            f"Hi {first_name}, your order to {city_name} is delayed due to {cause}. "
            "Our drivers are taking extra precautions on icy roads. Thank you for your patience and stay warm!"
        )

    if weather_key == "Extreme":
        cause = clean_desc if clean_desc else "severe weather alerts"
        return (
            f"Hi {first_name}, your order to {city_name} is delayed due to severe weather ({cause}). "
            "Courier safety is our top priority, and deliveries will resume as soon as conditions clear. "
            "Thank you for your understanding!"
        )

    # General fallback for any unexpected delay category (e.g., Thunderstorm/Squall)
    cause = clean_desc if clean_desc else f"inclement weather ({weather})"
    return (
        f"Hi {first_name}, your order to {city_name} is delayed due to {cause}. "
        "We are actively monitoring conditions to deliver your package as soon as possible. "
        "We appreciate your patience!"
    )

