"""CLI entry point: ``exoscale-dns``.

Manages DNS domains and their records. DNS has two resource kinds, so the shared
harness emits ``<verb>-domain`` / ``<verb>-record`` commands (``list-domains``,
``get-domain``, ``create-domain``, ``delete-domain``, ``list-records``,
``create-record``, ``delete-record``) rather than the bare verbs.

Output is newline-terminated JSON on stdout; connector errors exit 1, argument
errors exit 2.
"""
from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.dns import DnsDomainClient
from ._base import PrimaryResource, SubResource, run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ``exoscale-dns`` binary."""
    return run_resource_cli(
        DnsDomainClient,
        prog="exoscale-dns",
        description="Manage Exoscale DNS domains and records via the APIv2.",
        argv=argv,
        primary=PrimaryResource(singular="domain", plural="domains"),
        sub_resources=[
            SubResource(
                singular="record",
                plural="records",
                parent_arg="--domain-id",
                list_method="list_records",
                create_method="create_record",
                delete_method="delete_record",
            ),
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
