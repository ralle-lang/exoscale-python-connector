"""CLI entry point: ``exoscale-deploy-target`` (read-only)."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from ..resources.deploy_target import DeployTargetClient
from ._base import PrimaryResource, run_resource_cli


def main(argv: Sequence[str] | None = None) -> int:
    return run_resource_cli(
        DeployTargetClient,
        prog="exoscale-deploy-target",
        description="List and fetch Exoscale deploy targets.",
        argv=argv,
        primary=PrimaryResource(
            singular="deploy-target", plural="deploy-targets", verbs=("list", "get")
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
