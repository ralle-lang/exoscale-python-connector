"""CLI entry point: ``exoscale-snapshot``.

Exposes list / get / find / delete for compute snapshots. Creation is not
available directly (snapshots are triggered via an instance action); the
``create`` verb from the shared harness is intentionally excluded by using
a custom description that documents this constraint.

Use ``exoscale-snapshot delete --id <id>`` to remove a snapshot, or trigger
creation via the instance client / Ansible.
"""
from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.snapshot import SnapshotClient
from ._base import run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        SnapshotClient,
        prog="exoscale-snapshot",
        description=(
            "Manage Exoscale compute snapshots via the APIv2. "
            "Note: snapshots are created via 'POST /instance/{id}:create-snapshot'; "
            "this CLI does not expose a create verb."
        ),
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())
