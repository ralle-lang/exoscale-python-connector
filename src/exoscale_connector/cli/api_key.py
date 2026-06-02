"""CLI entry point: ``exoscale-api-key``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.api_key.ApiKeyClient`.
"""
from __future__ import annotations

import sys

from ..resources.api_key import ApiKeyClient
from ._base import run_resource_cli


def main() -> int:
    return run_resource_cli(
        ApiKeyClient,
        prog="exoscale-api-key",
        description="Manage Exoscale IAM API keys via the APIv2.",
    )


if __name__ == "__main__":
    sys.exit(main())
