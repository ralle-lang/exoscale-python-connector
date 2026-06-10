"""CLI entry point: ``exoscale-template``.

Templates are mostly read-only from the CLI's perspective; ``create`` registers
a custom template from a URL + checksum payload.
"""
from __future__ import annotations

from typing import Optional, Sequence

from ..resources.template import TemplateClient
from ._base import PrimaryResource, run_resource_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_resource_cli(
        TemplateClient,
        prog="exoscale-template",
        description="List, register and delete compute templates.",
        argv=argv,
        primary=PrimaryResource(
            singular="template",
            plural="templates",
            verbs=("list", "get", "find", "create", "delete"),
        ),
    )


if __name__ == "__main__":
    import sys

    sys.exit(main())
