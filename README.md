# atmospore — async Python client

Async client for the [Atmospore](https://atmospore.com) pollen forecast API.
Species-level pollen forecasts for any point on Earth.

```bash
pip install atmospore
```

## Usage

Get a free API key at [atmospore.com/account](https://atmospore.com/account)
(100 calls/day, no credit card required).

```python
import asyncio
from atmospore import AtmosporeClient

async def main():
    async with AtmosporeClient(api_key="ak_...") as client:
        # Point forecast
        days = await client.pollen(lat=59.91, lon=10.75, forecast_days=7)
        for day in days:
            print(day.date, day.overall_risk)

        # Top contributing species today
        top = await client.pollen_top(lat=59.91, lon=10.75, limit=5)
        for s in top:
            print(s.species, s.max_value, s.units, s.risk_level)

        # Area aggregate (avg/min/max over a radius)
        area = await client.pollen_area(
            lat=59.91, lon=10.75, radius_km=25, forecast_days=7,
            species=["tree_tot", "grass_tot", "weed_tot"],
        )

        # Species metadata (no auth required)
        species = await client.species()

asyncio.run(main())
```

## API surface

| Method | Endpoint | Returns |
|---|---|---|
| `client.pollen(lat, lon, dt?, forecast_days=1)` | `/v1/pollen` | `list[DailyPollen]` |
| `client.pollen_top(lat, lon, dt?, forecast_days=1, limit?)` | `/v1/pollen-top` | `list[TopSpecies]` |
| `client.pollen_area(lat, lon, radius_km=25, dt?, forecast_days=1, species?)` | `/v1/pollen-area` | `list[DailyPollen]` |
| `client.species()` | `/v1/species` | `list[SpeciesMetadata]` (no auth) |

## Errors

```python
from atmospore import (
    AuthenticationError,  # 401/403 — bad / missing / revoked key
    RateLimitError,       # 429 — daily quota exceeded
    APIError,             # other 4xx / 5xx with status + body
    AtmosporeError,       # base class
)
```

`RateLimitError` carries `.limit`, `.used`, `.resets_at` for graceful backoff.

## Behaviour

- **Async-first** via `aiohttp`. Use as `async with AtmosporeClient(...)` or call `await client.close()`.
- **Retries** on 5xx with exponential backoff (3 retries by default).
- **Risk levels normalised** to Title Case (`'Low'`, `'Moderate'`, `'High'`, `'Very High'`) regardless of how the API serialises them.
- **Pydantic models** for typed access to response data.

## Development

```bash
git clone https://github.com/atmospore/atmospore-python
cd atmospore-python
pip install -e ".[test]"
pytest
```

## Related

- [atmospore-mcp](https://github.com/atmospore/atmospore-mcp) — MCP server for Claude and other AI assistants, built on this client.
- [atmospore.com](https://atmospore.com) — the hosted forecast and developer dashboard.

## License

MIT.
