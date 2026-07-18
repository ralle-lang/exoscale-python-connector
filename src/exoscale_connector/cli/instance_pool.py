"""CLI entry point: ``exoscale-instance-pool``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.instance_pool.InstancePoolClient`.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.instance_pool import InstancePoolClient
from ._base import run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        InstancePoolClient,
        prog="exoscale-instance-pool",
        description="Manage Exoscale instance pools via the APIv2.",
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())
