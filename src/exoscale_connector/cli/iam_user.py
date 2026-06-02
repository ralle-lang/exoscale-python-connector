"""CLI entry point: ``exoscale-iam-user``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.iam_user.IAMUserClient`.
"""
from __future__ import annotations

import sys

from ..resources.iam_user import IAMUserClient
from ._base import run_resource_cli


def main() -> int:
    return run_resource_cli(
        IAMUserClient,
        prog="exoscale-iam-user",
        description="Manage Exoscale IAM users via the APIv2.",
    )


if __name__ == "__main__":
    sys.exit(main())
