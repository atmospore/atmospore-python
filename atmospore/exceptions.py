"""Exceptions raised by the Atmospore client."""

from __future__ import annotations


class AtmosporeError(Exception):
    """Base exception for all Atmospore client errors."""


class AuthenticationError(AtmosporeError):
    """API key is missing, invalid, or revoked (HTTP 401/403)."""


class RateLimitError(AtmosporeError):
    """Daily quota exceeded (HTTP 429).

    Attributes:
        limit: The quota limit (calls/day).
        used: Calls used so far today.
        resets_at: ISO-8601 timestamp when the quota resets.
    """

    def __init__(
        self,
        message: str,
        *,
        limit: int | None = None,
        used: int | None = None,
        resets_at: str | None = None,
    ) -> None:
        super().__init__(message)
        self.limit = limit
        self.used = used
        self.resets_at = resets_at


class APIError(AtmosporeError):
    """The API returned a non-success response that isn't auth or rate-limit related."""

    def __init__(self, message: str, *, status: int, body: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body
