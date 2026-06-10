"""Typed exception hierarchy for the Exoscale connector.

Callers can catch :class:`ExoscaleError` to handle anything raised by the
connector, or narrow to a specific subclass (e.g. :class:`ExoscaleNotFoundError`)
for control flow such as idempotent create/delete.
"""
from __future__ import annotations

from typing import Any, Optional


class ExoscaleError(Exception):
    """Base class for every error raised by the connector."""


class ConfigError(ExoscaleError):
    """Configuration is missing or invalid (e.g. credentials or zone not set)."""


class APIError(ExoscaleError):
    """The API returned a non-success HTTP status.

    Attributes
    ----------
    status_code: the HTTP status returned by the API.
    payload: the parsed JSON error body, when one was returned.
    method/url: the request that triggered the error, for diagnostics.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        payload: Optional[dict] = None,
        method: str = "",
        url: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.method = method
        self.url = url


class NotFoundError(APIError):
    """A resource lookup returned HTTP 404."""


class OperationError(ExoscaleError):
    """An asynchronous API operation finished in a non-success state."""

    def __init__(
        self, message: str, *, operation_id: str = "", state: str = "", payload: Any = None
    ) -> None:
        super().__init__(message)
        self.operation_id = operation_id
        self.state = state
        self.payload = payload


class OperationTimeoutError(OperationError):
    """An asynchronous API operation did not complete within the timeout."""


class WaitTimeoutError(ExoscaleError):
    """A resource did not reach the expected state within the timeout.

    Raised by :func:`exoscale_connector.wait.wait_for_state`. Carries the last
    observed state for diagnostics.
    """

    def __init__(self, message: str, *, expected: str = "", last_state: Optional[str] = None):
        super().__init__(message)
        self.expected = expected
        self.last_state = last_state
