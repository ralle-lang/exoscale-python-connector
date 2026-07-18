"""CLI entry point: ``exoscale-anti-affinity-group``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.anti_affinity_group.AntiAffinityGroupClient`.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.anti_affinity_group import AntiAffinityGroupClient
from ._base import run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        AntiAffinityGroupClient,
        prog="exoscale-anti-affinity-group",
        description="Manage Exoscale anti-affinity groups via the APIv2.",
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())
