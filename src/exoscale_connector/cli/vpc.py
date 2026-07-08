"""CLI entry point: ``exoscale-vpc``.

Manages VPCs and their subnets. VPC has two resource kinds, so the shared
harness emits ``<verb>-vpc`` / ``<verb>-subnet`` commands (``list-vpcs``,
``get-vpc``, ``create-vpc``, ``delete-vpc``, ``list-subnets``,
``create-subnet``, ``delete-subnet``) rather than the bare verbs.

Routes and instance attach/detach are nested one level deeper (a route belongs
to a subnet, which belongs to a VPC) and don't fit the generic ``<verb>-<noun>``
harness; use :class:`~exoscale_connector.resources.vpc.VpcClient` directly for
those (``attach_subnet``, ``create_route``, ...).
"""
from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.vpc import VpcClient
from ._base import PrimaryResource, SubResource, run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        VpcClient,
        prog="exoscale-vpc",
        description="Manage Exoscale VPCs and subnets via the APIv2.",
        argv=argv,
        primary=PrimaryResource(singular="vpc", plural="vpcs"),
        sub_resources=[
            SubResource(
                singular="subnet",
                plural="subnets",
                parent_arg="--vpc-id",
                list_method="list_subnets",
                create_method="create_subnet",
                delete_method="delete_subnet",
            ),
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
