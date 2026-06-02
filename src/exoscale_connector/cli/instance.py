"""CLI entry point: ``exoscale-instance``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.instance.InstanceClient`.
"""
from __future__ import annotations

import sys

from ..resources.instance import InstanceClient
from ._base import run_resource_cli


def main() -> int:
    return run_resource_cli(
        InstanceClient,
        prog="exoscale-instance",
        description="Manage Exoscale compute instances via the APIv2.",
    )


if __name__ == "__main__":
    sys.exit(main())
