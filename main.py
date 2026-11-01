"""Main entry point for the Weather-Aware Order Delivery System.

Orchestrates loading environment variables, setting up logging,
triggering parallel weather checks, and presenting terminal summaries.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Ensure UTF-8 console output across all Windows terminals
if sys.platform.startswith("win"):
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

# Optional terminal coloring for clean UX
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    COLOR_ENABLED = True
except ImportError:
    COLOR_ENABLED = False

from order_processor import OrderProcessor, ProcessingSummary
from weather_service import WeatherService


def _color(text: str, color_code: str) -> str:
    """Format text with ANSI color if colorama is enabled."""
    if COLOR_ENABLED:
        return f"{color_code}{text}{Style.RESET_ALL}"
    return text


def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """Configure structured logging to console and logs/weather_errors.log file.

    Args:
        log_dir: Directory where error log file should be saved.

    Returns:
        Configured logger instance.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / "weather_errors.log"

    logger = logging.getLogger("weather_system")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # Formatter for file logging
    file_fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File Handler: captures warnings, errors, and critical messages
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    # Console Handler: informative progress output
    console_fmt = logging.Formatter("%(levelname)s: %(message)s")
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    return logger


def check_api_key() -> Optional[str]:
    """Retrieve and validate the OpenWeatherMap API key from environment.

    Returns:
        The valid API key string, or None if missing or placeholder.
    """
    load_dotenv()
    api_key = os.getenv("OPENWEATHERMAP_API_KEY", "").strip()

    if not api_key or api_key == "your_api_key_here":
        return None
    return api_key


def print_missing_key_instructions() -> None:
    """Display instructions when the OpenWeatherMap API key is missing."""
    print("=" * 72)
    print(_color("  [!] CONFIGURATION REQUIRED: OPENWEATHERMAP API KEY MISSING", Fore.YELLOW if COLOR_ENABLED else ""))
    print("=" * 72)
    print("\nTo run the Weather-Aware Order Delivery System:")
    print("  1. Create a free account at: https://home.openweathermap.org/users/sign_up")
    print("  2. Generate a free API key at: https://home.openweathermap.org/api_keys")
    print("  3. Open the '.env' file in this project directory.")
    print("  4. Set your key:")
    print("       OPENWEATHERMAP_API_KEY=your_actual_api_key_here")
    print("  5. Run the program again:\n       python main.py\n")
    print("=" * 72)


def _pad(text: str, width: int) -> str:
    """Pad text to specified width before applying color codes."""
    clean = str(text or "")
    if len(clean) < width:
        return clean + (" " * (width - len(clean)))
    return clean[:width]


def display_terminal_summary(summary: ProcessingSummary) -> None:
    """Print an executive terminal dashboard showing processing metrics.

    Args:
        summary: ProcessingSummary produced by OrderProcessor.
    """
    cyan = Fore.CYAN if COLOR_ENABLED else ""
    green = Fore.GREEN if COLOR_ENABLED else ""
    yellow = Fore.YELLOW if COLOR_ENABLED else ""
    red = Fore.RED if COLOR_ENABLED else ""
    blue = Fore.BLUE if COLOR_ENABLED else ""
    bright = Style.BRIGHT if COLOR_ENABLED else ""

    print("\n" + "=" * 76)
    print(_color(f"  {bright}WEATHER-AWARE ORDER DELIVERY SYSTEM - PROCESSING SUMMARY", cyan))
    print("=" * 76)

    # Core required summary metrics
    print(f"  * Total Orders:                {summary.total_orders}")
    print(f"  * Successfully Processed:      {_color(str(summary.successfully_processed), green)}")
    print(f"  * Delayed Orders:              {_color(str(summary.delayed_orders), yellow if summary.delayed_orders else green)}")
    print(f"  * Pending Orders:              {_color(str(summary.pending_orders), blue)}")
    print(f"  * Failed Weather Requests:     {_color(str(summary.failed_requests), red if summary.failed_requests else green)}")
    print("-" * 76)

    # Order by order table
    print(f"  {'ID':<6} {'Customer':<18} {'City':<16} {'Weather':<14} {'Status':<10}")
    print("  " + "-" * 72)

    for order in summary.processed_orders:
        oid = _pad(str(order.get("order_id", "")), 6)
        cust = _pad(str(order.get("customer", "")), 18)
        city = _pad(str(order.get("city", "")), 16)
        
        cond = order.get("weather_condition")
        if cond:
            weather_colored = _pad(cond, 14)
        elif order.get("weather_error"):
            weather_colored = _color(_pad("Failed", 14), red)
        else:
            weather_colored = _pad("N/A", 14)
        
        status = order.get("status", "Pending")
        if status == "Delayed":
            status_colored = _color(_pad(status, 10), yellow)
        elif status == "Pending" and not order.get("weather_error"):
            status_colored = _color(_pad(status, 10), green)
        else:
            status_colored = _color(_pad("Pending*", 10), red)

        print(f"  {oid} {cust} {city} {weather_colored} {status_colored}")

        # If delayed, display apology message preview
        if order.get("status") == "Delayed" and order.get("apology_message"):
            msg = order['apology_message']
            print(f"    |-- Apology: \"{msg}\"")

        # If weather error occurred, display error note
        if order.get("weather_error"):
            err_snippet = order['weather_error']
            print(f"    |-- Error: {err_snippet}")

    print("=" * 76)
    if summary.errors:
        print(_color(f"  [i] {len(summary.errors)} weather lookup issue(s) logged to logs/weather_errors.log", red))
        if any("401" in err for err in summary.errors):
            print(_color("  [!] HTTP 401 note: Newly generated OpenWeatherMap keys typically take 10-30 minutes to activate globally.", yellow))
    print(_color("  [OK] Updated orders saved successfully to 'orders.json'", green))
    print("=" * 76 + "\n")


async def async_main() -> int:
    """Async main routine."""
    logger = setup_logging()

    api_key = check_api_key()
    if not api_key:
        print_missing_key_instructions()
        return 1

    weather_service = WeatherService(api_key=api_key)
    processor = OrderProcessor(weather_service=weather_service, orders_file_path="orders.json")

    print("\nStarting Weather-Aware Order Delivery System...")
    print("Fetching weather conditions for order destination cities in parallel...\n")

    summary = await processor.process_orders()
    display_terminal_summary(summary)
    return 0


def main() -> int:
    """Entry point wrapper."""
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())

