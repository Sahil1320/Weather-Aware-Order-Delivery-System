# AI Development Log (`AI_LOG.md`)

This document records the prompts, architectural decisions, and AI-assisted engineering methodology used to develop the core components of the **Weather-Aware Order Delivery System**.

---

## 1. Parallel API Fetching (`asyncio.gather()`)

### Intent & Objective
To query current weather data for multiple destination cities concurrently over HTTP rather than sequentially, minimizing total latency and maximizing throughput using Python's native asynchronous event loop (`asyncio`) and `aiohttp`.

### Prompt Used
```text
Write a production-grade asynchronous weather fetching service in Python using `aiohttp` and `asyncio.gather()`. 
Requirements:
1. Accept a list of city names and query OpenWeatherMap's Current Weather API concurrently.
2. Must use `asyncio.gather()` over a single shared `aiohttp.ClientSession` instance.
3. Include configurable request timeouts (`aiohttp.ClientTimeout`).
4. Ensure tasks run in parallel so that total execution time is roughly equal to the slowest individual request rather than the sum of all requests.
5. Return structured dataclass objects (`WeatherResult`) mapping city names to weather outcomes.
```

### What This Prompt Implemented
- **Module**: [`weather_service.py`](weather_service.py)
- **Implementation Details**:
  - Implemented `WeatherService.fetch_weather_for_cities(cities: List[str]) -> Dict[str, WeatherResult]`.
  - Created an `aiohttp.ClientSession` as an async context manager with a default 10-second timeout.
  - Constructed concurrent tasks using list comprehension:
    ```python
    tasks = [self.fetch_weather_for_city(session, city) for city in unique_cities]
    results: List[WeatherResult] = await asyncio.gather(*tasks)
    ```
  - Bundled responses into a lookup dictionary keyed by city name for $O(1)$ access by the order processor.

---

## 2. Error Handling & Fault Resilience (Invalid Cities & API Failures)

### Intent & Objective
To make the delivery pipeline resilient to failures: invalid city names (e.g., `InvalidCity123`), HTTP 404/401/429 status codes, connection drops, and network timeouts. A failure in one city must never crash the program or disrupt processing for other valid cities.

### Prompt Used
```text
Enhance the async weather fetching logic with robust error handling and fault resilience:
1. OpenWeatherMap returns HTTP 404 for invalid cities like 'InvalidCity123'. Catch this cleanly and return a structured failure result without raising an unhandled exception.
2. Handle HTTP 401 (invalid/missing API key), HTTP 429 (rate limits), `asyncio.TimeoutError`, and `aiohttp.ClientConnectorError`.
3. Log errors to a dedicated log file (`logs/weather_errors.log`) and console using Python's standard `logging` library.
4. Ensure that if one city fails, `asyncio.gather()` completes successfully for all other cities.
5. In the order database, do NOT mark failed requests as successfully processed; keep their status as 'Pending' and attach the error explanation.
```

### What This Prompt Implemented
- **Modules**: [`weather_service.py`](weather_service.py), [`order_processor.py`](order_processor.py), [`main.py`](main.py)
- **Implementation Details**:
  - Internalized `try...except` handling directly within `WeatherService.fetch_weather_for_city` so that each coroutine reliably resolves to a `WeatherResult` object even on network failure.
  - Checked HTTP response status codes explicitly:
    - `404`: `"City '<city>' not found (HTTP 404 - Invalid City)."`
    - `401`: `"Invalid OpenWeatherMap API key (HTTP 401 Unauthorized)."`
    - `429`: `"OpenWeatherMap API rate limit exceeded (HTTP 429)."`
  - Configured Python logging with dual handlers:
    - File handler writing to `logs/weather_errors.log`.
    - Stream handler logging progress to standard output.
  - In `OrderProcessor.process_orders()`, separated `failed_requests` from `successfully_processed` orders in the `ProcessingSummary` metrics.

---

## 3. Weather-Based Delay Logic

### Intent & Objective
To evaluate incoming weather conditions for each order and automatically transition order statuses to `"Delayed"` when inclement conditions are detected, while preserving all original order fields and keeping benign orders as `"Pending"`.

### Prompt Used
```text
Implement order status evaluation rules based on OpenWeatherMap weather conditions:
1. In OpenWeatherMap API responses, examine the `weather[0]["main"]` field.
2. If the condition is 'Rain', 'Snow', or 'Extreme' (case-insensitive), update order status to 'Delayed'.
3. For all other conditions (e.g., 'Clear', 'Clouds', 'Mist'), keep status as 'Pending'.
4. Retain all original fields from `orders.json` ('order_id', 'customer', 'city', 'status') and enrich with 'weather_condition', 'weather_description', 'temperature_c', and 'last_checked_at'.
5. Persist the updated orders list back to `orders.json` with clean indentation.
```

### What This Prompt Implemented
- **Module**: [`order_processor.py`](order_processor.py)
- **Implementation Details**:
  - Defined `DELAY_WEATHER_CONDITIONS = {"Rain", "Snow", "Extreme"}`.
  - Implemented `OrderProcessor.is_delay_condition(weather_main: Optional[str]) -> bool` with case normalization (`.strip().capitalize()`).
  - Applied the golden delay logic:
    - Delayed orders receive `status = "Delayed"` and an attached `apology_message`.
    - Non-delayed orders receive `status = "Pending"` without an apology message.
    - Preserved original JSON structure and atomic updates back to `orders.json`.

---

## 4. Weather-Aware Personalized Apology Generator

### Intent & Objective
To generate empathetic, natural-sounding, weather-specific apology messages tailored to the customer's first name, destination city, and specific weather conditions without incurring third-party paid AI API costs at runtime.

### Prompt Used
```text
Write a pure Python module `apology_generator.py` containing a reusable function:
`generate_apology(customer: str, city: str, weather: str, description: Optional[str] = None) -> str`
Requirements:
1. Extract the customer's first name (e.g., 'Alice Smith' -> 'Alice') for an empathetic, personal tone.
2. Generate context-aware messages for 'Rain', 'Snow', and 'Extreme' conditions.
   Example: "Hi Alice, your order to New York is delayed due to heavy rain. We appreciate your patience!"
3. Incorporate dynamic descriptions if present (e.g., 'heavy intensity rain', 'blizzard', 'severe weather alerts').
4. Do not require an external paid LLM API at runtime; use structured dynamic templates crafted with AI assistance.
5. Provide a safe fallback for edge cases (missing names, whitespace, unexpected conditions).
```

### What This Prompt Implemented
- **Module**: [`apology_generator.py`](apology_generator.py)
- **Implementation Details**:
  - Implemented `_extract_first_name(customer_name: str) -> str` which handles full names, single names, empty strings, and whitespace.
  - Implemented condition-specific contextual templates:
    - **Rain**: Highlights road safety and wet driving conditions.
    - **Snow**: Mentions winter road precautions and advises the customer to stay warm.
    - **Extreme**: Prioritizes courier safety during severe alerts and promises delivery as soon as conditions clear.
    - **Fallback**: Gracefully handles other inclement weather codes.
  - Zero runtime AI API keys required, making the module fast, deterministic, and free to execute.

