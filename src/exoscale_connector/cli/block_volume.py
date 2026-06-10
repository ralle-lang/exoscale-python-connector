"""CLI entry point: ``exoscale-block-volume``.

Thin wrapper over the shared harness for block storage volume management.
The shared harness provides list / get / find / create / delete. Volume-specific
operations (attach, detach, resize) are not exposed as CLI subcommands here —
use the Python client directly or the Exoscale management console for those.
"""
from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.block_volume import BlockVolumeClient
from ._base import run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        BlockVolumeClient,
        prog="exoscale-block-volume",
        description="Manage Exoscale block storage volumes via the APIv2.",
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())
