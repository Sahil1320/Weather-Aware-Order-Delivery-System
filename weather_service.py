"""Weather Service module for parallel OpenWeatherMap API communication.

Utilizes aiohttp and asyncio.gather() to fetch weather data concurrently
with strict timeout handling, comprehensive error catching, and structured logging.
"""

from dataclasses import dataclass
import logging
from typing import Dict, List, Optional
import aiohttp
import asyncio

logger = logging.getLogger("weather_system")


@dataclass
class WeatherResult:
    """Represents the outcome of a weather query for a specific city."""
    city: str
    success: bool
    main: Optional[str] = None
    description: Optional[str] = None
    temp_celsius: Optional[float] = None
    error_message: Optional[str] = None
    status_code: Optional[int] = None


class WeatherService:
    """Asynchronous client for OpenWeatherMap Current Weather API."""

    BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_seconds: float = 10.0,
        base_url: Optional[str] = None,
    ) -> None:
        """Initialize the WeatherService.

        Args:
            api_key: OpenWeatherMap API key.
            timeout_seconds: Maximum duration for each API call before timing out.
            base_url: Optional override for testing or mocking.
        """
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.base_url = base_url or self.BASE_URL

    async def fetch_weather_for_city(
        self,
        session: aiohttp.ClientSession,
        city: str,
    ) -> WeatherResult:
        """Fetch current weather for a single city asynchronously.

        Handles network failures, timeouts, 404 (invalid cities), 401, 429, etc.
        without raising exceptions, ensuring caller resilience.

        Args:
            session: Active aiohttp ClientSession.
            city: City name to look up.

        Returns:
            WeatherResult object containing weather details or failure reason.
        """
        if not self.api_key:
            err = "OpenWeatherMap API key is missing or not configured."
            logger.error(f"[{city}] Configuration Error: {err}")
            return WeatherResult(
                city=city,
                success=False,
                error_message=err,
            )

        params = {
            "q": city,
            "appid": self.api_key,
            "units": "metric",
        }

        try:
            async with session.get(self.base_url, params=params, timeout=self.timeout) as response:
                status = response.status
                
                if status == 200:
                    data = await response.json()
                    weather_list = data.get("weather", [])
                    main_condition = weather_list[0].get("main") if weather_list else "Unknown"
                    desc = weather_list[0].get("description") if weather_list else ""
                    temp = data.get("main", {}).get("temp")
                    
                    logger.info(f"[{city}] Weather fetched successfully: {main_condition} ({desc}), {temp}°C")
                    return WeatherResult(
                        city=city,
                        success=True,
                        main=main_condition,
                        description=desc,
                        temp_celsius=temp,
                        status_code=200,
                    )

                if status == 404:
                    err_msg = f"City '{city}' not found (HTTP 404 - Invalid City)."
                    logger.error(f"[{city}] Not Found: {err_msg}")
                    return WeatherResult(
                        city=city,
                        success=False,
                        error_message=err_msg,
                        status_code=404,
                    )

                if status == 401:
                    err_msg = "Invalid OpenWeatherMap API key (HTTP 401 Unauthorized)."
                    logger.error(f"[{city}] Auth Error: {err_msg}")
                    return WeatherResult(
                        city=city,
                        success=False,
                        error_message=err_msg,
                        status_code=401,
                    )

                if status == 429:
                    err_msg = "OpenWeatherMap API rate limit exceeded (HTTP 429)."
                    logger.error(f"[{city}] Rate Limit: {err_msg}")
                    return WeatherResult(
                        city=city,
                        success=False,
                        error_message=err_msg,
                        status_code=429,
                    )

                # Any other unexpected HTTP status
                body = await response.text()
                err_msg = f"Weather API error (HTTP {status}): {body[:100]}"
                logger.error(f"[{city}] API Error: {err_msg}")
                return WeatherResult(
                    city=city,
                    success=False,
                    error_message=err_msg,
                    status_code=status,
                )

        except asyncio.TimeoutError:
            err_msg = f"Request timed out after {self.timeout.total}s while fetching weather for '{city}'."
            logger.error(f"[{city}] Timeout: {err_msg}")
            return WeatherResult(city=city, success=False, error_message=err_msg)

        except aiohttp.ClientConnectorError as exc:
            err_msg = f"Network connection error for '{city}': {exc}"
            logger.error(f"[{city}] Connection Error: {err_msg}")
            return WeatherResult(city=city, success=False, error_message=err_msg)

        except aiohttp.ClientError as exc:
            err_msg = f"aiohttp ClientError for '{city}': {exc}"
            logger.error(f"[{city}] Client Error: {err_msg}")
            return WeatherResult(city=city, success=False, error_message=err_msg)

        except Exception as exc:
            err_msg = f"Unexpected error while fetching weather for '{city}': {exc}"
            logger.error(f"[{city}] Unexpected Error: {err_msg}", exc_info=True)
            return WeatherResult(city=city, success=False, error_message=err_msg)

    async def fetch_weather_for_cities(
        self,
        cities: List[str],
    ) -> Dict[str, WeatherResult]:
        """Fetch current weather for multiple cities concurrently using asyncio.gather().

        All requests are initiated simultaneously over a shared aiohttp ClientSession.
        Failure of one city's request never impedes or interrupts other requests.

        Args:
            cities: List of city names.

        Returns:
            Dictionary mapping city name to WeatherResult.
        """
        if not cities:
            return {}

        unique_cities = list(dict.fromkeys(cities))  # preserve order while deduplicating
        logger.info(f"Initiating concurrent weather fetch for {len(unique_cities)} cities: {unique_cities}")

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            # Genuine parallel API fetching via asyncio.gather()
            tasks = [self.fetch_weather_for_city(session, city) for city in unique_cities]
            results: List[WeatherResult] = await asyncio.gather(*tasks)

        # Map results by city name
        return {result.city: result for result in results}

