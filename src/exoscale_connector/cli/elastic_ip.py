"""CLI entry point: ``exoscale-elastic-ip``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.elastic_ip.ElasticIPClient`.
"""
from __future__ import annotations

import sys

from ..resources.elastic_ip import ElasticIPClient
from ._base import run_resource_cli


def main() -> int:
    return run_resource_cli(
        ElasticIPClient,
        prog="exoscale-elastic-ip",
        description="Manage Exoscale Elastic IPs via the APIv2.",
    )


if __name__ == "__main__":
    sys.exit(main())
