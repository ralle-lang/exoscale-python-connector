"""CLI entry point: ``exoscale-instance``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.instance.InstanceClient`.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.instance import InstanceClient
from ._base import run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        InstanceClient,
        prog="exoscale-instance",
        description="Manage Exoscale compute instances via the APIv2.",
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())
