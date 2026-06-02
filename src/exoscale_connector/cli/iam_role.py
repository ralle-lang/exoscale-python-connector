"""CLI entry point: ``exoscale-iam-role``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.iam_role.IAMRoleClient`.
"""
from __future__ import annotations

import sys

from ..resources.iam_role import IAMRoleClient
from ._base import run_resource_cli


def main() -> int:
    return run_resource_cli(
        IAMRoleClient,
        prog="exoscale-iam-role",
        description="Manage Exoscale IAM roles via the APIv2.",
    )


if __name__ == "__main__":
    sys.exit(main())
