"""exoscale-connector: a clean, typed Python connector for the Exoscale APIv2.

Typical use::

    from exoscale_connector import ExoscaleClient
    from exoscale_connector.resources.security_group import SecurityGroupClient

    client = ExoscaleClient.from_env(zone="de-fra-1")
    groups = SecurityGroupClient(client).list()

Credentials come from ``EXOSCALE_API_KEY`` / ``EXOSCALE_API_SECRET`` in the
environment (inject them with your vault tooling); nothing is read from disk or
hardcoded.
"""
from __future__ import annotations

from .client import ExoscaleClient
from .config import ClientConfig
from .errors import (
    APIError,
    ConfigError,
    ExoscaleError,
    NotFoundError,
    OperationError,
    OperationTimeoutError,
    WaitTimeoutError,
)
from .models import ExoscaleModel, Operation, Reference
from .wait import wait_for_state

__version__ = "0.4.0"

__all__ = [
    "ExoscaleClient",
    "ClientConfig",
    "ExoscaleModel",
    "Operation",
    "Reference",
    "ExoscaleError",
    "ConfigError",
    "APIError",
    "NotFoundError",
    "OperationError",
    "OperationTimeoutError",
    "WaitTimeoutError",
    "wait_for_state",
    "__version__",
]
