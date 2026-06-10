"""CLI entry point: ``exoscale-zone`` (read-only)."""
from __future__ import annotations

from typing import Optional, Sequence

from ..resources.zone import ZoneClient
from ._base import PrimaryResource, run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        ZoneClient,
        prog="exoscale-zone",
        description="List Exoscale zones.",
        argv=argv,
        primary=PrimaryResource(singular="zone", plural="zones", verbs=("list",)),
    )


if __name__ == "__main__":
    import sys

    sys.exit(main())
