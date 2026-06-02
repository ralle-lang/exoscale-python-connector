"""CLI entry point: ``exoscale-private-network``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.private_network.PrivateNetworkClient`.
"""
from __future__ import annotations

import sys

from ..resources.private_network import PrivateNetworkClient
from ._base import run_resource_cli


def main() -> int:
    return run_resource_cli(
        PrivateNetworkClient,
        prog="exoscale-private-network",
        description="Manage Exoscale Private Networks via the APIv2.",
    )


if __name__ == "__main__":
    sys.exit(main())
