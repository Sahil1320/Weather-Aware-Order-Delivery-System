"""Tests for WeatherService and OrderProcessor modules."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from order_processor import DELAY_WEATHER_CONDITIONS, OrderProcessor, ProcessingSummary
from weather_service import WeatherResult, WeatherService


# ==============================================================================
# 1. Delay Business Logic Tests
# ==============================================================================

class TestDelayLogic:
    """Test delay condition detection rules."""

    @pytest.mark.parametrize("condition", ["Rain", "rain", "RAIN", "Snow", "snow", "SNOW", "Extreme", "extreme"])
    def test_delay_conditions_trigger_delay(self, condition):
        """Rain, Snow, and Extreme must always evaluate to True."""
        assert OrderProcessor.is_delay_condition(condition) is True

    @pytest.mark.parametrize("condition", ["Clear", "clear", "Clouds", "clouds", "Mist", "Fog", "Drizzle", "", None])
    def test_benign_conditions_do_not_trigger_delay(self, condition):
        """Benign or other conditions must evaluate to False."""
        assert OrderProcessor.is_delay_condition(condition) is False


# ==============================================================================
# 2. WeatherService Asynchronous Unit Tests (Mocked HTTP)
# ==============================================================================

class TestWeatherService:
    """Test WeatherService API client methods with mocked aiohttp responses."""

    @pytest.mark.asyncio
    async def test_fetch_weather_success_200(self):
        """200 OK should parse weather main, description, and temperature."""
        service = WeatherService(api_key="dummy_test_key")

        mock_json = {
            "weather": [{"id": 500, "main": "Rain", "description": "heavy rain"}],
            "main": {"temp": 14.5},
            "name": "New York",
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_json)

        # Mock the async context manager on session.get
        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__.return_value = mock_resp
        mock_get_ctx.__aexit__.return_value = None

        mock_session = MagicMock()
        mock_session.get.return_value = mock_get_ctx

        result = await service.fetch_weather_for_city(mock_session, "New York")

        assert result.success is True
        assert result.city == "New York"
        assert result.main == "Rain"
        assert result.description == "heavy rain"
        assert result.temp_celsius == 14.5
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_fetch_weather_invalid_city_404(self):
        """404 Not Found should return success=False with clear error message."""
        service = WeatherService(api_key="dummy_test_key")

        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.text = AsyncMock(return_value='{"cod":"404","message":"city not found"}')

        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__.return_value = mock_resp
        mock_get_ctx.__aexit__.return_value = None

        mock_session = MagicMock()
        mock_session.get.return_value = mock_get_ctx

        result = await service.fetch_weather_for_city(mock_session, "InvalidCity123")

        assert result.success is False
        assert result.city == "InvalidCity123"
        assert result.status_code == 404
        assert "Invalid City" in result.error_message

    @pytest.mark.asyncio
    async def test_fetch_weather_timeout_handling(self):
        """TimeoutError should be handled gracefully without crashing."""
        service = WeatherService(api_key="dummy_test_key", timeout_seconds=1.0)

        mock_session = MagicMock()
        mock_session.get.side_effect = asyncio.TimeoutError()

        result = await service.fetch_weather_for_city(mock_session, "London")

        assert result.success is False
        assert result.city == "London"
        assert "timed out" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_parallel_fetching_uses_gather(self):
        """fetch_weather_for_cities must execute concurrently across all cities."""
        service = WeatherService(api_key="dummy_test_key")
        cities = ["New York", "Mumbai", "London", "InvalidCity123"]

        mock_results = {
            "New York": WeatherResult("New York", True, main="Rain", description="light rain"),
            "Mumbai": WeatherResult("Mumbai", True, main="Clear", description="clear sky"),
            "London": WeatherResult("London", True, main="Snow", description="light snow"),
            "InvalidCity123": WeatherResult("InvalidCity123", False, error_message="City not found", status_code=404),
        }

        async def fake_fetch(session, city):
            await asyncio.sleep(0.01)  # tiny yield
            return mock_results[city]

        with patch.object(service, "fetch_weather_for_city", side_effect=fake_fetch) as mock_fetch:
            results = await service.fetch_weather_for_cities(cities)

            assert len(results) == 4
            assert mock_fetch.call_count == 4
            assert results["New York"].main == "Rain"
            assert results["InvalidCity123"].success is False


# ==============================================================================
# 3. OrderProcessor Integration Tests
# ==============================================================================

class TestOrderProcessor:
    """Test full order evaluation, resilience, and persistence workflow."""

    SAMPLE_ORDERS = [
        {"order_id": "1001", "customer": "Alice Smith", "city": "New York", "status": "Pending"},
        {"order_id": "1002", "customer": "Bob Jones", "city": "Mumbai", "status": "Pending"},
        {"order_id": "1003", "customer": "Charlie Green", "city": "London", "status": "Pending"},
        {"order_id": "1004", "customer": "InvalidCity123", "city": "InvalidCity123", "status": "Pending"},
    ]

    @pytest.fixture
    def orders_file(self, tmp_path):
        """Create a temporary orders.json file."""
        file_path = tmp_path / "orders.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.SAMPLE_ORDERS, f)
        return file_path

    @pytest.mark.asyncio
    async def test_process_orders_golden_flow(self, orders_file):
        """End-to-end test simulating exact requirements:

        - New York has Rain -> Status becomes 'Delayed', apology generated
        - Mumbai has Clear -> Status remains 'Pending'
        - London has Snow -> Status becomes 'Delayed', apology generated
        - InvalidCity123 fails -> Status remains 'Pending', logged, not counted as success
        """
        mock_weather_service = MagicMock(spec=WeatherService)
        mock_weather_service.fetch_weather_for_cities = AsyncMock(
            return_value={
                "New York": WeatherResult(
                    city="New York",
                    success=True,
                    main="Rain",
                    description="heavy rain",
                    temp_celsius=12.0,
                ),
                "Mumbai": WeatherResult(
                    city="Mumbai",
                    success=True,
                    main="Clear",
                    description="clear sky",
                    temp_celsius=31.0,
                ),
                "London": WeatherResult(
                    city="London",
                    success=True,
                    main="Snow",
                    description="moderate snow",
                    temp_celsius=-1.5,
                ),
                "InvalidCity123": WeatherResult(
                    city="InvalidCity123",
                    success=False,
                    error_message="City 'InvalidCity123' not found (HTTP 404 - Invalid City).",
                    status_code=404,
                ),
            }
        )

        processor = OrderProcessor(
            weather_service=mock_weather_service,
            orders_file_path=str(orders_file),
        )

        summary = await processor.process_orders()

        # Check Summary Metrics
        assert summary.total_orders == 4
        assert summary.successfully_processed == 3  # New York, Mumbai, London
        assert summary.delayed_orders == 2          # New York (Rain), London (Snow)
        assert summary.pending_orders == 1          # Mumbai (Clear)
        assert summary.failed_requests == 1         # InvalidCity123

        # Read back persisted JSON file
        with open(orders_file, "r", encoding="utf-8") as f:
            updated_orders = json.load(f)

        assert len(updated_orders) == 4

        # Order 1001: New York (Rain -> Delayed)
        order_ny = next(o for o in updated_orders if o["order_id"] == "1001")
        assert order_ny["status"] == "Delayed"
        assert order_ny["weather_condition"] == "Rain"
        assert "heavy rain" in order_ny["apology_message"]
        assert "Hi Alice" in order_ny["apology_message"]
        assert order_ny["temperature_c"] == 12.0

        # Order 1002: Mumbai (Clear -> Pending)
        order_mum = next(o for o in updated_orders if o["order_id"] == "1002")
        assert order_mum["status"] == "Pending"
        assert order_mum["weather_condition"] == "Clear"
        assert "apology_message" not in order_mum

        # Order 1003: London (Snow -> Delayed)
        order_lon = next(o for o in updated_orders if o["order_id"] == "1003")
        assert order_lon["status"] == "Delayed"
        assert order_lon["weather_condition"] == "Snow"
        assert "moderate snow" in order_lon["apology_message"]
        assert "Hi Charlie" in order_lon["apology_message"]

        # Order 1004: InvalidCity123 (Failed fetch -> Pending with weather_error)
        order_inv = next(o for o in updated_orders if o["order_id"] == "1004")
        assert order_inv["status"] == "Pending"
        assert order_inv["weather_condition"] is None
        assert "weather_error" in order_inv
        assert "HTTP 404" in order_inv["weather_error"]
        assert "apology_message" not in order_inv

        # Verify all original fields are intact
        for o in updated_orders:
            assert "order_id" in o
            assert "customer" in o
            assert "city" in o
            assert "status" in o

    @pytest.mark.asyncio
    async def test_failure_of_one_city_does_not_abort_others(self, orders_file):
        """If one city raises an unexpected network exception, other orders proceed."""
        mock_weather_service = MagicMock(spec=WeatherService)
        mock_weather_service.fetch_weather_for_cities = AsyncMock(
            return_value={
                "New York": WeatherResult(city="New York", success=True, main="Clear"),
                "Mumbai": WeatherResult(city="Mumbai", success=False, error_message="Network dropped"),
                "London": WeatherResult(city="London", success=True, main="Rain"),
                "InvalidCity123": WeatherResult(city="InvalidCity123", success=False, error_message="404"),
            }
        )

        processor = OrderProcessor(
            weather_service=mock_weather_service,
            orders_file_path=str(orders_file),
        )

        summary = await processor.process_orders()

        assert summary.successfully_processed == 2
        assert summary.delayed_orders == 1
        assert summary.failed_requests == 2

    @pytest.mark.asyncio
    async def test_process_orders_extreme_condition(self, orders_file):
        """Verify that an order with Extreme weather is marked Delayed with proper apology."""
        mock_weather_service = MagicMock(spec=WeatherService)
        mock_weather_service.fetch_weather_for_cities = AsyncMock(
            return_value={
                "New York": WeatherResult(
                    city="New York",
                    success=True,
                    main="Extreme",
                    description="hurricane warning",
                    temp_celsius=18.0,
                ),
                "Mumbai": WeatherResult(city="Mumbai", success=True, main="Clear"),
                "London": WeatherResult(city="London", success=True, main="Clouds"),
                "InvalidCity123": WeatherResult(city="InvalidCity123", success=False, error_message="404"),
            }
        )

        processor = OrderProcessor(
            weather_service=mock_weather_service,
            orders_file_path=str(orders_file),
        )

        summary = await processor.process_orders()

        assert summary.delayed_orders == 1
        assert summary.pending_orders == 2
        assert summary.failed_requests == 1

        order_ny = next(o for o in summary.processed_orders if o["order_id"] == "1001")
        assert order_ny["status"] == "Delayed"
        assert order_ny["weather_condition"] == "Extreme"
        assert "severe weather" in order_ny["apology_message"].lower()
        assert "Hi Alice" in order_ny["apology_message"]


