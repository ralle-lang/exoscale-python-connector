"""CLI entry point: ``exoscale-security-group``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.security_group.SecurityGroupClient`.
"""
from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.security_group import SecurityGroupClient
from ._base import run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        SecurityGroupClient,
        prog="exoscale-security-group",
        description="Manage Exoscale security groups via the APIv2.",
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())
