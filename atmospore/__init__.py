"""Async Python client for the Atmospore pollen forecast API."""

from atmospore.client import AtmosporeClient
from atmospore.exceptions import (
    AtmosporeError,
    AuthenticationError,
    RateLimitError,
    APIError,
)
from atmospore.models import (
    DailyPollen,
    SpeciesLevel,
    SpeciesMetadata,
    TopSpecies,
)

__all__ = [
    "AtmosporeClient",
    "AtmosporeError",
    "AuthenticationError",
    "RateLimitError",
    "APIError",
    "DailyPollen",
    "SpeciesLevel",
    "SpeciesMetadata",
    "TopSpecies",
]

__version__ = "0.1.0"
