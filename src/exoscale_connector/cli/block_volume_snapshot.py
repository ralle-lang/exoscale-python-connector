"""CLI entry point: ``exoscale-block-volume-snapshot``.

Thin wrapper over the shared harness for block storage snapshot management.
``/block-storage-snapshot`` has no POST, so the harness's ``create`` verb is
excluded via ``verbs=``. Snapshots are created on the volume
('POST /block-storage/{id}:create-snapshot') — use the block volume client.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from ..resources.block_volume_snapshot import BlockVolumeSnapshotClient
from ._base import run_resource_cli


def main(argv: Sequence[str] | None = None) -> int:
    return run_resource_cli(
        BlockVolumeSnapshotClient,
        prog="exoscale-block-volume-snapshot",
        description=(
            "Manage Exoscale block storage snapshots via the APIv2. "
            "Note: snapshots are created via the block volume client "
            "('POST /block-storage/{id}:create-snapshot'), not via this CLI."
        ),
        argv=argv,
        verbs=("list", "get", "find", "delete"),
    )


if __name__ == "__main__":
    sys.exit(main())
