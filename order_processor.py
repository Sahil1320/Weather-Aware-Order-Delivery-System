"""Order Processor module for weather-aware order status evaluation.

Coordinates parallel weather fetching, executes delay business logic,
generates personalized apology messages, and persists updated order data.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from apology_generator import generate_apology
from weather_service import WeatherResult, WeatherService

logger = logging.getLogger("weather_system")

# Inclement weather conditions that trigger delivery delays
DELAY_WEATHER_CONDITIONS: Set[str] = {"Rain", "Snow", "Extreme"}


@dataclass
class ProcessingSummary:
    """Summary metrics of the order processing run."""
    total_orders: int = 0
    successfully_processed: int = 0
    delayed_orders: int = 0
    pending_orders: int = 0
    failed_requests: int = 0
    processed_orders: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class OrderProcessor:
    """Manages order evaluation against live weather conditions."""

    def __init__(
        self,
        weather_service: WeatherService,
        orders_file_path: str = "orders.json",
    ) -> None:
        """Initialize OrderProcessor.

        Args:
            weather_service: Instance of WeatherService to query weather.
            orders_file_path: Path to the local JSON order database.
        """
        self.weather_service = weather_service
        self.orders_file_path = Path(orders_file_path)

    def load_orders(self) -> List[Dict[str, Any]]:
        """Load orders from local JSON database file.

        Returns:
            List of order dictionaries.

        Raises:
            FileNotFoundError: If the orders file does not exist.
            json.JSONDecodeError: If the file content is not valid JSON.
        """
        if not self.orders_file_path.exists():
            err = f"Orders database not found at '{self.orders_file_path}'"
            logger.error(err)
            raise FileNotFoundError(err)

        with open(self.orders_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                raise ValueError(f"Expected a JSON list of orders, got {type(data).__name__}")
            return data

    def save_orders(self, orders: List[Dict[str, Any]]) -> None:
        """Persist updated orders back to the local JSON file.

        Args:
            orders: List of updated order dictionaries.
        """
        with open(self.orders_file_path, "w", encoding="utf-8") as f:
            json.dump(orders, f, indent=2, ensure_ascii=False)
            f.write("\n")
        logger.info(f"Successfully saved {len(orders)} orders to '{self.orders_file_path}'")

    @staticmethod
    def is_delay_condition(weather_main: Optional[str]) -> bool:
        """Determine if a weather condition triggers a delay.

        Args:
            weather_main: Main weather condition string (e.g., 'Rain', 'Clear').

        Returns:
            True if condition is Rain, Snow, or Extreme (case-insensitive).
        """
        if not weather_main:
            return False
        return weather_main.strip().capitalize() in DELAY_WEATHER_CONDITIONS

    async def process_orders(self) -> ProcessingSummary:
        """Process all orders: fetch weather concurrently and update statuses.

        Execution steps:
        1. Read all orders from orders.json.
        2. Extract unique city names.
        3. Concurrently fetch current weather for all cities via asyncio.gather().
        4. Apply delay business logic and apology generation.
        5. Persist updated order statuses back to orders.json.
        6. Return execution summary metrics.

        Returns:
            ProcessingSummary containing statistics and updated orders.
        """
        orders = self.load_orders()
        summary = ProcessingSummary(total_orders=len(orders))

        if not orders:
            logger.warning("No orders found to process.")
            return summary

        # Extract all destination cities
        cities = [order.get("city", "") for order in orders if order.get("city")]

        # Concurrently fetch weather for all cities
        weather_map: Dict[str, WeatherResult] = await self.weather_service.fetch_weather_for_cities(cities)

        updated_orders: List[Dict[str, Any]] = []

        for original_order in orders:
            # Clone order dictionary to preserve all original fields
            order = dict(original_order)
            city = order.get("city", "")
            customer = order.get("customer", "")
            order_id = order.get("order_id", "N/A")

            weather_res: Optional[WeatherResult] = weather_map.get(city)

            timestamp = datetime.now(timezone.utc).isoformat()

            if weather_res and weather_res.success:
                summary.successfully_processed += 1
                condition = weather_res.main or "Unknown"
                description = weather_res.description or ""
                temp = weather_res.temp_celsius

                order["weather_condition"] = condition
                order["weather_description"] = description
                order["temperature_c"] = temp
                order["last_checked_at"] = timestamp

                # Clear previous error field if any
                order.pop("weather_error", None)

                # Delay logic: Rain, Snow, Extreme -> Delayed
                if self.is_delay_condition(condition):
                    order["status"] = "Delayed"
                    apology = generate_apology(
                        customer=customer,
                        city=city,
                        weather=condition,
                        description=description,
                    )
                    order["apology_message"] = apology
                    summary.delayed_orders += 1
                    logger.info(
                        f"Order {order_id} ({customer} -> {city}) marked DELAYED due to {condition}."
                    )
                else:
                    order["status"] = "Pending"
                    order.pop("apology_message", None)
                    summary.pending_orders += 1
                    logger.info(
                        f"Order {order_id} ({customer} -> {city}) remains PENDING (Weather: {condition})."
                    )

            else:
                # Weather fetch failed (e.g. invalid city or network error)
                summary.failed_requests += 1
                error_msg = weather_res.error_message if weather_res else "No weather response received."
                summary.errors.append(f"Order {order_id} ({city}): {error_msg}")

                # Keep original status (Pending), do NOT mark as successfully processed
                order["status"] = "Pending"
                order["weather_condition"] = None
                order["weather_description"] = None
                order["weather_error"] = error_msg
                order["last_checked_at"] = timestamp
                order.pop("apology_message", None)

                logger.warning(
                    f"Order {order_id} ({city}) weather lookup failed: {error_msg}"
                )

            updated_orders.append(order)

        # Persist updated orders to disk
        self.save_orders(updated_orders)
        summary.processed_orders = updated_orders

        return summary

