"""CLI entry point: ``exoscale-sks``.

Manages SKS clusters and their nodepools. SKS has two resource kinds, so the
shared harness emits ``<verb>-cluster`` / ``<verb>-nodepool`` commands
(``list-clusters``, ``get-cluster``, ``create-cluster``, ``delete-cluster``,
``list-nodepools``, ``create-nodepool``, ``delete-nodepool``) rather than the
bare verbs.

Output is newline-terminated JSON on stdout; connector errors exit 1, argument
errors exit 2.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.sks import SksClusterClient
from ._base import PrimaryResource, SubResource, run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ``exoscale-sks`` binary."""
    return run_resource_cli(
        SksClusterClient,
        prog="exoscale-sks",
        description="Manage Exoscale SKS clusters and nodepools via the APIv2.",
        argv=argv,
        primary=PrimaryResource(singular="cluster", plural="clusters"),
        sub_resources=[
            SubResource(
                singular="nodepool",
                plural="nodepools",
                parent_arg="--cluster-id",
                list_method="list_nodepools",
                create_method="create_nodepool",
                delete_method="delete_nodepool",
            ),
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
