"""Pydantic models for Atmospore API responses.

Field naming follows the API: snake_case Python attributes map to the JSON keys
returned by atmospore.com. Risk levels are normalized to Title Case ('Low',
'Moderate', 'High', 'Very High') regardless of how the API serialises them
(some endpoints return lowercase, S3 location bundles return Title Case).
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, field_validator


def _normalize_risk(value: Any) -> str | None:
    """Normalise 'low' / 'LOW' / 'very_high' / 'Very High' → Title Case."""
    if value is None:
        return None
    s = str(value).strip().lower().replace("_", " ").replace("-", " ")
    return {
        "low": "Low",
        "moderate": "Moderate",
        "high": "High",
        "very high": "Very High",
    }.get(s, s.title() if s else None)


class SpeciesLevel(BaseModel):
    """Per-species pollen reading at a single point in time."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    value: float = 0.0
    units: str = "grains/m³"
    risk_level: str | None = None

    @field_validator("risk_level", mode="before")
    @classmethod
    def _normalise(cls, v: Any) -> str | None:
        return _normalize_risk(v)


class DailyPollen(BaseModel):
    """One day of pollen levels at a point or area."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    date: str
    pollen_levels: dict[str, SpeciesLevel] = {}
    overall_risk: str | None = None

    @field_validator("overall_risk", mode="before")
    @classmethod
    def _norm_risk(cls, v: Any) -> str | None:
        return _normalize_risk(v)


class TopSpecies(BaseModel):
    """A species in a ranked top-contributors list."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    species: str
    display_name: str | None = None
    category: str | None = None
    max_value: float = 0.0
    avg: float | None = None
    units: str = "grains/m³"
    risk_level: str | None = None

    @field_validator("max_value", mode="before")
    @classmethod
    def _max_alias(cls, v: Any, info: Any) -> float:
        # API uses `max`; allow that as an alias.
        return float(v) if v is not None else 0.0

    @field_validator("risk_level", mode="before")
    @classmethod
    def _norm_risk(cls, v: Any) -> str | None:
        return _normalize_risk(v)


class SpeciesMetadata(BaseModel):
    """Static metadata for a modelled species."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    species: str
    display_name: str | None = None
    category: str | None = None
    # Multilingual display names: {"en": "Birch", "sv": "Björk", "no": "Bjørk"}
    names: dict[str, str] | None = None
    # Concentration thresholds in grains/m³ for [low, moderate, high, very_high].
    risk_thresholds: list[float] | None = None
