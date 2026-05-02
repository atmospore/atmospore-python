"""Async client for the Atmospore pollen forecast API."""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from typing import Any

import aiohttp

from atmospore.exceptions import (
    APIError,
    AuthenticationError,
    AtmosporeError,
    RateLimitError,
)
from atmospore.models import (
    DailyPollen,
    SpeciesMetadata,
    TopSpecies,
)

DEFAULT_BASE_URL = "https://pollenapi.com/v1"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3


class AtmosporeClient:
    """Async client for atmospore.com pollen data.

    Use as an async context manager:

        async with AtmosporeClient(api_key="...") as client:
            forecast = await client.pollen(lat=59.91, lon=10.75)

    Or manage the session manually with `await client.close()`.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        session: aiohttp.ClientSession | None = None,
        user_agent: str = "atmospore-python/0.1.0",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> AtmosporeClient:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    # --- Public API -------------------------------------------------------

    async def pollen(
        self,
        *,
        lat: float,
        lon: float,
        dt: str | None = None,
        forecast_days: int = 1,
    ) -> list[DailyPollen]:
        """Pollen forecast at a point. Returns one DailyPollen per day.

        `dt` defaults to today (UTC) in YYYY-MM-DD format if not provided.
        """
        params = {"lat": lat, "lon": lon, "forecast_days": forecast_days, "dt": dt or _today_utc()}
        data = await self._request("GET", "/pollen", params=params)
        days = data.get("data") or data.get("forecast") or []
        # API returns `species` per day; the DailyPollen model expects `pollen_levels`.
        for day in days:
            if "species" in day and "pollen_levels" not in day:
                day["pollen_levels"] = day["species"]
        return [DailyPollen.model_validate(d) for d in days]

    async def pollen_top(
        self,
        *,
        lat: float,
        lon: float,
        dt: str | None = None,
        forecast_days: int = 1,
        limit: int | None = None,
    ) -> list[TopSpecies]:
        """Ranked top-contributing species at a point.

        `dt` defaults to today (UTC) in YYYY-MM-DD format if not provided.
        """
        params: dict[str, Any] = {
            "lat": lat,
            "lon": lon,
            "forecast_days": forecast_days,
            "dt": dt or _today_utc(),
        }
        data = await self._request("GET", "/pollen-top", params=params)
        units = (data.get("meta") or {}).get("units", "grains/m³")
        items = data.get("data") or data.get("speciesData") or []
        # Normalise: API uses `max`, model expects `max_value`.
        for it in items:
            if "max" in it and "max_value" not in it:
                it["max_value"] = it["max"]
            it.setdefault("units", units)
        result = [TopSpecies.model_validate(s) for s in items]
        return result[:limit] if limit else result

    async def pollen_area(
        self,
        *,
        lat: float,
        lon: float,
        radius_km: float = 25,
        dt: str | None = None,
        forecast_days: int = 1,
        species: list[str] | None = None,
    ) -> list[DailyPollen]:
        """Area-aggregated pollen levels (avg/min/max) over a radius."""
        params: dict[str, Any] = {
            "lat": lat,
            "lon": lon,
            "radius_km": radius_km,
            "forecast_days": forecast_days,
            "dt": dt or _today_utc(),
        }
        if species:
            params["species"] = ",".join(species)
        data = await self._request("GET", "/pollen-area", params=params)
        days = data.get("data") or data.get("forecast") or []
        # API returns `species` per day; the DailyPollen model expects `pollen_levels`.
        for day in days:
            if "species" in day and "pollen_levels" not in day:
                day["pollen_levels"] = day["species"]
        return [DailyPollen.model_validate(d) for d in days]

    async def species(self) -> list[SpeciesMetadata]:
        """Static species metadata. No API key required."""
        data = await self._request("GET", "/species", auth=False)
        raw = data.get("data") or data.get("species") or {}
        # API returns `data` as a dict keyed by species slug, e.g.
        # {"birch": {"display_name": "Birch", ...}, ...}.
        # Some older shapes returned a list — handle both.
        if isinstance(raw, dict):
            return [
                SpeciesMetadata.model_validate({**meta, "species": slug})
                for slug, meta in raw.items()
            ]
        return [SpeciesMetadata.model_validate(s) for s in raw]

    # --- Internal ---------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> dict[str, Any]:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )

        url = f"{self.base_url}{path}"
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if auth:
            if not self.api_key:
                raise AuthenticationError("api_key is required for this endpoint")
            headers["x-api-key"] = self.api_key

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with self._session.request(
                    method, url, params=params, headers=headers
                ) as resp:
                    body_text = await resp.text()

                    if resp.status == 401 or resp.status == 403:
                        raise AuthenticationError(
                            f"API key rejected (HTTP {resp.status}): {body_text[:200]}"
                        )

                    if resp.status == 429:
                        try:
                            payload = json.loads(body_text) if body_text else {}
                        except ValueError:
                            payload = {}
                        raise RateLimitError(
                            payload.get("error", "Daily quota exceeded"),
                            limit=payload.get("limit"),
                            used=payload.get("used"),
                            resets_at=payload.get("resets_at"),
                        )

                    if 500 <= resp.status < 600:
                        last_error = APIError(
                            f"Server error {resp.status}",
                            status=resp.status,
                            body=body_text[:500],
                        )
                        if attempt < self.retries:
                            await asyncio.sleep(_backoff(attempt))
                            continue
                        raise last_error

                    if not resp.ok:
                        raise APIError(
                            f"Unexpected status {resp.status}",
                            status=resp.status,
                            body=body_text[:500],
                        )

                    try:
                        return json.loads(body_text) if body_text else {}
                    except ValueError as e:
                        raise APIError(
                            f"Malformed JSON response: {e}",
                            status=resp.status,
                            body=body_text[:500],
                        ) from e

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = AtmosporeError(f"Network error: {e}")
                if attempt < self.retries:
                    await asyncio.sleep(_backoff(attempt))
                    continue
                raise last_error from e

        # Defensive — shouldn't reach here.
        if last_error:
            raise last_error
        raise AtmosporeError("Request failed after retries with no captured error")


def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter: 0.5, 1.0, 2.0 seconds + random 0-100ms."""
    return min(2.0**attempt * 0.5, 5.0) + random.random() * 0.1


def _today_utc() -> str:
    """Today's date in YYYY-MM-DD (UTC). The API requires `dt` on point endpoints."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
