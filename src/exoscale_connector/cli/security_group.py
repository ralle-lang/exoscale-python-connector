"""CLI entry point: ``exoscale-security-group``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.security_group.SecurityGroupClient`.
"""
from __future__ import annotations

import sys

from ..resources.security_group import SecurityGroupClient
from ._base import run_resource_cli


def main() -> int:
    return run_resource_cli(
        SecurityGroupClient,
        prog="exoscale-security-group",
        description="Manage Exoscale security groups via the APIv2.",
    )


if __name__ == "__main__":
    sys.exit(main())
