"""CLI entry point: ``exoscale-ssh-key``.

Thin wrapper over the shared harness; all behaviour lives in
:class:`~exoscale_connector.resources.ssh_key.SSHKeyClient`.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.ssh_key import SSHKeyClient
from ._base import run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        SSHKeyClient,
        prog="exoscale-ssh-key",
        description="Manage Exoscale SSH keys via the APIv2.",
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())
