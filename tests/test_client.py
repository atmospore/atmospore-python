"""Tests for AtmosporeClient — all HTTP is mocked via aioresponses."""

from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses

from atmospore import (
    APIError,
    AtmosporeClient,
    AuthenticationError,
    DailyPollen,
    RateLimitError,
    SpeciesMetadata,
    TopSpecies,
)


BASE = "https://pollenapi.com/v1"


# --- Happy paths ---------------------------------------------------------


async def test_pollen_returns_daily_list():
    """Live API uses `species` per day; client maps it to `pollen_levels` for consistency."""
    payload = {
        "data": [
            {
                "date": "2026-05-01",
                "overall_risk": "high",
                "species": {
                    "birch": {"value": 564.8, "risk_level": "high"},
                    "alder": {"value": 0, "risk_level": "low"},
                },
            }
        ]
    }
    with aioresponses() as m:
        m.get(re.compile(r".*/pollen\?.*"), payload=payload)
        async with AtmosporeClient(api_key="ak_test") as c:
            days = await c.pollen(lat=59.91, lon=10.75)

    assert len(days) == 1
    day = days[0]
    assert isinstance(day, DailyPollen)
    assert day.date == "2026-05-01"
    assert day.overall_risk == "High"
    assert "birch" in day.pollen_levels
    assert day.pollen_levels["birch"].value == 564.8
    assert day.pollen_levels["birch"].risk_level == "High"


async def test_pollen_supports_legacy_pollen_levels_shape():
    """Older S3-bundle-style responses use `pollen_levels` directly."""
    payload = {
        "data": [
            {
                "date": "2026-05-01",
                "pollen_levels": {
                    "tree": {"value": 301.6, "risk_level": "High"},
                },
            }
        ]
    }
    with aioresponses() as m:
        m.get(re.compile(r".*/pollen\?.*"), payload=payload)
        async with AtmosporeClient(api_key="ak_test") as c:
            days = await c.pollen(lat=0, lon=0)
    assert days[0].pollen_levels["tree"].value == 301.6


async def test_pollen_top_normalises_max_to_max_value():
    """API returns `max` (raw); client exposes it as `max_value` on the model."""
    payload = {
        "meta": {"units": "grains/m³"},
        "data": [
            {
                "species": "betulaceae",
                "display_name": "Birch family",
                "category": "tree",
                "max": 542,
                "avg": 412.3,
                "risk_level": "high",
            },
            {
                "species": "pinaceae",
                "max": 116,
                "risk_level": "moderate",
            },
        ],
    }
    with aioresponses() as m:
        m.get(re.compile(r".*/pollen-top\?.*"), payload=payload)
        async with AtmosporeClient(api_key="ak_test") as c:
            tops = await c.pollen_top(lat=59.91, lon=10.75)

    assert len(tops) == 2
    assert all(isinstance(t, TopSpecies) for t in tops)
    assert tops[0].species == "betulaceae"
    assert tops[0].max_value == 542
    assert tops[0].risk_level == "High"  # normalised from "high"
    assert tops[0].units == "grains/m³"
    assert tops[1].risk_level == "Moderate"


async def test_pollen_top_limit():
    payload = {"meta": {"units": "grains/m³"}, "data": [{"species": f"s{i}", "max": i} for i in range(10)]}
    with aioresponses() as m:
        m.get(re.compile(r".*/pollen-top\?.*"), payload=payload)
        async with AtmosporeClient(api_key="ak_test") as c:
            tops = await c.pollen_top(lat=0, lon=0, limit=3)
    assert len(tops) == 3


async def test_pollen_area_maps_species_to_pollen_levels():
    """API returns `species` per day; client exposes it as `pollen_levels` for consistency with /pollen."""
    payload = {
        "meta": {"units": "grains/m³"},
        "data": [
            {
                "date": "2026-05-01",
                "overall_risk": "moderate",
                "species": {
                    "tree_tot": {"avg": 117.25, "max": 121, "risk_level": "moderate"},
                    "grass_tot": {"avg": 0, "max": 0, "risk_level": "low"},
                },
            }
        ],
    }
    with aioresponses() as m:
        m.get(re.compile(r".*/pollen-area\?.*"), payload=payload)
        async with AtmosporeClient(api_key="ak_test") as c:
            days = await c.pollen_area(lat=53.07, lon=8.81, radius_km=25)

    assert len(days) == 1
    assert "tree_tot" in days[0].pollen_levels
    assert days[0].pollen_levels["tree_tot"].risk_level == "Moderate"
    assert days[0].overall_risk == "Moderate"


async def test_species_no_auth_required():
    """The live API returns `data` as a dict keyed by species slug."""
    payload = {
        "meta": {"total_species": 2, "units": "grains/m³"},
        "data": {
            "birch": {
                "display_name": "Birch",
                "category": "tree",
                "names": {"en": "Birch", "no": "Bjørk", "sv": "Björk"},
                "risk_thresholds": [15, 90, 500, 1500],
            },
            "oak": {
                "display_name": "Oak",
                "category": "tree",
                "risk_thresholds": [15, 90, 500, 1500],
            },
        },
    }
    with aioresponses() as m:
        m.get(f"{BASE}/species", payload=payload)
        async with AtmosporeClient() as c:  # no api_key
            species = await c.species()
    assert len(species) == 2
    by_slug = {s.species: s for s in species}
    assert by_slug["birch"].display_name == "Birch"
    assert by_slug["birch"].names == {"en": "Birch", "no": "Bjørk", "sv": "Björk"}
    assert by_slug["birch"].risk_thresholds == [15, 90, 500, 1500]
    assert by_slug["oak"].category == "tree"


async def test_species_legacy_list_shape():
    """Older API responses returned `data` as a list — still supported for compatibility."""
    payload = {"data": [{"species": "birch", "display_name": "Birch", "category": "tree"}]}
    with aioresponses() as m:
        m.get(f"{BASE}/species", payload=payload)
        async with AtmosporeClient() as c:
            species = await c.species()
    assert len(species) == 1
    assert species[0].species == "birch"


# --- Error handling ------------------------------------------------------


async def test_missing_api_key_raises_auth_error():
    async with AtmosporeClient() as c:  # no api_key
        with pytest.raises(AuthenticationError, match="api_key is required"):
            await c.pollen(lat=0, lon=0)


async def test_401_raises_auth_error():
    with aioresponses() as m:
        m.get(re.compile(r".*/pollen\?.*"), status=401, body='{"error": "Invalid API key"}')
        async with AtmosporeClient(api_key="ak_bad") as c:
            with pytest.raises(AuthenticationError):
                await c.pollen(lat=0, lon=0)


async def test_403_raises_auth_error():
    with aioresponses() as m:
        m.get(re.compile(r".*/pollen\?.*"), status=403, body='{"error": "Forbidden"}')
        async with AtmosporeClient(api_key="ak_test") as c:
            with pytest.raises(AuthenticationError):
                await c.pollen(lat=0, lon=0)


async def test_429_raises_rate_limit_with_metadata():
    with aioresponses() as m:
        m.get(
            re.compile(r".*/pollen\?.*"),
            status=429,
            payload={
                "error": "Daily API quota exceeded",
                "limit": 100,
                "used": 101,
                "resets_at": "2026-05-02T00:00:00Z",
            },
        )
        async with AtmosporeClient(api_key="ak_test") as c:
            with pytest.raises(RateLimitError) as excinfo:
                await c.pollen(lat=0, lon=0)
    assert excinfo.value.limit == 100
    assert excinfo.value.used == 101
    assert excinfo.value.resets_at == "2026-05-02T00:00:00Z"


async def test_5xx_retries_then_succeeds():
    payload_ok = {"data": [{"date": "2026-05-01", "pollen_levels": {}}]}
    with aioresponses() as m:
        m.get(re.compile(r".*/pollen\?.*"), status=502)
        m.get(re.compile(r".*/pollen\?.*"), status=503)
        m.get(re.compile(r".*/pollen\?.*"), payload=payload_ok)
        async with AtmosporeClient(api_key="ak_test", retries=3) as c:
            days = await c.pollen(lat=0, lon=0)
    assert len(days) == 1


async def test_5xx_retries_then_gives_up():
    with aioresponses() as m:
        for _ in range(4):  # retries=3 → 4 total attempts
            m.get(re.compile(r".*/pollen\?.*"), status=502)
        async with AtmosporeClient(api_key="ak_test", retries=3) as c:
            with pytest.raises(APIError) as excinfo:
                await c.pollen(lat=0, lon=0)
    assert excinfo.value.status == 502


async def test_4xx_other_than_auth_or_rate_limit_raises_api_error():
    with aioresponses() as m:
        m.get(re.compile(r".*/pollen\?.*"), status=400, body='{"error": "Bad lat"}')
        async with AtmosporeClient(api_key="ak_test") as c:
            with pytest.raises(APIError) as excinfo:
                await c.pollen(lat=999, lon=0)
    assert excinfo.value.status == 400


async def test_malformed_json_raises_api_error():
    with aioresponses() as m:
        m.get(re.compile(r".*/pollen\?.*"), status=200, body="this is not json")
        async with AtmosporeClient(api_key="ak_test") as c:
            with pytest.raises(APIError, match="Malformed JSON"):
                await c.pollen(lat=0, lon=0)


# --- Risk level normalisation -------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("low", "Low"),
        ("LOW", "Low"),
        ("Low", "Low"),
        ("moderate", "Moderate"),
        ("Moderate", "Moderate"),
        ("high", "High"),
        ("very_high", "Very High"),
        ("very high", "Very High"),
        ("Very High", "Very High"),
        ("VERY-HIGH", "Very High"),
        (None, None),
    ],
)
async def test_risk_normalisation(raw, expected):
    payload = {
        "data": [
            {"date": "2026-05-01", "overall_risk": raw, "pollen_levels": {}}
        ]
    }
    with aioresponses() as m:
        m.get(re.compile(r".*/pollen\?.*"), payload=payload)
        async with AtmosporeClient(api_key="ak_test") as c:
            days = await c.pollen(lat=0, lon=0)
    assert days[0].overall_risk == expected
