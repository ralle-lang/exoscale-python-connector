"""CLI entry point: ``exoscale-instance-type`` (read-only)."""

from __future__ import annotations

from collections.abc import Sequence

from ..resources.instance_type import InstanceTypeClient
from ._base import PrimaryResource, run_resource_cli


def main(argv: Sequence[str] | None = None) -> int:
    return run_resource_cli(
        InstanceTypeClient,
        prog="exoscale-instance-type",
        description="List compute offerings (instance types).",
        argv=argv,
        primary=PrimaryResource(
            singular="instance-type", plural="instance-types", verbs=("list", "get")
        ),
    )


if __name__ == "__main__":
    import sys

    sys.exit(main())
