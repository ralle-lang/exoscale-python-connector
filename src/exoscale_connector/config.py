"""Client configuration and credential resolution.

Credentials and connection settings are read from the environment by default so
that secrets are never hardcoded and can be injected by any vault tooling at
runtime. :meth:`ClientConfig.from_env` is the normal entry point; the dataclass
can also be constructed directly for tests or programmatic use.
"""
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field
from typing import Optional

from .errors import ConfigError

# Well-known Exoscale zones, used only for friendly hints — never to restrict,
# since new zones are added over time.
KNOWN_ZONES = frozenset(
    {
        "ch-gva-2",
        "ch-dk-2",
        "de-fra-1",
        "de-muc-1",
        "at-vie-1",
        "at-vie-2",
        "bg-sof-1",
    }
)

# APIv2 hostnames follow this pattern; the zone is interpolated per request.
_ENDPOINT_TEMPLATE = "https://api-{zone}.exoscale.com/v2"


@dataclass
class ClientConfig:
    """Connection settings for :class:`~exoscale_connector.client.ExoscaleClient`."""

    # Credentials are excluded from repr so that logging, tracebacks, and
    # debugger output never echo them.
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    zone: Optional[str] = None
    # Optional full endpoint override (e.g. for a private gateway or test double).
    # When set, it takes precedence over the per-zone template.
    endpoint: Optional[str] = None
    timeout: float = 60.0
    verify_tls: bool = True
    max_retries: int = 3
    retry_backoff: float = 0.5
    # How many *consecutive* transient failures (connection drops, timeouts, a
    # sporadic 404 while an operation is still propagating) the async-operation
    # poll loop tolerates before giving up. Reset on every successful poll.
    max_poll_failures: int = 3
    # Default deadline for awaiting async operations. Deliberately much longer
    # than the per-request ``timeout``: a single HTTP call should fail fast, but
    # instance creates / SKS clusters routinely take minutes to settle.
    operation_timeout: float = 600.0

    def __post_init__(self) -> None:
        if not self.verify_tls:
            warnings.warn(
                "TLS certificate verification is DISABLED for Exoscale API calls "
                "(verify_tls=False / EXOSCALE_VERIFY_TLS)",
                stacklevel=2,
            )

    @classmethod
    def from_env(cls, *, zone: Optional[str] = None) -> "ClientConfig":
        """Build a config from ``EXOSCALE_*`` environment variables.

        Raises :class:`ConfigError` if the key or secret is absent. ``zone`` passed
        here overrides ``EXOSCALE_ZONE`` and may still be overridden per request.
        """
        api_key = os.environ.get("EXOSCALE_API_KEY", "").strip()
        api_secret = os.environ.get("EXOSCALE_API_SECRET", "").strip()
        if not api_key or not api_secret:
            raise ConfigError(
                "EXOSCALE_API_KEY and EXOSCALE_API_SECRET must be set in the environment"
            )
        return cls(
            api_key=api_key,
            api_secret=api_secret,
            zone=(zone or os.environ.get("EXOSCALE_ZONE") or "").strip() or None,
            endpoint=(os.environ.get("EXOSCALE_API_ENDPOINT") or "").strip() or None,
            timeout=float(os.environ.get("EXOSCALE_TIMEOUT", "60")),
            verify_tls=_env_bool("EXOSCALE_VERIFY_TLS", default=True),
        )

    def base_url(self, zone: Optional[str] = None) -> str:
        """Return the APIv2 base URL for ``zone`` (or the configured default).

        A configured ``endpoint`` override wins over the zone template.
        """
        if self.endpoint:
            return self.endpoint.rstrip("/")
        effective = (zone or self.zone or "").strip()
        if not effective:
            raise ConfigError(
                "A zone is required: set EXOSCALE_ZONE, pass zone=..., or set an endpoint override"
            )
        return _ENDPOINT_TEMPLATE.format(zone=effective)


def _env_bool(name: str, *, default: bool) -> bool:
    """Parse a boolean-ish environment variable, falling back to ``default``."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
