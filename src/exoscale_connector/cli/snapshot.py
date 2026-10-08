"""CLI entry point: ``exoscale-snapshot``.

Exposes list / get / find / delete for compute snapshots. ``/snapshot`` has
no POST, so the harness's ``create`` verb is excluded via ``verbs=``;
snapshots are triggered by an instance action instead.

Use ``exoscale-snapshot delete --id <id>`` to remove a snapshot, or trigger
creation via the instance client / Ansible.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from ..resources.snapshot import SnapshotClient
from ._base import run_resource_cli


def main(argv: Sequence[str] | None = None) -> int:
    return run_resource_cli(
        SnapshotClient,
        prog="exoscale-snapshot",
        description=(
            "Manage Exoscale compute snapshots via the APIv2. "
            "Note: snapshots are created via 'POST /instance/{id}:create-snapshot'; "
            "this CLI does not expose a create verb."
        ),
        argv=argv,
        verbs=("list", "get", "find", "delete"),
    )


if __name__ == "__main__":
    sys.exit(main())
