"""CLI entry point: ``exoscale-event`` (read-only)."""
from __future__ import annotations

import sys
from typing import Optional, Sequence

from ..resources.event import EventClient
from ._base import PrimaryResource, run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        EventClient,
        prog="exoscale-event",
        description="Read the Exoscale account audit event stream.",
        argv=argv,
        primary=PrimaryResource(singular="event", plural="events", verbs=("list",)),
    )


if __name__ == "__main__":
    sys.exit(main())
