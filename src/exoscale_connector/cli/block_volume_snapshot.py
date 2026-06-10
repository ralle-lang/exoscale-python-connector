"""CLI entry point: ``exoscale-block-volume-snapshot``.

Thin wrapper over the shared harness for block storage snapshot management.
Note: direct creation via this collection is not supported by the APIv2.
Snapshots are created via 'POST /block-storage/{id}:create-snapshot' (on the
volume). The 'create' subcommand from the shared harness is present but will
fail at the API level if called directly — use the volume client or Ansible
playbooks to trigger snapshot creation instead.
"""
from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.block_volume_snapshot import BlockVolumeSnapshotClient
from ._base import run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        BlockVolumeSnapshotClient,
        prog="exoscale-block-volume-snapshot",
        description=(
            "Manage Exoscale block storage snapshots via the APIv2. "
            "Note: snapshots are created via the block volume client "
            "('POST /block-storage/{id}:create-snapshot'), not via this CLI."
        ),
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())
