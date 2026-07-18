"""CLI entry point: ``exoscale-load-balancer``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.load_balancer.LoadBalancerClient`.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.load_balancer import LoadBalancerClient
from ._base import run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        LoadBalancerClient,
        prog="exoscale-load-balancer",
        description="Manage Exoscale Network Load Balancers via the APIv2.",
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())
